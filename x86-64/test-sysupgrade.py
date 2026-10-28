#!/usr/bin/env python3
"""Destructive upgrades ONLY inside a disposable QEMU guest, never a live router."""
import functools
import http.server
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import threading
import time

import paramiko

base, image = map(lambda p: Path(p).resolve(), sys.argv[1:3])
disk = image.parent / 'upgrade-test.img'
shutil.copyfile(base, disk)
password = 'disposable-upgrade-test'
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(image.parent))
httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 33380), handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
log = (image.parent / 'upgrade-test.log').open('wb')
qemu = subprocess.Popen([
    'qemu-system-x86_64', '-machine', 'q35', '-m', '1024', '-smp', '2',
    # The deployed EFI/GPT disks currently boot via BIOS; smoke-test25 covers UEFI.
    '-drive', f'file={disk},format=raw,if=virtio',
    '-netdev', 'user,id=lan,hostfwd=tcp:127.0.0.1:22222-:22',
    '-device', 'virtio-net-pci,netdev=lan', '-display', 'none',
    '-serial', 'stdio', '-monitor', 'none'],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect('127.0.0.1', port=22222, username='root', password=password,
                       timeout=4, auth_timeout=4, banner_timeout=4,
                       allow_agent=False, look_for_keys=False)
    except Exception:
        client.close()
        raise
    return client


def run(client, command):
    _, out, err = client.exec_command(command, timeout=90)
    result = out.read().decode()
    errors = err.read().decode()
    if out.channel.recv_exit_status() != 0:
        raise RuntimeError(f'Guest check failed: {command}\n{result}\n{errors}')
    return result


def wait_ssh(previous_boot=None):
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if qemu.poll() is not None:
            raise RuntimeError('QEMU stopped unexpectedly')
        try:
            client = connect()
            boot = run(client, 'cat /proc/sys/kernel/random/boot_id').strip()
            if previous_boot is None or boot != previous_boot:
                return client
            client.close()
        except (OSError, paramiko.SSHException, RuntimeError):
            pass
        time.sleep(3)
    raise RuntimeError('SSH did not recover after boot/upgrade')


try:
    # Configure a test-only password through the serial console of the old image.
    selector = selectors.DefaultSelector()
    selector.register(qemu.stdout, selectors.EVENT_READ)
    start = time.monotonic()
    output = b''
    activated = False
    while time.monotonic() - start < 180:
        for key, _ in selector.select(timeout=1):
            data = os.read(key.fileobj.fileno(), 65536)
            if not data:
                raise RuntimeError('Guest exited during initial boot')
            log.write(data)
            log.flush()
            output += data
        if not activated and time.monotonic() - start > 65 and b'Please press Enter' in output:
            qemu.stdin.write(b'\n')
            qemu.stdin.flush()
            activated = True
        if activated and b'root@Johnnywrt:~# ' in output:
            qemu.stdin.write(f"printf '{password}\\n{password}\\n' | passwd root\n".encode())
            qemu.stdin.flush()
            break
    else:
        raise RuntimeError('Initial guest console not ready')
    selector.close()
    # Drain serial output continuously so a full pipe cannot block an upgrade.
    def drain():
        while data := qemu.stdout.read(4096):
            log.write(data)
            log.flush()
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    client = wait_ssh()
    run(client, r'''set -e
/etc/init.d/zerotier stop
uci set zerotier.global.enabled='0'
uci set system.@system[0].hostname='upgrade-check'
uci set network.lan.hostname='retained-test'
uci commit
mkdir -p /etc/meowx/subscriptions /etc/zerotier/networks.d
printf 'rules:\n  - MATCH,DIRECT\n' > /etc/meowx/subscriptions/upgrade-test.yaml
printf 'allowDefault=0\nallowDNS=0\n' > /etc/zerotier/networks.d/0123456789abcdef.local.conf
test -s /etc/zerotier/identity.secret
''')
    retained = ['/etc/config/network', '/etc/config/meowx', '/etc/config/zerotier',
                '/etc/shadow', '/etc/dropbear/dropbear_ed25519_host_key',
                '/etc/zerotier/identity.secret',
                '/etc/zerotier/networks.d/0123456789abcdef.local.conf',
                '/etc/meowx/subscriptions/upgrade-test.yaml']
    baseline = run(client, 'sha256sum ' + ' '.join(retained))
    # Round 1 validates old -> new; round 2 validates the new upgrade baseline.
    for round_number in (1, 2):
        backup_list = run(client, 'sysupgrade -l').splitlines()
        for path in retained:
            assert path in backup_list, f'Not preserved by sysupgrade: {path}'
        run(client, f'curl -fsS http://10.0.2.2:33380/{image.name} -o /tmp/upgrade.img.gz')
        if round_number == 2:
            run(client, 'sh /tmp/test-update-metadata.sh /usr/libexec/johnny-update /tmp/upgrade.img.gz')
        run(client, 'sysupgrade -T /tmp/upgrade.img.gz')
        boot = run(client, 'cat /proc/sys/kernel/random/boot_id').strip()
        run(client, "(trap '' HUP; sleep 2; sysupgrade /tmp/upgrade.img.gz) >/tmp/upgrade.log 2>&1 </dev/null &")
        client.close()
        client = wait_ssh(boot)
        assert run(client, 'sha256sum ' + ' '.join(retained)) == baseline, 'Retained settings changed'
        with client.open_sftp() as sftp:
            sftp.put(str(Path(__file__).with_name('test-update-metadata.sh')), '/tmp/test-update-metadata.sh')
        run(client, 'sh /tmp/test-update-metadata.sh')
        status = json.loads(run(client, '/usr/libexec/johnny-update status'))
        assert status['state'] == 'idle' and status['current'].startswith('Johnnywrt-ISO-')
        run(client, r'''set -e
test "$(uci get system.@system[0].hostname)" = upgrade-check
grep -F ' -F -z -P ' /etc/init.d/dropbear
pid=$(cat /var/run/dropbear.*.pid | head -1)
tr '\0' ' ' < "/proc/$pid/cmdline" | grep ' -z '
test -s /etc/johnnywrt-build
test -s /usr/share/rpcd/acl.d/johnny-update.json
test -s /www/luci-static/resources/view/system/johnny-update.js
/usr/bin/meowx-core -t -d /etc/meowx/run -f /etc/meowx/subscriptions/upgrade-test.yaml
fw4 check
''')
        print(f'PASS: upgrade round {round_number}, SSH authentication, retained settings and service checks', flush=True)
    client.close()
finally:
    qemu.terminate()
    try:
        qemu.wait(timeout=10)
    except subprocess.TimeoutExpired:
        qemu.kill()
        qemu.wait()
    httpd.shutdown()
    if 'reader' in locals():
        reader.join(timeout=5)
    log.close()
    disk.unlink(missing_ok=True)

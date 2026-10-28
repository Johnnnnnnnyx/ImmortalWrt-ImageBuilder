#!/usr/bin/env python3
"""Destructive upgrades ONLY inside a disposable QEMU guest, never a live router."""
import argparse
import functools
import gzip
import http.server
import json
import os
from pathlib import Path
import selectors
import shutil
import socket
import subprocess
import sys
import threading
import time

import paramiko

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('base', type=Path)
parser.add_argument('image', type=Path)
parser.add_argument('--machine', choices=('pc', 'q35'), default='pc')
parser.add_argument('--reboot-only', action='store_true')
args = parser.parse_args()
base, image = args.base.resolve(), args.image.resolve()
disk = image.parent / 'upgrade-test.img'
shutil.copyfile(base, disk)
password = 'disposable-upgrade-test'
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(image.parent))
httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 33380), handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
log = (image.parent / 'upgrade-test.log').open('wb')
monitor_path = image.parent / 'upgrade-monitor.sock'
completed = False
qemu = subprocess.Popen([
    'qemu-system-x86_64', '-machine', args.machine, '-m', '1024', '-smp', '2',
    # Match deployed i440FX/BIOS machines; smoke-test25 covers q35/UEFI.
    '-drive', f'file={disk},format=raw,if=virtio',
    '-netdev', 'user,id=lan,hostfwd=tcp:127.0.0.1:22222-:22',
    '-device', 'virtio-net-pci,netdev=lan', '-display', 'none',
    '-serial', 'stdio', '-monitor', 'none',
    '-qmp', f'unix:{monitor_path},server=on,wait=off'],
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
    started = time.monotonic()
    # TCG must write a 1 GiB image before booting; 240s was marginal in CI.
    deadline = started + 600
    next_report = started + 30
    last_status = 'No successful SSH connection yet'
    while time.monotonic() < deadline:
        if qemu.poll() is not None:
            raise RuntimeError('QEMU stopped unexpectedly')
        client = None
        try:
            client = connect()
            boot = run(client, 'cat /proc/sys/kernel/random/boot_id').strip()
            state = run(client, 'readlink /overlay/.fs_state').strip()
            last_status = f'boot changed={boot != previous_boot}, overlay state={state}'
            # S95done marks FS_STATE_READY=2 after initial filesystem setup.
            # Rebooting earlier lets fstools clear the pending overlay next boot.
            if (previous_boot is None or boot != previous_boot) and state == '2':
                run(client, 'sync')
                print(f'PASS: SSH and overlay ready after {time.monotonic() - started:.0f}s', flush=True)
                return client
            client.close()
        except (OSError, EOFError, paramiko.SSHException, RuntimeError) as error:
            last_status = f'{type(error).__name__}: {error}'
            if client is not None:
                client.close()
        if time.monotonic() >= next_report:
            print(f'Waiting for guest ({time.monotonic() - started:.0f}s): {last_status}', flush=True)
            next_report = time.monotonic() + 30
        time.sleep(3)
    raise RuntimeError('SSH and overlay did not become ready: ' + last_status)


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
    # Prove this virtual hardware can reboot before testing any firmware update.
    boot = run(client, 'cat /proc/sys/kernel/random/boot_id').strip()
    run(client, "(trap '' HUP; sleep 2; reboot) >/tmp/reboot-test.log 2>&1 </dev/null &")
    client.close()
    client = wait_ssh(boot)
    print(f'PASS: baseline BIOS reboot and SSH authentication ({args.machine})', flush=True)
    if args.reboot_only:
        client.close()
        completed = True
        sys.exit(0)
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
            sftp.put(str(Path(__file__).with_name('test-ui-layout.sh')), '/tmp/test-ui-layout.sh')
        run(client, 'sh /tmp/test-update-metadata.sh')
        run(client, 'sh /tmp/test-ui-layout.sh')
        menu_fixture = image.parent / 'luci-menu-test'
        menu_fixture.mkdir(exist_ok=True)
        with client.open_sftp() as sftp:
            sftp.get('/www/luci-static/resources/ui.js', str(menu_fixture / 'ui.js'))
            for name in sftp.listdir('/usr/share/luci/menu.d'):
                if name.endswith('.json'):
                    sftp.get('/usr/share/luci/menu.d/' + name, str(menu_fixture / name))
        subprocess.run(['node', str(Path(__file__).with_name('test-luci-menu.js')), str(menu_fixture)], check=True)
        status = json.loads(run(client, '/usr/libexec/johnny-update status'))
        assert status['state'] == 'idle' and status['current'].startswith('Johnnywrt-ISO-')
        run(client, r'''set -e
test "$(uci get system.@system[0].hostname)" = upgrade-check
grep -F ' -F -z -P ' /etc/init.d/dropbear
pid=$(cat /var/run/dropbear.*.pid | head -1)
tr '\0' ' ' < "/proc/$pid/cmdline" | grep ' -z '
test -s /etc/johnnywrt-build
test -s /usr/share/rpcd/acl.d/johnny-update.json
test -s /www/luci-static/resources/johnny/update.js
grep -q johnny_online_update /www/luci-static/resources/view/system/flash.js
test "$(jsonfilter -i /usr/share/luci/menu.d/luci-app-zerotier.json -e '@["admin/services/zerotier/config"].action.path')" = zerotier/config
test -z "$(jsonfilter -i /usr/share/luci/menu.d/luci-app-zerotier.json -e '@["admin/vpn/zerotier"].title')"
/usr/bin/meowx-core -t -d /etc/meowx/run -f /etc/meowx/subscriptions/upgrade-test.yaml
fw4 check
''')
        print(f'PASS: upgrade round {round_number}, SSH authentication, retained settings and service checks', flush=True)
    client.close()
    completed = True
finally:
    if not completed and qemu.poll() is None:
        # Capture BIOS/GRUB errors that are visible only on the VGA console.
        try:
            with socket.socket(socket.AF_UNIX) as monitor:
                monitor.settimeout(5)
                monitor.connect(str(monitor_path))
                stream = monitor.makefile('rwb', buffering=0)
                stream.readline()  # QMP greeting
                for command, arguments in [('qmp_capabilities', {}), ('query-status', {}),
                        ('screendump', {'filename': str(image.parent / 'upgrade-test-screen.ppm')})]:
                    stream.write((json.dumps({'execute': command, 'arguments': arguments, 'id': command}) + '\n').encode())
                    while response := stream.readline():
                        response = json.loads(response)
                        if response.get('id') == command:
                            print(f'Upgrade diagnostic {command}: {response}', flush=True)
                            break
        except (OSError, ValueError) as error:
            print(f'Could not capture upgrade screen: {error}', flush=True)
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
    if not completed:
        with disk.open('rb') as source, gzip.open(image.parent / 'upgrade-failed.img.gz', 'wb', compresslevel=1) as target:
            shutil.copyfileobj(source, target)
    monitor_path.unlink(missing_ok=True)
    disk.unlink(missing_ok=True)

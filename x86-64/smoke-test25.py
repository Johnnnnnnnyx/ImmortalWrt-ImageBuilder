#!/usr/bin/env python3
"""Boot the built EFI image and verify the installed bypass-router behavior."""
import gzip
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import time

image = Path(sys.argv[1])
disk = image.parent / "smoke-test.img"
log_path = image.parent / "boot-test.log"
with gzip.open(image, "rb") as source, disk.open("wb") as target:
    shutil.copyfileobj(source, target)

# This guest is disposable: the downloadable compressed image is never modified.
checks = r'''
set -ex
test "$(uci get luci.main.mediaurlbase)" = /luci-static/aurora
test -d /www/luci-static/aurora
test "$(uci get network.lan.proto)" = dhcp
test "$(uci get dhcp.lan.ignore)" = 1
test "$(uci get network.zerotier.proto)" = none
test -z "$(uci -q get zerotier.earth.id)"
test "$(uci get zerotier.global.enabled)" = 1
test "$(uci get firewall.johnny_zerotier.masq)" = 0
test "$(uci get firewall.zerotier_to_lan.dest)" = lan
test "$(uci get firewall.lan_to_zerotier.dest)" = zerotier
test -x /usr/bin/meowx-core
test -x /usr/sbin/quickstart
test -f /usr/lib/lua/luci/controller/quickstart.lua
test -z "$(jsonfilter -i /usr/share/luci/menu.d/luci-base.json -e '@["admin/nas"].title')"
fw4 check
ip link add zttest001 type dummy
ip link set zttest001 up
sleep 3
test "$(ubus call network.interface.zerotier status | jsonfilter -e '@.device')" = zttest001
ip addr add 192.0.2.2/32 dev zttest001
test "$(ip -4 -o addr show dev zttest001 | awk '{print $4}')" = 192.0.2.2/32
/etc/init.d/network reload
sleep 3
test "$(ubus call network.interface.zerotier status | jsonfilter -e '@.device')" = zttest001
/etc/init.d/network restart
for attempt in $(seq 1 30); do
    [ "$(ubus call network.interface.zerotier status | jsonfilter -e '@.device')" = zttest001 ] && break
    sleep 1
done
test "$(ubus call network.interface.zerotier status | jsonfilter -e '@.device')" = zttest001
test "$(ip -4 -o addr show dev zttest001 | awk '{print $4}')" = 192.0.2.2/32
ip link del zttest001
sleep 2
ip link add zttest002 type dummy
ip link set zttest002 up
sleep 3
test "$(ubus call network.interface.zerotier status | jsonfilter -e '@.device')" = zttest002
ip link del zttest002
# Repeat the defaults that run on an upgrade with saved configuration.
uci set network.lan.hostname=preserved-test
uci commit network
sh /rom/etc/uci-defaults/99-custom.sh
sh /rom/etc/uci-defaults/40_luci-zerotier
sh /rom/etc/uci-defaults/99-zz-bypass
test "$(uci get network.lan.hostname)" = preserved-test
test "$(uci get network.lan.proto)" = dhcp
test "$(uci get firewall.johnny_zerotier.name)" = zerotier
fw4 check
uname -r
echo JOHNNY_BOOT_TEST_PASSED
'''.strip()

process = subprocess.Popen(
    ["qemu-system-x86_64", "-machine", "q35", "-m", "512", "-smp", "2",
     "-bios", "/usr/share/OVMF/OVMF_CODE.fd",
     "-drive", f"file={disk},format=raw,if=virtio",
     "-netdev", "user,id=lan", "-device", "virtio-net-pci,netdev=lan",
     "-display", "none", "-serial", "stdio", "-monitor", "none", "-no-reboot"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
)
selector = selectors.DefaultSelector()
selector.register(process.stdout, selectors.EVENT_READ)
started = time.monotonic()
sent = False
output = b""
passed = False
try:
    with log_path.open("wb") as log:
        while time.monotonic() - started < 240:
            for key, _ in selector.select(timeout=1):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("QEMU exited before the boot checks completed")
                log.write(chunk)
                log.flush()
                output += chunk
            # Allow first-boot UCI defaults and services to finish before testing.
            if not sent and time.monotonic() - started > 65 and b"Please press Enter" in output:
                process.stdin.write(b"\n")
                # A here-document keeps the test marker separate from echoed input.
                process.stdin.write(("cat > /tmp/check.sh <<'JOHNNY_EOF'\n" + checks +
                                     "\nJOHNNY_EOF\nsh /tmp/check.sh\n").encode())
                process.stdin.flush()
                sent = True
            if b"\nJOHNNY_BOOT_TEST_PASSED\r\n" in output:
                passed = True
                break
finally:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    selector.close()
    disk.unlink(missing_ok=True)

if not passed:
    print(output[-16000:].decode(errors="replace"))
    raise SystemExit("Boot checks failed or timed out; see boot-test.log")
print("PASS: real firmware boot, DHCP bypass defaults, firewall and ZeroTier device rebinding")

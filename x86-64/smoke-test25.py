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
grep -F ' -F -z -P ' /etc/init.d/dropbear
pid=$(cat /var/run/dropbear.*.pid | head -1)
tr '\0' ' ' < "/proc/$pid/cmdline" | grep ' -z '
test "$(uci get system.@system[0].hostname)" = Johnnywrt
grep "DISTRIB_ID='ImmortalWrt'" /etc/openwrt_release
# LuCI deliberately serves the unauthenticated login page with HTTP 403.
status=$(curl -sSL -D /tmp/johnny-luci.headers -w '%{http_code}' http://127.0.0.1/cgi-bin/luci/ -o /tmp/johnny-luci.html)
test "$status" = 403
grep -i '^X-LuCI-Login-Required: yes' /tmp/johnny-luci.headers
grep 'Johnnywrt' /tmp/johnny-luci.html
grep 'johnnywrt.svg' /tmp/johnny-luci.html
curl -fsS http://127.0.0.1/luci-static/aurora/images/johnnywrt.svg -o /tmp/johnny-icon.svg
cmp /tmp/johnny-icon.svg /www/luci-static/aurora/images/johnnywrt.svg
test -f /usr/lib/lua/luci/controller/rpc.lua
test -f /usr/lib/lua/luci/model/ipkg.lua
# Exercise RPC login and a read-only UCI request in this disposable guest.
token=$(curl -fsS -H 'Content-Type: application/json' -d '{"id":1,"method":"login","params":["root",""]}' http://127.0.0.1/cgi-bin/luci/rpc/auth | jsonfilter -e '@.result')
echo "$token" | grep -Eq '^[0-9a-f]{32}$'
rpc_hostname=$(curl -fsS -H 'Content-Type: application/json' -d '{"id":2,"method":"get","params":["system","@system[0]","hostname"]}' "http://127.0.0.1/cgi-bin/luci/rpc/uci?auth=$token" | jsonfilter -e '@.result')
test "$rpc_hostname" = Johnnywrt
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
test -s /etc/meowx/run/ui/index.html
test "$(uci get meowx.mixin.ui_path)" = ui
test -z "$(uci -q get meowx.mixin.ui_name)"
test -x /usr/sbin/quickstart
test -f /usr/lib/lua/luci/controller/quickstart.lua
test -z "$(jsonfilter -i /usr/share/luci/menu.d/luci-base.json -e '@["admin/nas"].title')"
# Profile validation must work even when every geodata URL is unreachable.
(cd /etc/meowx/run && sha256sum -c geodata.sha256)
for mode in false true; do
    cat > /tmp/johnny-offline.yaml <<EOF
mode: rule
geodata-mode: $mode
geox-url:
  mmdb: http://127.0.0.1:9/unreachable
  geoip: http://127.0.0.1:9/unreachable
  geosite: http://127.0.0.1:9/unreachable
  asn: http://127.0.0.1:9/unreachable
rules:
  - GEOIP,CN,DIRECT
  - GEOSITE,cn,DIRECT
  - IP-ASN,13335,DIRECT
  - MATCH,DIRECT
EOF
    /usr/bin/meowx-core -t -d /etc/meowx/run -f /tmp/johnny-offline.yaml
done
# Updating and loading this exact kernel's module catches a mismatched feed.
# The guest disk is disposable; test-only packages never enter the ISO.
apk update
/usr/sbin/quickstart version --more | grep johnny-feeds-1
qs_base=http://127.0.0.1:3038/cgi-bin/luci/istore
qs_api() { curl -fsS --max-time 20 -H 'X-Forwarded-Sid: smoke-test' "$@"; }
qs_status() { qs_api "$qs_base/network/status/" | jsonfilter -e '@.result.networkInfo'; }
qs_wait() {
    for attempt in $(seq 1 45); do
        state=$(qs_status)
        [ "$state" = "$1" ] && return 0
        sleep 1
    done
    echo "FAIL: QuickStart expected $1, got $state"
    return 1
}
qs_wait netSuccess
qs_api "$qs_base/guide/soft-source/list/" > /tmp/qs-sources.json
grep 'ImmortalWrtUSTC' /tmp/qs-sources.json
if grep -q 'downloads.openwrt.org\|/openwrt/' /tmp/qs-sources.json; then exit 1; fi
test "$(qs_api "$qs_base/guide/soft-source/" | jsonfilter -e '@.result.softSource.url')" = https://downloads.immortalwrt.org/
cp /etc/apk/repositories.d/distfeeds.list /tmp/qs-feeds-original
sha256sum /etc/apk/repositories.d/meowx.list > /tmp/qs-thirdparty.sha256
echo 'https://custom.example/packages.adb' >> /etc/apk/repositories.d/distfeeds.list
qs_api -H 'Content-Type: application/json' -d '{"softSourceIdentity":"ImmortalWrtUSTC"}' "$qs_base/guide/soft-source/" > /tmp/qs-switch.json
test "$(jsonfilter -i /tmp/qs-switch.json -e '@.result.softSource.url')" = https://mirrors.ustc.edu.cn/immortalwrt/
test -z "$(jsonfilter -i /tmp/qs-switch.json -e '@.error')"
test "$(uci get system.@imm_init[0].apk_mirror)" = https://mirrors.ustc.edu.cn/immortalwrt
test -z "$(uci changes system)"
grep -F "option apk_mirror 'https://mirrors.ustc.edu.cn/immortalwrt'" /etc/config/system
grep '^https://custom.example/packages.adb$' /etc/apk/repositories.d/distfeeds.list
sha256sum -c /tmp/qs-thirdparty.sha256
cp /etc/apk/repositories.d/distfeeds.list /tmp/qs-feeds-switched
/etc/init.d/quickstart restart
sleep 3
test "$(qs_api "$qs_base/guide/soft-source/" | jsonfilter -e '@.result.softSource.url')" = https://mirrors.ustc.edu.cn/immortalwrt/
cmp /tmp/qs-feeds-switched /etc/apk/repositories.d/distfeeds.list
# Reject stale clients requesting an incompatible distribution without writing.
qs_api -H 'Content-Type: application/json' -d '{"softSourceIdentity":"OpenWrtHttps"}' "$qs_base/guide/soft-source/" > /tmp/qs-rejected.json
rejected=$(jsonfilter -i /tmp/qs-rejected.json -e '@.success')
test -n "$rejected"
test "$rejected" != 0
test -n "$(jsonfilter -i /tmp/qs-rejected.json -e '@.error')"
cmp /tmp/qs-feeds-switched /etc/apk/repositories.d/distfeeds.list
qs_api -H 'Content-Type: application/json' -d '{"softSourceIdentity":"ImmortalWrt"}' "$qs_base/guide/soft-source/" > /tmp/qs-switch.json
test "$(jsonfilter -i /tmp/qs-switch.json -e '@.result.softSource.url')" = https://downloads.immortalwrt.org/
test -z "$(jsonfilter -i /tmp/qs-switch.json -e '@.error')"
test "$(uci get system.@imm_init[0].apk_mirror)" = https://downloads.immortalwrt.org
test -z "$(uci changes system)"
grep -F "option apk_mirror 'https://downloads.immortalwrt.org'" /etc/config/system
sed -i '\|^https://custom.example/packages.adb$|d' /etc/apk/repositories.d/distfeeds.list
cmp /tmp/qs-feeds-original /etc/apk/repositories.d/distfeeds.list
# A failed real index must still be visible; restoring it must recover.
sed -i '\|/base/packages.adb$|c\http://127.0.0.1:9/base/packages.adb' /etc/apk/repositories.d/distfeeds.list
qs_wait softSourceFailed
cp /tmp/qs-feeds-original /etc/apk/repositories.d/distfeeds.list
qs_wait netSuccess
apk update
apk add kmod-veth
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
sh /rom/etc/uci-defaults/99-zzz-johnnywrt
test "$(uci get network.lan.hostname)" = preserved-test
test "$(uci get network.lan.proto)" = dhcp
test "$(uci get firewall.johnny_zerotier.name)" = zerotier
fw4 check
# Simulate a remote site and a local NAS with NO default/return route.
ip netns add johnny_remote
ip netns add johnny_nas
ip link add ztqa0 type veth peer name remote0
ip link set remote0 netns johnny_remote
ip link add lanqa0 type veth peer name nas0
ip link set nas0 netns johnny_nas
ip netns exec johnny_remote ip link set lo up
ip netns exec johnny_remote ip link set remote0 up
ip netns exec johnny_remote ip addr add 198.18.0.2/30 dev remote0
ip netns exec johnny_remote ip route add 198.19.0.0/16 via 198.18.0.1
ip netns exec johnny_remote ip route add 198.20.0.0/24 via 198.18.0.1
ip netns exec johnny_nas ip link set lo up
ip netns exec johnny_nas ip link set nas0 up
ip link set ztqa0 up
ip addr add 198.18.0.1/30 dev ztqa0
sleep 3
uci set network.lan.proto=static
uci set network.lan.netmask=255.255.255.0
uci set firewall.@defaults[0].fullcone=1
uci commit firewall
for subnet in 198.19.0 198.19.1; do
    uci set network.lan.ipaddr="$subnet.1"
    uci commit network
    /etc/init.d/network reload
    sleep 5
    ip link set lanqa0 master br-lan
    ip link set lanqa0 up
    ip netns exec johnny_nas ip addr flush dev nas0
    ip netns exec johnny_nas ip addr add "$subnet.2/24" dev nas0
    # Check automatic LAN-event refresh BEFORE explicitly reloading fw4.
    nft list set inet fw4 johnny_lan4 | grep "$subnet.0/24"
    if [ "$subnet" = 198.19.1 ]; then
        if nft list set inet fw4 johnny_lan4 | grep -q '198.19.0.0/24'; then
            echo 'FAIL: previous LAN subnet remained in the NAT set'
            exit 1
        fi
    fi
    ip netns exec johnny_remote ping -c 2 -W 2 "$subnet.2"
    /etc/init.d/firewall reload
    sleep 2
    fw4 check
    ip netns exec johnny_remote ping -c 2 -W 2 "$subnet.2"
    # Prove the test fails without return-path NAT, rather than merely pinging
    # a peer which already knows how to route back to the remote network.
    nft flush chain inet fw4 johnny_zt_lan
    if ip netns exec johnny_remote ping -c 1 -W 1 "$subnet.2"; then
        echo 'FAIL: NAS unexpectedly has a return path without NAT'
        exit 1
    fi
    /etc/init.d/firewall reload
    sleep 2
    ip netns exec johnny_remote ping -c 2 -W 2 "$subnet.2"
done
# A routed destination outside the directly connected LAN must NOT get NAT.
ip netns exec johnny_nas ip addr add 198.20.0.2/24 dev nas0
ip route add 198.20.0.0/24 dev br-lan
if ip netns exec johnny_remote ping -c 1 -W 1 198.20.0.2; then
    echo 'FAIL: return-path NAT leaked beyond the connected LAN'
    exit 1
fi
nft list set inet fw4 johnny_lan4
nft list chain inet fw4 johnny_zt_lan
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
activated = False
sent = False
output = b""
passed = False
try:
    with log_path.open("wb") as log:
        while time.monotonic() - started < 480:
            for key, _ in selector.select(timeout=1):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("QEMU exited before the boot checks completed")
                log.write(chunk)
                log.flush()
                output += chunk
            # Allow first-boot UCI defaults and services to finish before testing.
            if not activated and time.monotonic() - started > 65 and b"Please press Enter" in output:
                process.stdin.write(b"\n")
                process.stdin.flush()
                activated = True
            # askfirst flushes pending input while starting ash. Wait for ash's
            # actual prompt before sending the checks, otherwise they are lost.
            if activated and not sent and b"root@Johnnywrt:~# " in output:
                # A here-document keeps the test marker separate from echoed input.
                process.stdin.write(("cat > /tmp/check.sh <<'JOHNNY_EOF'\n" + checks +
                                     "\nJOHNNY_EOF\nsh /tmp/check.sh || echo JOHNNY_BOOT_TEST_FAILED\n").encode())
                process.stdin.flush()
                sent = True
            if b"\nJOHNNY_BOOT_TEST_PASSED\r\n" in output:
                passed = True
                break
            if b"\nJOHNNY_BOOT_TEST_FAILED\r\n" in output:
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
print("PASS: boot, branding, APK kernel feed, offline MeowX, device rebinding and scoped ZeroTier return-path NAT")

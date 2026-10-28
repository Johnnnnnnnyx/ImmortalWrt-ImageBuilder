#!/bin/sh
# Run in the disposable firmware guest, never against live configuration.
set -eu
helper=${1:-/usr/libexec/johnny-ui-layout.uc}
source_root=${2:-/rom}
root=$(mktemp -d /tmp/johnny-ui-test.XXXXXX)
trap 'rm -rf "$root"; rm -f "$root.before" "$root.after"' EXIT
menu=/usr/share/luci/menu.d
flash=/www/luci-static/resources/view/system/flash.js
mkdir -p "$root$menu" "$(dirname "$root$flash")"
cp "$source_root$flash" "$root$flash"
for name in luci-base luci-app-zerotier luci-app-meowx; do
    cp "$source_root$menu/$name.json" "$root$menu/"
done
ucode "$helper" "$root"
ucode -e '
    import { readfile } from "fs";
    let root = ARGV[0], menu = root + "/usr/share/luci/menu.d/";
    let zt = json(readfile(menu + "luci-app-zerotier.json"));
    let meow = json(readfile(menu + "luci-app-meowx.json"));
    assert(zt["admin/services/zerotier"].order > meow["admin/services/meowx"].order);
    assert(zt["admin/services/zerotier/config"].action.path == "zerotier/config");
    assert(zt["admin/services/zerotier/interface"].action.path == "zerotier/interface");
    assert(zt["admin/services/zerotier"].depends.acl[0] == "luci-app-zerotier");
    assert(!zt["admin/vpn/zerotier"]);
    assert(json(readfile(menu + "luci-base.json"))["admin/vpn"].title == "VPN");
' "$root"
grep -qF "'require johnny.update as johnnyUpdate';" "$root$flash"
grep -qF "'johnny_online_update'" "$root$flash"
# Integration must keep all three native actions.
for handler in handleBackup handleRestore handleSysupgrade; do
    grep -q "$handler" "$root$flash"
done
find "$root" -type f -exec sha256sum {} \; | sort > "$root.before"
ucode "$helper" "$root"
find "$root" -type f -exec sha256sum {} \; | sort > "$root.after"
cmp "$root.before" "$root.after"
rm "$root.before" "$root.after"
# An additional VPN application must retain its category.
printf '%s\n' '{"admin/vpn/other":{"title":"Other VPN"}}' > "$root$menu/other.json"
ucode "$helper" "$root"
test "$(jsonfilter -i "$root$menu/luci-base.json" -e '@["admin/vpn"].title')" = VPN
# Reject changed upstream markup before writing any files.
printf '%s\n' 'unsupported upstream page' > "$root$flash"
find "$root" -type f -exec sha256sum {} \; | sort > "$root.before"
if ucode "$helper" "$root"; then
    echo 'FAIL: unsupported page accepted' >&2
    exit 1
fi
find "$root" -type f -exec sha256sum {} \; | sort > "$root.after"
cmp "$root.before" "$root.after"
rm "$root.before" "$root.after"
echo 'PASS: UI relocation, native actions, idempotence and upstream layout guard'

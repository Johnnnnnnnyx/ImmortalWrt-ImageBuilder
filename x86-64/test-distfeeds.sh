#!/bin/sh
set -eu
cd "$(dirname "$0")"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/feeds" <<'EOF'
https://mirrors.cernet.edu.cn/openwrt/releases/25.12.2/targets/x86/64/kmods/6.12.103-1-0413601b1c3f0490e17f340fe09229ea/packages.adb
https://mirrors.vsean.net/openwrt/releases/25.12.2/packages/x86_64/base/packages.adb
https://dl.miaomiaowux.com/meowx/openwrt/openwrt-25.12/x86_64/meowx/packages.adb
https://custom.example/immortalwrt/packages.adb
https://downloads.openwrt.org/releases/25.12.2/targets/x86/64/kmods/6.12.103-1-0413601b1c3f0490e17f340fe09229ea/packages.adb
https://mirrors.ustc.edu.cn/immortalwrt/releases/25.12.2/packages/x86_64/luci/packages.adb
https://mirrors.tuna.tsinghua.edu.cn/openwrt/releases/25.12.2/packages/x86_64/luci/packages.adb
EOF
cat > "$tmp/expected" <<'EOF'
https://downloads.immortalwrt.org/releases/25.12.2/targets/x86/64/kmods/6.12.103-1-0413601b1c3f0490e17f340fe09229ea/packages.adb
https://downloads.immortalwrt.org/releases/25.12.2/packages/x86_64/base/packages.adb
https://dl.miaomiaowux.com/meowx/openwrt/openwrt-25.12/x86_64/meowx/packages.adb
https://custom.example/immortalwrt/packages.adb
https://downloads.immortalwrt.org/releases/25.12.2/targets/x86/64/kmods/6.12.103-1-0413601b1c3f0490e17f340fe09229ea/packages.adb
https://mirrors.ustc.edu.cn/immortalwrt/releases/25.12.2/packages/x86_64/luci/packages.adb
https://downloads.immortalwrt.org/releases/25.12.2/packages/x86_64/luci/packages.adb
EOF
sh johnny-fix-distfeeds "$tmp/feeds"
cmp "$tmp/expected" "$tmp/feeds"
sh johnny-fix-distfeeds "$tmp/feeds"
cmp "$tmp/expected" "$tmp/feeds"
printf 'PASS: feed correction preserves kernel ABI, custom feeds and repeat runs\n'

#!/bin/bash
# Log file for debugging
# 目前支持少部分第三方软件apk 通过打开shell/apk-custom-packages.sh的注释来集成
source shell/apk-custom-packages.sh
if [ "${CUSTOM_BYPASS:-0}" = "1" ]; then
  set -e
  CUSTOM_PACKAGES="$CUSTOM_PACKAGES luci-app-store luci-i18n-quickstart-zh-cn luci-i18n-zerotier-zh-cn"
  CUSTOM_PACKAGES="$CUSTOM_PACKAGES meowx-core meowx luci-app-meowx luci-i18n-meowx-zh-cn"
  CUSTOM_PACKAGES="$CUSTOM_PACKAGES luci-theme-aurora"
  CUSTOM_PACKAGES="$CUSTOM_PACKAGES luci-mod-rpc luci-lib-ipkg luci-compat"
fi
echo "第三方apk软件包: $CUSTOM_PACKAGES"
LOGFILE="/tmp/uci-defaults-log.txt"
echo "Starting 99-custom.sh at $(date)" >> $LOGFILE
echo "编译固件大小为: $PROFILE MB"
echo "Include Docker: $INCLUDE_DOCKER"

echo "Create pppoe-settings"
mkdir -p  /home/build/immortalwrt/files/etc/config

# 创建pppoe配置文件 yml传入环境变量ENABLE_PPPOE等 写入配置文件 供99-custom.sh读取
cat << EOF > /home/build/immortalwrt/files/etc/config/pppoe-settings
enable_pppoe=${ENABLE_PPPOE}
pppoe_account=${PPPOE_ACCOUNT}
pppoe_password=${PPPOE_PASSWORD}
EOF

echo "cat pppoe-settings"
cat /home/build/immortalwrt/files/etc/config/pppoe-settings

if [ -z "$CUSTOM_PACKAGES" ]; then
  echo "⚪️ 未选择 任何第三方软件包"
else
  # ============= 同步第三方插件库==============
  # 同步第三方软件仓库run/apk
  echo "🔄 正在同步第三方软件仓库 Cloning run file repo..."
  git clone --depth=1 https://github.com/wukongdaily/apk.git /tmp/store-apk-repo

  # 拷贝 run/x86 下所有 run 文件和apk文件 到 extra-packages 目录
  mkdir -p /home/build/immortalwrt/extra-packages
  cp -r /tmp/store-apk-repo/run/x86/* /home/build/immortalwrt/extra-packages/

  echo "✅ Run files copied to extra-packages:"
  # 解压并拷贝apk到packages目录
  sh shell/apk-prepare-packages.sh
  ls -lah /home/build/immortalwrt/packages/
fi

if [ "${CUSTOM_BYPASS:-0}" = "1" ]; then
  # Use the author's 25.12 APK instead of the older bundled theme.
  rm -f packages/luci-theme-aurora-*.apk
  curl -fL --retry 3 https://github.com/eamonxg/luci-theme-aurora/releases/download/v1.4.0/luci-theme-aurora-1.4.0-r20260920.apk -o packages/luci-theme-aurora-1.4.0-r20260920.apk
  echo '05f9015e0a4e2859f6a153f69e472f2984481490d4ce6db19b8a41bba7264f1e  packages/luci-theme-aurora-1.4.0-r20260920.apk' | sha256sum -c -
  # Bundle the dashboard and fonts so opening it needs no first-run download.
  curl -fL --retry 3 https://github.com/Zephyruso/zashboard/releases/download/v3.29.1/dist.zip -o /tmp/zashboard.zip
  echo '4f16cce229e223bd07b5a3daccfbfb8bf349d7335572d412959284ab6c9bab50  /tmp/zashboard.zip' | sha256sum -c -
  unzip -q /tmp/zashboard.zip -d /tmp/zashboard
  mkdir -p files/etc/meowx/run/ui
  cp -a /tmp/zashboard/dist/. files/etc/meowx/run/ui/
  test -s files/etc/meowx/run/ui/index.html
  # Pin upstream data to one immutable commit and verify every download.
  # These names match meowx-core's asset lookup, including its profile tests.
  GEO_URL=https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/d7fba95fbfc9eb82ec33b1762b3d7e11833eacd9
  for pair in geoip.metadb:geoip.metadb geoip.dat:GeoIP.dat geosite.dat:GeoSite.dat GeoLite2-ASN.mmdb:ASN.mmdb; do
    curl -fL --retry 3 --connect-timeout 20 --max-time 180 "$GEO_URL/${pair%%:*}" -o "files/etc/meowx/run/${pair#*:}"
  done
  cp custom25/geodata.sha256 files/etc/meowx/run/geodata.sha256
  (cd files/etc/meowx/run && sha256sum -c geodata.sha256)
  # Add the signed APK feed to ImageBuilder and the installed firmware.
  MEOWX_URL="https://dl.miaomiaowux.com/meowx/openwrt"
  MEOWX_FEED="$MEOWX_URL/openwrt-25.12/x86_64/meowx/packages.adb"
  mkdir -p keys files/etc/apk/keys files/etc/apk/repositories.d files/etc/hotplug.d/net files/etc/hotplug.d/iface
  curl -fL --retry 3 "$MEOWX_URL/public-key.pem" -o keys/meowx.pem
  echo "$MEOWX_FEED" >> repositories
  cp keys/meowx.pem files/etc/apk/keys/meowx.pem
  echo "$MEOWX_FEED" > files/etc/apk/repositories.d/meowx.list
  cp custom25/31-zerotier-interface files/etc/hotplug.d/net/31-zerotier-interface
  cp custom25/90-zerotier-rebind files/etc/hotplug.d/iface/90-zerotier-rebind
  cp custom25/99-zz-bypass files/etc/uci-defaults/99-zz-bypass
  cp custom25/99-zzz-johnnywrt files/etc/uci-defaults/99-zzz-johnnywrt
  mkdir -p files/usr/libexec files/etc/nftables.d files/usr/share/nftables.d/chain-pre/srcnat files/www/luci-static/aurora/images
  cp custom25/johnny-fix-distfeeds custom25/johnny-zt-nat custom25/johnny-ssh-qos files/usr/libexec/
  printf '%s\n' "${BUILD_ID:-development}" > files/etc/johnnywrt-build
  printf '%s\n' "${RELEASE_TAG:-development}" > files/etc/johnnywrt-release
  cp custom25/johnny-update files/usr/libexec/
  chmod 755 files/usr/libexec/johnny-update
  mkdir -p files/www/luci-static/resources/view/system files/usr/share/luci/menu.d files/usr/share/rpcd/acl.d
  cp custom25/johnny-update.js files/www/luci-static/resources/view/system/
  cp custom25/johnny-update-menu.json files/usr/share/luci/menu.d/johnny-update.json
  cp custom25/johnny-update-acl.json files/usr/share/rpcd/acl.d/johnny-update.json
  cp custom25/30-johnny-zt-lan.nft files/etc/nftables.d/
  printf 'jump johnny_zt_lan\n' > files/usr/share/nftables.d/chain-pre/srcnat/30-johnny-zt-lan.nft
  cp custom25/johnnywrt.svg files/www/luci-static/aurora/images/johnnywrt.svg
  chmod 755 files/usr/libexec/johnny-fix-distfeeds files/usr/libexec/johnny-zt-nat files/usr/libexec/johnny-ssh-qos files/etc/uci-defaults/99-zzz-johnnywrt
  # The shared defaults rewrite LAN/WAN even after a settings-preserving upgrade.
  printf '#!/bin/sh\nexit 0\n' > files/etc/uci-defaults/99-custom.sh
  # This shell fragment is unnecessary here and is not a valid UCI config.
  rm -f files/etc/config/pppoe-settings
  chmod 755 files/etc/hotplug.d/net/31-zerotier-interface files/etc/hotplug.d/iface/90-zerotier-rebind files/etc/uci-defaults/99-zz-bypass
fi

# 输出调试信息
echo "$(date '+%Y-%m-%d %H:%M:%S') - 开始构建固件..."

# ============= imm仓库内的插件==============
# 定义所需安装的包列表 下列插件你都可以自行删减
PACKAGES=""
PACKAGES="$PACKAGES curl"
PACKAGES="$PACKAGES luci-i18n-diskman-zh-cn"
PACKAGES="$PACKAGES luci-i18n-firewall-zh-cn"
PACKAGES="$PACKAGES luci-theme-argon"
PACKAGES="$PACKAGES luci-app-argon-config"
PACKAGES="$PACKAGES luci-i18n-argon-config-zh-cn"
#25.12
PACKAGES="$PACKAGES luci-i18n-package-manager-zh-cn"
PACKAGES="$PACKAGES luci-i18n-ttyd-zh-cn"
PACKAGES="$PACKAGES openssh-sftp-server"

# 文件管理器
PACKAGES="$PACKAGES luci-i18n-filemanager-zh-cn"
# ======== shell/apk-custom-packages.sh =======
# 合并imm仓库以外的第三方插件 暂时注释
PACKAGES="$PACKAGES $CUSTOM_PACKAGES"


# 判断是否需要编译 Docker 插件
if [ "$INCLUDE_DOCKER" = "yes" ]; then
    PACKAGES="$PACKAGES luci-i18n-dockerman-zh-cn"
    echo "Adding package: luci-i18n-dockerman-zh-cn"
fi

# 若构建openclash 则添加内核
if echo "$PACKAGES" | grep -q "luci-app-openclash"; then
    echo "✅ 已选择 luci-app-openclash，添加 openclash core"
    mkdir -p files/etc/openclash/core
    # Download clash_meta
    META_URL="https://raw.githubusercontent.com/vernesong/OpenClash/core/master/meta/clash-linux-amd64-v1.tar.gz"
    wget -qO- $META_URL | tar xOvz > files/etc/openclash/core/clash_meta
    chmod +x files/etc/openclash/core/clash_meta
    # Download GeoIP and GeoSite
    wget -q https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat -O files/etc/openclash/GeoIP.dat
    wget -q https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat -O files/etc/openclash/GeoSite.dat
    # Download latest openclash Client
    URL=$(curl -s https://api.github.com/repos/vernesong/OpenClash/releases/latest \
      | grep "browser_download_url.*apk" \
      | head -n1 \
      | cut -d '"' -f 4)
    echo "OpenClash latest apk: $URL"
    wget "$URL" -P /home/build/immortalwrt/packages/
else
    echo "⚪️ 未选择 luci-app-openclash"
fi

if echo "$PACKAGES" | grep -q "luci-app-ssr-plus"; then
    echo "✅ 已选择 luci-app-ssr-plus，添加 mihomo core"
    mkdir -p files/usr/bin
    # Download mihomo
    MIHOMO_URL="https://github.com/MetaCubeX/mihomo/releases/download/v1.19.24/mihomo-linux-amd64-compatible-v1.19.24.gz"
    mkdir -p files/usr/bin
    wget -qO- "$MIHOMO_URL" | gzip -dc > files/usr/bin/mihomo
    chmod +x files/usr/bin/mihomo
    echo "✅ 已下载 mihomo core"
    ls -lah files/usr/bin
else
    echo "⚪️ 未选择 luci-app-ssr-plus"
fi

# 构建镜像
echo "$(date '+%Y-%m-%d %H:%M:%S') - Building image with the following packages:"
echo "$PACKAGES"

make image PROFILE="generic" PACKAGES="$PACKAGES" FILES="/home/build/immortalwrt/files" ROOTFS_PARTSIZE=$PROFILE

if [ $? -ne 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Error: Build failed!"
    exit 1
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') - Build completed successfully."

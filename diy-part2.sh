#!/bin/bash
#
# https://github.com/P3TERX/Actions-OpenWrt
# File name: diy-part2.sh
# Description: OpenWrt DIY script part 2 (After Update feeds)
#
# Copyright (c) 2019-2024 P3TERX <https://p3terx.com>
#
# This is free software, licensed under the MIT License.
# See /LICENSE for more information.
#

# 固化网关 IP
sed -i 's/192.168.1.1/192.168.2.253/g' package/base-files/files/bin/config_generate

# 设置登录密码为 password (更稳妥的 uci-defaults 方式)
mkdir -p package/base-files/files/etc/uci-defaults
cat > package/base-files/files/etc/uci-defaults/99-set-root-password <<EOF
#!/bin/sh
echo "root:password" | chpasswd
exit 0
EOF
chmod +x package/base-files/files/etc/uci-defaults/99-set-root-password


# 注意：HomeProxy 补丁已集成到 maifeipin/homeproxy 源码，此处不再需要临时补丁。

# 集成 MetaCubeXD 面板到 HomeProxy
mkdir -p package/luci-app-homeproxy/root/etc/homeproxy/ui
curl -sL https://github.com/MetaCubeX/metacubexd/releases/latest/download/compressed-dist.tgz | tar -xz -C package/luci-app-homeproxy/root/etc/homeproxy/ui

# ============================================================
# 固化 sing-box 版本为 1.12.25
# 我们的 homeproxy 大师版 schema（URI-based DNS, routing-driven
# resolution, clash_api）已在此版本上完整验证。
# 锁定版本可防止上游 feeds 升级导致 schema 不兼容。
# ============================================================
SINGBOX_MK="feeds/packages/net/sing-box/Makefile"
if [ -f "$SINGBOX_MK" ]; then
  sed -i 's/^PKG_VERSION:=.*/PKG_VERSION:=1.12.25/' "$SINGBOX_MK"
  sed -i 's/^PKG_HASH:=.*/PKG_HASH:=881435f07b5ab8170ccf3cb69e87130759521dc0ed1ae4bfeacbe7772a93a158/' "$SINGBOX_MK"
  echo ">>> sing-box pinned to v1.12.25"
else
  echo ">>> WARNING: sing-box Makefile not found at $SINGBOX_MK"
fi

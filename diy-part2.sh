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
# sing-box 版本说明
# openwrt-24.10 feeds 自带 sing-box v1.12.25（Go 1.23 编译）。
# 我们的 homeproxy fork 使用 legacy DNS 格式（address_resolver），
# 在 1.12.x 中仍完全兼容（deprecated 但可用，1.14 才移除）。
# ============================================================

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

# 1. 固化网关 IP
sed -i 's/192.168.1.1/192.168.2.253/g' package/base-files/files/bin/config_generate

# 2. 设置登录密码为 password (更稳妥的 uci-defaults 方式)
mkdir -p package/base-files/files/etc/uci-defaults
cat > package/base-files/files/etc/uci-defaults/99-set-root-password <<EOF
#!/bin/sh
echo "root:password" | chpasswd
exit 0
EOF
chmod +x package/base-files/files/etc/uci-defaults/99-set-root-password

# 3. 彻底清理旧版 HomeProxy，全面改用原生 Sing-box TUN + sb 控制台
rm -rf feeds/luci/applications/luci-app-homeproxy
rm -rf package/feeds/luci/luci-app-homeproxy
rm -rf package/luci-app-homeproxy

# 4. 固件内置权限与目录初始化
mkdir -p files/usr/bin files/etc/sing-box/nodes
chmod +x files/usr/bin/sb files/usr/bin/sing-box-menu 2>/dev/null || true

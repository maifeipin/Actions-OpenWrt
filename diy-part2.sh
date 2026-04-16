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

# Modify default IP
#sed -i 's/192.168.1.1/192.168.50.5/g' package/base-files/files/bin/config_generate

# Modify default theme
#sed -i 's/luci-theme-bootstrap/luci-theme-argon/g' feeds/luci/collections/luci/Makefile

# Modify hostname
#sed -i 's/OpenWrt/P3TERX-Router/g' package/base-files/files/bin/config_generate

# 固化网关 IP
sed -i 's/192.168.1.1/192.168.2.253/g' package/base-files/files/bin/config_generate

# 设置登录密码
# 默认密码为 password
PASSWORD='password'
# 检查 shadow 文件是否存在
if [ -f "package/base-files/files/etc/shadow" ]; then
    # 使用 openssl 生成 SHA-512 密码哈希值（openssl 在 Ubuntu 中默认可用）
    SHA512_PASSWORD=$(openssl passwd -6 "$PASSWORD")
    # 使用 | 作为 sed 分隔符，避免哈希值中的 / 冲突
    sed -i "s|root:.*|root:${SHA512_PASSWORD}:18934:0:99999:7:::|g" package/base-files/files/etc/shadow
    echo "登录密码已设置为: $PASSWORD"
else
    echo "警告: shadow 文件不存在，密码设置可能失败"
fi

# Fix HomeProxy transport "raw" bug (Sing-box 1.8+ compatibility)
sed -i 's/transport: !isEmpty(node.transport) ? {/transport: (!isEmpty(node.transport) \&\& node.transport !== "raw") ? {/' feeds/luci/applications/luci-app-homeproxy/root/etc/homeproxy/scripts/generate_client.uc

# Fix HomeProxy missing Mainland China routing rules in bypass mode
sed -i "/outbound: 'direct-out'/a \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ push(config.route.rules, { rule_set: 'geosite-cn', action: 'route', outbound: 'direct-out' });\n\t\t\tpush(config.route.rules, { rule_set: 'geoip-cn', action: 'route', outbound: 'direct-out' });" feeds/luci/applications/luci-app-homeproxy/root/etc/homeproxy/scripts/generate_client.uc

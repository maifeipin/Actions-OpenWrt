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

# HomeProxy 补丁路径
TARGET="feeds/luci/applications/luci-app-homeproxy/root/etc/homeproxy/scripts/generate_client.uc"

# 1. 修复 Transport "raw" 崩溃问题 (Sing-box 1.8+ 兼容性)
sed -i 's/transport: !isEmpty(node.transport) ? {/transport: (!isEmpty(node.transport) \&\& node.transport !== "raw") ? {/' $TARGET

# 2. 注入 Mainland China 分流规则 (加固单行版，避免语法错误)
# 插入在 config.route.final 之前
sed -i "/config.route.final = 'main-out';/i \        if (routing_mode === 'bypass_mainland_china') { push(config.route.rules, { rule_set: 'geosite-cn', action: 'route', outbound: 'direct-out' }); push(config.route.rules, { rule_set: 'geoip-cn', action: 'route', outbound: 'direct-out' }); }" $TARGET


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

# 4. 下载 musl 版 sing-box 二进制（含 NaiveProxy 出站，CGO 静态链接 libcronet）
#    OpenWrt feeds 自带的 sing-box 不含 with_naive_outbound（需 Chromium 工具链），
#    故从官方 GitHub release 下载 musl 版（with_musl 标签，CGO 静态链接 libcronet）。
SINGBOX_VERSION="1.13.16"
SINGBOX_URL="https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VERSION}/sing-box-${SINGBOX_VERSION}-linux-amd64-musl.tar.gz"
echo "[*] 下载 musl 版 sing-box v${SINGBOX_VERSION} (含 NaiveProxy 支持)..."
curl -sSL "$SINGBOX_URL" -o /tmp/singbox-musl.tar.gz
tar -xzf /tmp/singbox-musl.tar.gz -C /tmp/
mkdir -p files/usr/bin
cp "/tmp/sing-box-${SINGBOX_VERSION}-linux-amd64-musl/sing-box" files/usr/bin/sing-box
chmod +x files/usr/bin/sing-box
rm -rf /tmp/singbox-musl.tar.gz "/tmp/sing-box-${SINGBOX_VERSION}-linux-amd64-musl"
echo "[+] sing-box musl 二进制已内置到 files/usr/bin/sing-box"

# 5. 创建 sing-box procd 守护脚本（含 TUN 设备自动重建与智能 DNS 切换）
mkdir -p files/etc/init.d
cat > files/etc/init.d/sing-box <<'INITEOF'
#!/bin/sh /etc/rc.common
START=99
USE_PROCD=1

start_service() {
  [ ! -c /dev/net/tun ] && {
    modprobe tun 2>/dev/null || insmod /lib/modules/"$(uname -r)"/tun.ko 2>/dev/null
    mkdir -p /dev/net
    [ ! -c /dev/net/tun ] && mknod /dev/net/tun c 10 200
    chmod 666 /dev/net/tun
  }

  # 启动时自动接管 dnsmasq 重定向至 Sing-box DNS (127.0.0.1#1053)
  uci set dhcp.@dnsmasq[0].noresolv='1' 2>/dev/null
  uci set dhcp.@dnsmasq[0].localuse='1' 2>/dev/null
  uci del dhcp.@dnsmasq[0].server 2>/dev/null || true
  uci add_list dhcp.@dnsmasq[0].server='127.0.0.1#1053' 2>/dev/null
  uci commit dhcp 2>/dev/null
  /etc/init.d/dnsmasq restart 2>/dev/null || true

  procd_open_instance
  procd_set_param command /usr/bin/sing-box run -c /etc/sing-box/config.json
  procd_set_param respawn 3600 5 0
  procd_set_param stdout 1
  procd_set_param stderr 1
  procd_close_instance
}

stop_service() {
  # 停止 Sing-box 时自动还原 dnsmasq 直连公共 DNS (223.5.5.5)，防全网断网
  uci del dhcp.@dnsmasq[0].noresolv 2>/dev/null || true
  uci del dhcp.@dnsmasq[0].server 2>/dev/null || true
  uci add_list dhcp.@dnsmasq[0].server='223.5.5.5' 2>/dev/null
  uci commit dhcp 2>/dev/null
  /etc/init.d/dnsmasq restart 2>/dev/null || true
}
INITEOF
chmod +x files/etc/init.d/sing-box

# 6. 固件内置权限与目录初始化
mkdir -p files/usr/bin files/etc/sing-box/nodes
chmod +x files/usr/bin/sb files/usr/bin/sing-box-menu 2>/dev/null || true


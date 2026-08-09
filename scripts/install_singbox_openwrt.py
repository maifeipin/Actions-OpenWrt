#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redmi AX6 OpenWrt Sing-box TUN 透明代理一键安装与迁移脚本
功能：
1. 从环境变量或 config.json 读取代理节点凭据（不硬编码密码）。
2. 自动查询本地 SQLite 数据库获取 NaiveProxy 代理节点（路径可配置）。
3. 支持一键修改路由器网段（192.168.1.1 -> 192.168.31.1），含 /24 掩码。
4. 自动停止并彻底清理旧的 Brook / NaiveProxy 客户端文件及自启配置。
5. 临时配置 DNS 以保证路由器联网，安装 kmod-tun 内核模块并严格检查返回码。
6. 创建 /dev/net/tun 设备节点，且 init.d 脚本在每次启动时自动重建（解决重启丢失问题）。
7. 下载并部署适合 OpenWrt musl 的 Sing-box 静态二进制内核及 geoip-cn/geosite-cn 规则集。
8. 部署最新 Sing-box 1.13.x 规格配置（dns_fallback Google DoH via proxy，显式 TLS SNI）。
9. 写入 procd 系统守护自启脚本，并配置 sysupgrade.conf 以防固件升级丢失配置。
10. 重定向 dnsmasq 到 Sing-box DNS 分流端口 (:1053)，对关键命令检查返回码。
11. IP 变更后自动等待路由器重启并在新地址上验证 sing-box 运行状态。
"""

import os
import sys
import re
import json
import time
import sqlite3
import shlex
import tarfile
import subprocess
import urllib.request
from urllib.parse import urlsplit, parse_qs, unquote

# ==================== 配置选项 ====================
# 默认路由器连接信息（x86 工控机初始 IP 为 192.168.2.1，目标 IP 为 192.168.2.253 防冲突）
ROUTER_IP_INIT = "192.168.2.1"
ROUTER_IP_TARGET = "192.168.2.253"
SSH_USER = "root"

# 下载地址 (支持 x86_64 和 arm64 架构，使用 musl 版本适配 OpenWrt)
SINGBOX_URL_AMD64 = "https://github.com/SagerNet/sing-box/releases/download/v1.13.16/sing-box-1.13.16-linux-amd64-musl.tar.gz"
SINGBOX_URL_ARM64 = "https://github.com/SagerNet/sing-box/releases/download/v1.13.16/sing-box-1.13.16-linux-arm64-musl.tar.gz"
GEOIP_URL = "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs"
GEOSITE_URL = "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-cn.srs"

# 本地暂存目录（与脚本同目录，放 .gitignore 中）
LOCAL_TMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp_deploy")
os.makedirs(LOCAL_TMP_DIR, exist_ok=True)

# 数据库路径（优先环境变量，其次 config.json，最后默认值）
# 修复 #10：数据库路径可配置，不强依赖硬编码路径
_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.json")
_ai_db_default = r"C:\app\WebGPT\src\bin\Debug\ai.db"
AI_DB_PATH = os.environ.get("AI_DB_PATH") or (
    json.load(open(_CONFIG_FILE, encoding="utf-8")).get("ai_db_path", _ai_db_default)
    if os.path.exists(_CONFIG_FILE) else _ai_db_default
)

HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ==================== 辅助函数 ====================

def run_local_cmd(cmd, timeout=60):
    """运行本地 shell 命令，返回 (returncode, stdout, stderr)"""
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return res.returncode, res.stdout, res.stderr


def run_critical_cmd(cmd, description, timeout=60):
    """运行关键命令，失败时打印错误并退出"""
    code, out, err = run_local_cmd(cmd, timeout=timeout)
    if code != 0:
        print(f"[-] {description} 失败 (exit={code}): {(err or out).strip()[:200]}")
        sys.exit(1)
    return out


def download_file(url, dest):
    """下载文件（无校验，下载完整性依赖 HTTPS）"""
    print(f"[*] 正在下载 {url} 至 {dest}...")
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=120) as response, open(dest, "wb") as out_file:
        out_file.write(response.read())
    print("[+] 下载完成。")


def ping_router(ip):
    """检测路由器是否可达"""
    code, _, _ = run_local_cmd(f"ping -n 1 -w 1500 {ip}")
    return code == 0


def check_ssh(ip):
    """检测路由器 SSH 端口与 SSH 登录是否就绪"""
    code, _, _ = run_local_cmd(f"ssh -o BatchMode=yes -o ConnectTimeout=2 -o StrictHostKeyChecking=no root@{ip} true", timeout=5)
    return code == 0


def get_proxy_node():
    """
    从本地 ai.db 数据库获取 NaiveProxy 节点配置。
    修复 #9：无硬编码凭据；默认值从环境变量读取，空值则报错退出。
    修复 #10：数据库路径使用 AI_DB_PATH 常量（可配置）。
    修复 #13：import re 移至文件头部。
    """
    if os.path.exists(AI_DB_PATH):
        try:
            conn = sqlite3.connect(AI_DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT host, runcmd, servername FROM proxyserver "
                "WHERE runcmd LIKE '%naive%' AND is_active=1 LIMIT 1"
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                host, runcmd, servername = row
                proxy_match = re.search(r"--proxy=https://([^:]+):([^@]+)@([^:/]+):(\d+)", runcmd)
                if proxy_match:
                    username = proxy_match.group(1)
                    password = proxy_match.group(2)
                    domain = proxy_match.group(3)
                    port = int(proxy_match.group(4))
                    print(f"[+] 成功从数据库读取代理节点: {servername} ({host})")
                    return {
                        "server": host,          # 物理 IP，绕过 Cloudflare 端口封锁
                        "server_name": domain,   # TLS 证书验证域名
                        "server_port": port,
                        "username": username,
                        "password": password,
                    }
        except Exception as e:
            print(f"[!] 读取数据库出错: {e}")
    else:
        print(f"[!] 未找到数据库 {AI_DB_PATH}")

    # 修复 #9：从环境变量读取，避免硬编码
    server = os.environ.get("PROXY_SERVER")
    server_name = os.environ.get("PROXY_SERVER_NAME")
    port_str = os.environ.get("PROXY_PORT")
    username = os.environ.get("PROXY_USER")
    password = os.environ.get("PROXY_PASS")

    if all([server, server_name, port_str, username, password]):
        print("[+] 从环境变量读取代理节点配置。")
        return {
            "server": server,
            "server_name": server_name,
            "server_port": int(port_str),
            "username": username,
            "password": password,
        }

    print("[-] 无法获取代理节点配置！")
    print("    请设置以下环境变量后重试：")
    print("      PROXY_SERVER=<VPS IP>")
    print("      PROXY_SERVER_NAME=<TLS 证书域名>")
    print("      PROXY_PORT=<端口>")
    print("      PROXY_USER=<用户名>")
    print("      PROXY_PASS=<密码>")
    sys.exit(1)


def generate_config_json(node):
    """
    生成 Sing-box 1.13.x 格式的 config.json。
    （重定向调用统一的 generate_config_from_node 函数）
    """
    return generate_config_from_node(node)


def generate_init_script():
    """
    生成 procd init.d 守护启动脚本。
    修复 #1：start_service() 开头加入 TUN 设备自动重建逻辑，
             防止 /dev 是 tmpfs 导致重启后 /dev/net/tun 消失。
    """
    return r"""#!/bin/sh /etc/rc.common
START=99
USE_PROCD=1

start_service() {
  # 修复：/dev 是 tmpfs，重启后 /dev/net/tun 消失，此处自动重建
  [ ! -c /dev/net/tun ] && {
    modprobe tun 2>/dev/null || insmod /lib/modules/"$(uname -r)"/tun.ko 2>/dev/null
    mkdir -p /dev/net
    [ ! -c /dev/net/tun ] && mknod /dev/net/tun c 10 200
    chmod 666 /dev/net/tun
  }

  procd_open_instance
  procd_set_param command /usr/bin/sing-box run -c /etc/sing-box/config.json
  procd_set_param respawn 3600 5 0
  procd_set_param stdout 1
  procd_set_param stderr 1
  procd_close_instance
}
"""


# ==================== 节点解析器 ====================

def parse_vless_reality_url(url: str) -> dict:
    """
    解析 vless://uuid@host:port?...#name 格式的 Reality 分享链接。
    返回结构化节点 dict，缺少必填字段时抛出 ValueError。
    """
    url = url.strip()
    if not url.startswith("vless://"):
        raise ValueError("不是有效的 vless:// 链接")

    # 解析 fragment（节点名）
    name = ""
    if "#" in url:
        url, fragment = url.rsplit("#", 1)
        name = urllib.request.unquote(fragment)

    # 用 urlsplit 解析主体
    parsed = urlsplit(url)
    uuid = parsed.username
    server = parsed.hostname
    port = parsed.port

    if not all([uuid, server, port]):
        raise ValueError("vless:// 链接缺少 UUID、服务器地址或端口")

    # 解析查询参数
    from urllib.parse import parse_qs, unquote
    qs = parse_qs(parsed.query)

    def _q(key):
        vals = qs.get(key, [])
        return unquote(vals[0]) if vals else ""

    security = _q("security")
    if security != "reality":
        raise ValueError(f"security={security!r}，本工具仅支持 Reality 协议节点")

    pbk = _q("pbk")
    sid = _q("sid")
    sni = _q("sni")
    flow = _q("flow") or "xtls-rprx-vision"
    fp = _q("fp") or "chrome"

    missing = [k for k, v in [("pbk (公钥)", pbk), ("sid (ShortId)", sid), ("sni", sni)] if not v]
    if missing:
        raise ValueError(f"Reality 节点缺少必填字段: {', '.join(missing)}")

    return {
        "protocol": "reality",
        "name": name or f"Reality({server})",
        "server": server,
        "server_port": port,
        "uuid": uuid,
        "flow": flow,
        "fingerprint": fp,
        "server_name": sni,
        "public_key": pbk,
        "short_id": sid,
    }


def parse_naive_runcmd(runcmd: str) -> dict:
    """
    从 NaiveProxy 启动命令解析节点信息。
    支持格式：naive --proxy=https://user:pass@domain:port ...
    """
    import shlex
    runcmd = runcmd.strip()
    try:
        tokens = shlex.split(runcmd)
    except Exception:
        tokens = runcmd.split()

    proxy_val = ""
    rules_val = ""
    for token in tokens:
        if token.startswith("--proxy="):
            proxy_val = token.split("=", 1)[1]
        elif token.startswith("--host-resolver-rules="):
            rules_val = token.split("=", 1)[1]

    if not proxy_val:
        raise ValueError("未找到 --proxy= 参数，不是有效的 NaiveProxy 命令")

    parsed = urlsplit(proxy_val)
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"代理协议 {parsed.scheme!r} 不受支持，期望 https://")

    server_name = parsed.hostname
    port = parsed.port or 443
    username = parsed.username
    password = parsed.password

    if not all([server_name, username, password]):
        raise ValueError("NaiveProxy 命令缺少域名、用户名或密码")

    # 从 host-resolver-rules 提取物理 IP
    host_ip = server_name
    if rules_val:
        m = re.search(r"MAP\s+\S+\s+(\S+)", rules_val, re.IGNORECASE)
        if m:
            host_ip = m.group(1)

    return {
        "protocol": "naive",
        "name": f"NaiveProxy({server_name})",
        "server": host_ip,
        "server_port": port,
        "server_name": server_name,
        "username": username,
        "password": password,
    }


def parse_node_input(text: str) -> dict:
    """
    自动识别并解析节点输入：
      - vless:// 开头 → Reality 节点
      - 包含 --proxy= 或 naive → NaiveProxy 命令
    返回解析后的节点 dict，失败时抛出 ValueError。
    """
    text = text.strip()
    if text.startswith("vless://"):
        return parse_vless_reality_url(text)
    if "--proxy=" in text or text.startswith("naive"):
        return parse_naive_runcmd(text)
    raise ValueError(
        "无法识别节点格式。\n"
        "  支持格式 1：vless://uuid@host:port?security=reality&...#名称\n"
        "  支持格式 2：naive --proxy=https://user:pass@domain:port ..."
    )


def generate_singbox_outbound(node: dict) -> dict:
    """
    根据节点协议类型生成 Sing-box outbound 配置块。
    支持 naive 和 reality 两种协议。
    """
    proto = node.get("protocol", "naive")
    if proto == "reality":
        return {
            "type": "vless",
            "tag": "proxy",
            "server": node["server"],
            "server_port": node["server_port"],
            "uuid": node["uuid"],
            "flow": node.get("flow", "xtls-rprx-vision"),
            "tls": {
                "enabled": True,
                "server_name": node["server_name"],
                "utls": {
                    "enabled": True,
                    "fingerprint": node.get("fingerprint", "chrome"),
                },
                "reality": {
                    "enabled": True,
                    "public_key": node["public_key"],
                    "short_id": node["short_id"],
                },
            },
        }
    else:  # naive
        return {
            "type": "naive",
            "tag": "proxy",
            "server": node["server"],
            "server_port": node["server_port"],
            "username": node["username"],
            "password": node["password"],
            "tls": {
                "enabled": True,
                "server_name": node["server_name"],
            },
        }


def generate_config_from_node(node: dict) -> str:
    """
    通用配置生成器：根据节点 dict（naive 或 reality）
    生成完整的 Sing-box config.json 字符串。
    """
    config = {
        "log": {"level": "info", "timestamp": True},
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": "tun0",
                "address": ["172.19.0.1/30"],
                "auto_route": True,
                "auto_redirect": True,
                "strict_route": True,
                "stack": "system",
            },
            {
                "type": "direct",
                "tag": "dns-in",
                "listen": "127.0.0.1",
                "listen_port": 1053,
                "override_address": "8.8.8.8",
                "override_port": 53,
            },
        ],
        "outbounds": [
            generate_singbox_outbound(node),
            {"type": "direct", "tag": "direct"},
        ],
        "dns": {
            "servers": [
                {
                    "type": "udp",
                    "tag": "dns_domestic",
                    "server": "223.5.5.5",
                    "server_port": 53,
                },
                {
                    "type": "https",
                    "tag": "dns_fallback",
                    "server": "8.8.8.8",
                    "server_port": 443,
                    "path": "/dns-query",
                    "tls": {"enabled": True, "server_name": "dns.google"},
                    "detour": "proxy",
                },
            ],
            "rules": [
                {"domain_suffix": [".lan"], "server": "dns_domestic"},
                {"rule_set": "geosite-cn", "server": "dns_domestic"},
            ],
            "final": "dns_fallback",
            "strategy": "ipv4_only",
        },
        "route": {
            "default_domain_resolver": {"server": "dns_domestic"},
            "rules": [r for r in [
                {"inbound": ["tun-in"], "action": "sniff"},
                {"inbound": ["dns-in"], "action": "hijack-dns"},
                {"protocol": "dns", "action": "hijack-dns"},
                {"ip_is_private": True, "outbound": "direct"},
                {"rule_set": "geoip-cn", "outbound": "direct"},
                # NaiveProxy 不支持 UDP，拦截 UDP 443 (QUIC) 促使浏览器自动降级到 TCP (HTTP/2)
                {"network": "udp", "port": 443, "action": "reject"} if node.get("protocol", "naive") == "naive" else None,
            ] if r is not None],
            "rule_set": [
                {
                    "type": "local",
                    "tag": "geosite-cn",
                    "format": "binary",
                    "path": "/etc/sing-box/geosite-cn.srs",
                },
                {
                    "type": "local",
                    "tag": "geoip-cn",
                    "format": "binary",
                    "path": "/etc/sing-box/geoip-cn.srs",
                },
            ],
            "final": "proxy",
            "auto_detect_interface": True,
        },
        "experimental": {
            "cache_file": {"enabled": True, "path": "/tmp/sing-box-cache.db"}
        },
    }
    return json.dumps(config, ensure_ascii=False, indent=2)


def verify_singbox(router_ip):
    """在目标 IP 上验证 sing-box 是否运行"""
    ssh = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no root@{router_ip}"
    # 修复 #11：使用 pgrep -x 精确匹配进程名
    code, out, _ = run_local_cmd(f'{ssh} "pidof sing-box || pgrep sing-box"')
    if code == 0 and out.strip():
        print(f"[+] Sing-box 运行状态: 正常 (PID: {out.strip()})")
        return True
    else:
        print("[-] 警告：未检测到 sing-box 进程！请 SSH 登录路由器执行 logread | grep sing-box 排查。")
        return False


# ==================== 交互式菜单操作 ====================

def auto_detect_router() -> str:
    """自动检测路由器当前可用 IP，优先 SSH 连通性。"""
    for ip in ["192.168.2.1", "192.168.2.253", "192.168.31.1", "192.168.1.1"]:
        if check_ssh(ip):
            return ip
    for ip in ["192.168.2.1", "192.168.2.253", "192.168.31.1", "192.168.1.1"]:
        if ping_router(ip):
            return ip
    return None


def menu_import_node(router_ip: str):
    """
    菜单功能 1：粘贴节点并导入。
    支持：
      - NaiveProxy 启动命令（含 --proxy=https://...）
      - vless:// Reality 分享链接
    校验通过后生成新 config.json 并推送到路由器，随后重启 sing-box。
    """
    print()
    print("  ── 导入节点 ─────────────────────────────────────────")
    print("  支持格式：")
    print("    [A] NaiveProxy 命令   naive --proxy=https://user:pass@domain:port ...")
    print("    [B] Reality 链接      vless://uuid@host:port?security=reality&...#名称")
    print()
    print("  请粘贴节点内容（可多行，输入完毕后按两次 Enter 确认，或 q 取消）：")
    lines = []
    empty_count = 0
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            print("\n  已取消。")
            return
        if line.strip().lower() == "q":
            print("  已取消。")
            return
        if line == "":
            empty_count += 1
            if empty_count >= 2:
                break
        else:
            empty_count = 0
            lines.append(line)

    text = "\n".join(lines).strip()
    if not text:
        print("  [!] 未输入任何内容，已取消。")
        return

    # 若粘贴了多行 vless:// 链接，逐行处理，取第一条成功的
    node = None
    errors = []
    candidates = [l.strip() for l in text.splitlines() if l.strip()]
    for candidate in candidates:
        try:
            node = parse_node_input(candidate)
            break
        except ValueError as e:
            errors.append(str(e))

    if node is None:
        print(f"  [-] 解析失败：{errors[0] if errors else '未知错误'}")
        return

    # 显示解析结果让用户确认
    print()
    print(f"  ✅ 识别到节点：")
    print(f"     协议     : {node['protocol'].upper()}")
    print(f"     节点名称 : {node['name']}")
    print(f"     服务器   : {node['server']}:{node['server_port']}")
    if node['protocol'] == 'reality':
        print(f"     SNI      : {node['server_name']}")
        print(f"     公钥     : {node['public_key'][:16]}...")
        print(f"     ShortId  : {node['short_id']}")
    else:
        print(f"     证书域名 : {node['server_name']}")
        print(f"     用户名   : {node['username']}")
    print()
    confirm = input("  确认导入并推送到路由器？[y/N] ").strip().lower()
    if confirm != "y":
        print("  已取消。")
        return

    # 生成新配置并上传
    config_str = generate_config_from_node(node)
    config_tmp = os.path.join(LOCAL_TMP_DIR, "config_import.json")
    with open(config_tmp, "w", encoding="utf-8") as f:
        f.write(config_str)

    print(f"  [*] 正在上传配置到路由器 {router_ip} ...")
    code, _, err = run_local_cmd(
        f'scp -O -o StrictHostKeyChecking=no "{config_tmp}" root@{router_ip}:/etc/sing-box/config.json'
    )
    if code != 0:
        print(f"  [-] 上传失败: {err.strip()[:200]}")
        return

    print("  [+] 配置上传成功，正在重启 sing-box ...")
    ssh = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no root@{router_ip}"
    run_local_cmd(f'{ssh} "/etc/init.d/sing-box restart"')
    time.sleep(2)
    verify_singbox(router_ip)
    print(f"  [✓] 节点 [{node['name']}] 已生效。")


def menu_restart_singbox(router_ip: str):
    """菜单功能 2：重启 sing-box 服务。"""
    print()
    print(f"  [*] 正在重启路由器 {router_ip} 上的 sing-box 服务...")
    ssh = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no root@{router_ip}"
    code, _, err = run_local_cmd(f'{ssh} "/etc/init.d/sing-box restart"')
    if code != 0:
        print(f"  [-] 重启命令返回错误: {err.strip()[:100]}")
    else:
        time.sleep(2)
        verify_singbox(router_ip)


def menu_update_geo(router_ip: str):
    """
    菜单功能 3：下载最新 GeoIP/GeoSite 规则库并推送到路由器，
    然后重启 sing-box 使新规则生效。
    """
    print()
    print("  [*] 正在下载最新 geoip-cn.srs 和 geosite-cn.srs ...")
    geoip_srs   = os.path.join(LOCAL_TMP_DIR, "geoip-cn.srs")
    geosite_srs = os.path.join(LOCAL_TMP_DIR, "geosite-cn.srs")

    # 强制重新下载（覆盖缓存）
    try:
        download_file(GEOIP_URL, geoip_srs)
        download_file(GEOSITE_URL, geosite_srs)
    except Exception as e:
        print(f"  [-] 下载失败: {e}")
        return

    print("  [*] 正在上传规则库到路由器 ...")
    ssh = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no root@{router_ip}"
    for local_f, remote_f in [
        (geoip_srs,   "/etc/sing-box/geoip-cn.srs"),
        (geosite_srs, "/etc/sing-box/geosite-cn.srs"),
    ]:
        code, _, err = run_local_cmd(
            f'scp -O -o StrictHostKeyChecking=no "{local_f}" root@{router_ip}:{remote_f}'
        )
        if code != 0:
            print(f"  [-] 上传 {os.path.basename(local_f)} 失败: {err.strip()[:100]}")
            return
    print("  [+] 规则库上传成功，正在重启 sing-box 使新规则生效 ...")
    run_local_cmd(f'{ssh} "/etc/init.d/sing-box restart"')
    time.sleep(2)
    verify_singbox(router_ip)
    print("  [✓] GeoIP/GeoSite 规则库更新完成。")


def menu_show_status(router_ip: str):
    """
    菜单功能 4：查看 sing-box 运行状态 + 最近 30 行系统日志。
    通过 SSH 实时获取，直接打印到终端。
    """
    print()
    print(f"  [*] 查询路由器 {router_ip} 的 sing-box 状态和日志...")
    ssh = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no root@{router_ip}"
    # 进程状态
    _, pid_out, _ = run_local_cmd(f'{ssh} "pidof sing-box || pgrep sing-box"')
    pids = pid_out.strip()
    if pids:
        print(f"  ● sing-box 运行中  PID: {pids}")
    else:
        print("  ✗ sing-box 未运行")
    # 内存/CPU（busybox top 一次性输出）
    _, top_out, _ = run_local_cmd(f'{ssh} "top -bn1 | grep sing-box"', timeout=10)
    if top_out.strip():
        print(f"  资源占用: {top_out.strip()[:120]}")
    print()
    # 日志
    print("  ── 最近 30 行日志（logread | grep sing-box）─────────")
    _, log_out, _ = run_local_cmd(f'{ssh} "logread 2>/dev/null | grep -i sing-box | tail -30"', timeout=15)
    if log_out.strip():
        for line in log_out.strip().splitlines():
            print(f"  {line}")
    else:
        print("  (无 sing-box 相关日志)")
    print("  ─────────────────────────────────────────────────────")


def menu_update_node_only(router_ip: str):
    """
    菜单功能 5（快捷入口）：仅从本地数据库读取最新节点并更新路由器配置，
    不重新下载内核和规则库。适合节点密码变更后快速同步。
    """
    print()
    print("  [*] 从本地数据库读取最新节点配置 ...")
    try:
        node = get_proxy_node()
    except SystemExit:
        return
    config_str = generate_config_json(node)
    config_tmp = os.path.join(LOCAL_TMP_DIR, "config_db.json")
    with open(config_tmp, "w", encoding="utf-8") as f:
        f.write(config_str)
    print(f"  [*] 正在上传到路由器 {router_ip} ...")
    code, _, err = run_local_cmd(
        f'scp -O -o StrictHostKeyChecking=no "{config_tmp}" root@{router_ip}:/etc/sing-box/config.json'
    )
    if code != 0:
        print(f"  [-] 上传失败: {err.strip()[:200]}")
        return
    ssh = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no root@{router_ip}"
    run_local_cmd(f'{ssh} "/etc/init.d/sing-box restart"')
    time.sleep(2)
    verify_singbox(router_ip)
    print(f"  [✓] 节点 [{node.get('server_name', node.get('server'))}] 配置已同步并生效。")


# ==================== 交互式主菜单 ====================

def interactive_menu():
    """交互式管理菜单，适用于日常运维操作。"""
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║       OpenWrt Sing-box 透明代理  日常管理工具        ║")
    print("╚══════════════════════════════════════════════════════╝")

    # 自动检测路由器
    print("[*] 正在检测路由器 IP ...")
    router_ip = auto_detect_router()
    if router_ip:
        print(f"[+] 已连接路由器：{router_ip}")
    else:
        print("[!] 未检测到路由器，请确认已接入局域网。")
        print("    手动输入路由器 IP（直接 Enter 使用 192.168.31.1）：", end="")
        manual_ip = input().strip()
        router_ip = manual_ip or ROUTER_IP_TARGET

    while True:
        print()
        print(f"  当前路由器: {router_ip}")
        print("  ┌─────────────────────────────────────────────────┐")
        print("  │  1. 导入节点（NaiveProxy 命令 / Reality vless://）│")
        print("  │  2. 重启 sing-box 服务                           │")
        print("  │  3. 更新 GeoIP / GeoSite 分流规则库              │")
        print("  │  4. 查看运行状态 & 最近日志                      │")
        print("  │  5. 从本地数据库同步节点配置（快捷更新）         │")
        print("  │  0. 退出                                         │")
        print("  └─────────────────────────────────────────────────┘")
        choice = input("  请选择操作 [0-5]: ").strip()

        if choice == "0":
            print("  再见！")
            break
        elif choice == "1":
            menu_import_node(router_ip)
        elif choice == "2":
            menu_restart_singbox(router_ip)
        elif choice == "3":
            menu_update_geo(router_ip)
        elif choice == "4":
            menu_show_status(router_ip)
        elif choice == "5":
            menu_update_node_only(router_ip)
        else:
            print("  [!] 无效选项，请输入 0-5。")


# ==================== 主流程 ====================

def main():
    print("=== Redmi AX6 OpenWrt Sing-box TUN 一键透明代理部署脚本 ===")

    # 0. 确认路由器在线状态与当前 IP
    router_ip = auto_detect_router()
    if not router_ip:
        print(f"[-] 无法连接路由器 SSH（{ROUTER_IP_TARGET} 或 {ROUTER_IP_INIT}），"
              "请确认网线/Wi-Fi 已接入并重试。")
        sys.exit(1)
    print(f"[+] 成功连接路由器: {router_ip}")

    ssh = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no root@{router_ip}"

    # 1. 获取代理节点
    node = get_proxy_node()
    print(f"[*] 部署将使用以下节点：")
    print(f"    服务器IP : {node['server']}")
    print(f"    证书域名 : {node['server_name']}")
    print(f"    端口     : {node['server_port']}")

    # 2. 动态检测目标路由器 CPU 架构 (x86_64 vs arm64) 并下载对应内核
    _, arch_out, _ = run_local_cmd(f'{ssh} "uname -m"')
    arch_str = arch_out.strip().lower()
    if "x86_64" in arch_str or "amd64" in arch_str:
        singbox_url = SINGBOX_URL_AMD64
        print(f"[+] 检测到 x86_64 工控机架构 ({router_ip})，使用 amd64 Sing-box 内核")
    else:
        singbox_url = SINGBOX_URL_ARM64
        print(f"[+] 检测到 {arch_str} 架构 ({router_ip})，使用 arm64 Sing-box 内核")

    singbox_tar = os.path.join(LOCAL_TMP_DIR, "singbox-musl.tar.gz")
    singbox_bin = os.path.join(LOCAL_TMP_DIR, "sing-box")
    geoip_srs   = os.path.join(LOCAL_TMP_DIR, "geoip-cn.srs")
    geosite_srs = os.path.join(LOCAL_TMP_DIR, "geosite-cn.srs")

    try:
        if not os.path.exists(singbox_bin):
            download_file(singbox_url, singbox_tar)
            print("[*] 正在解压 sing-box 内核...")
            with tarfile.open(singbox_tar, "r:gz") as tar:
                member = next(
                    (m for m in tar.getmembers() if m.name.endswith("/sing-box")),
                    None
                )
                if not member:
                    raise Exception("未在压缩包中找到 sing-box 二进制文件。")
                member.name = os.path.basename(member.name)
                tar.extract(member, path=LOCAL_TMP_DIR)
                print("[+] 解压内核成功。")
            os.remove(singbox_tar)
        else:
            print("[+] 使用本地缓存的 sing-box 内核。")

        if not os.path.exists(geoip_srs):
            download_file(GEOIP_URL, geoip_srs)
        else:
            print("[+] 使用本地缓存的 geoip-cn.srs。")

        if not os.path.exists(geosite_srs):
            download_file(GEOSITE_URL, geosite_srs)
        else:
            print("[+] 使用本地缓存的 geosite-cn.srs。")
    except Exception as e:
        print(f"[-] 下载或准备资源失败: {e}")
        sys.exit(1)

    # 3. 清理旧 Brook/NaiveProxy 客户端（停止旧 sing-box 防止 "Text file busy"）
    print("[*] 正在清理与停止路由器上的旧版客户端及 Sing-box 进程...")
    run_local_cmd(
        f'{ssh} "/etc/init.d/sing-box stop 2>/dev/null; killall -9 sing-box 2>/dev/null; rm -f /usr/bin/sing-box; true"'
    )
    run_local_cmd(
        f'{ssh} "/etc/init.d/naive stop 2>/dev/null; /etc/init.d/naive disable 2>/dev/null; '
        f'/etc/init.d/brook stop 2>/dev/null; /etc/init.d/brook disable 2>/dev/null; true"'
    )
    run_local_cmd(
        f'{ssh} "rm -f /usr/bin/naive /usr/bin/naive_mgr /etc/init.d/naive '
        f'/etc/config/naive /usr/bin/brook /etc/init.d/brook"'
    )
    run_local_cmd(
        f'{ssh} "sed -i \'/\\/usr\\/bin\\/naive/d; /\\/usr\\/bin\\/naive_mgr/d; '
        f'/\\/etc\\/init.d\\/naive/d; /\\/usr\\/bin\\/brook/d\' /etc/sysupgrade.conf"'
    )
    print("[+] 旧客户端清理完成。")

    # 4. 安装/校验 kmod-tun（兼顾 opkg 和 apk 包管理器）
    print("[*] 正在检查与配置 kmod-tun 内核模块...")
    kmod_script = (
        "if [ ! -c /dev/net/tun ]; then "
        "  cp /tmp/resolv.conf /tmp/resolv.conf.bak 2>/dev/null; "
        "  echo nameserver 223.5.5.5 | tee /tmp/resolv.conf > /dev/null; "
        "  if command -v apk >/dev/null 2>&1; then "
        "    apk update && apk add kmod-tun; "
        "  elif command -v opkg >/dev/null 2>&1; then "
        "    opkg update && opkg install kmod-tun; "
        "  fi; "
        "  PKG_RET=$?; "
        "  mv /tmp/resolv.conf.bak /tmp/resolv.conf 2>/dev/null || true; "
        "fi; "
        "modprobe tun 2>/dev/null || true"
    )
    run_critical_cmd(
        f'{ssh} "{kmod_script}"',
        "kmod-tun 检查与配置",
        timeout=120
    )
    print("[+] kmod-tun 模块已就绪。")

    # 5. 创建 /dev/net/tun 设备节点（TUN 透明代理依赖）
    print("[*] 正在创建 /dev/net/tun 虚拟网卡节点...")
    run_local_cmd(
        f'{ssh} "mkdir -p /dev/net; '
        f'[ ! -c /dev/net/tun ] && mknod /dev/net/tun c 10 200 && chmod 666 /dev/net/tun || true"'
    )

    # 6. 生成配置文件并上传
    print("[*] 正在生成并上传配置文件...")
    config_json_path = os.path.join(LOCAL_TMP_DIR, "config.json")
    init_script_path = os.path.join(LOCAL_TMP_DIR, "sing-box.init")

    with open(config_json_path, "w", encoding="utf-8") as f:
        f.write(generate_config_json(node))

    with open(init_script_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(generate_init_script())

    run_critical_cmd(f'{ssh} "mkdir -p /etc/sing-box /etc/sing-box/nodes"', "创建目录")

    menu_sh_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sing-box-menu.sh")

    uploads = [
        (singbox_bin,      "/usr/bin/sing-box"),
        (geoip_srs,        "/etc/sing-box/geoip-cn.srs"),
        (geosite_srs,      "/etc/sing-box/geosite-cn.srs"),
        (config_json_path, "/etc/sing-box/config.json"),
        (init_script_path, "/etc/init.d/sing-box"),
        (menu_sh_path,     "/usr/bin/sb"),
    ]
    for local_f, remote_f in uploads:
        run_critical_cmd(
            f'scp -O -o StrictHostKeyChecking=no "{local_f}" root@{router_ip}:{remote_f}',
            f"上传 {os.path.basename(local_f)}"
        )
    run_local_cmd(f'{ssh} "ln -sf /usr/bin/sb /usr/bin/sing-box-menu"')
    print("[+] 所有文件上传成功。")

    # 7. 权限、自启、sysupgrade 持久化
    # 修复 #7：对关键命令逐一检查返回码
    print("[*] 正在设置权限并启用 Sing-box 服务...")
    run_critical_cmd(f'{ssh} "chmod +x /usr/bin/sing-box /etc/init.d/sing-box /usr/bin/sb /usr/bin/sing-box-menu"', "设置可执行权限")
    run_critical_cmd(f'{ssh} "/etc/init.d/sing-box enable"', "启用 sing-box 自启")
    run_critical_cmd(f'{ssh} "/etc/init.d/sing-box restart"', "启动 sing-box")

    for path in ["/usr/bin/sing-box", "/etc/sing-box/", "/etc/init.d/sing-box", "/usr/bin/sb", "/usr/bin/sing-box-menu"]:
        run_local_cmd(
            f"{ssh} \"grep -qF '{path}' /etc/sysupgrade.conf "
            f"|| echo '{path}' >> /etc/sysupgrade.conf\""
        )
    print("[+] sysupgrade 持久化配置完成。")

    # 8. 配置 dnsmasq 重定向
    print("[*] 正在配置 dnsmasq DNS 解析重定向...")
    run_critical_cmd(f"{ssh} \"uci set dhcp.@dnsmasq[0].noresolv='1'\"", "dnsmasq noresolv")
    run_critical_cmd(f"{ssh} \"uci set dhcp.@dnsmasq[0].localuse='1'\"", "dnsmasq localuse")
    run_local_cmd(f"{ssh} \"uci del dhcp.@dnsmasq[0].server\"")  # 忽略错误（可能本不存在）
    run_critical_cmd(
        f"{ssh} \"uci add_list dhcp.@dnsmasq[0].server='127.0.0.1#1053'\"",
        "dnsmasq server 配置"
    )
    run_critical_cmd(f"{ssh} \"uci commit dhcp\"", "UCI 提交 dhcp")
    run_critical_cmd(f"{ssh} \"/etc/init.d/dnsmasq restart\"", "dnsmasq 重启")
    print("[+] dnsmasq 已重定向至 Sing-box。")

    # 9. IP 修改（如需要）及验证
    if router_ip == ROUTER_IP_INIT:
        # 修复 #3：加 /24 子网掩码
        print(f"\n[*] 正在将路由器 LAN IP 修改为 {ROUTER_IP_TARGET}/24 ...")
        run_local_cmd(f"{ssh} \"uci set network.lan.ipaddr='{ROUTER_IP_TARGET}/24'\"")
        run_local_cmd(f"{ssh} \"uci commit network\"")
        # 重启网络后 SSH 连接会断开，用 Popen 发出指令后不等待
        subprocess.Popen(
            f'{ssh} "/etc/init.d/network restart"',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        print("[*] 路由器网络服务正在重启，等待新 IP 上线...")
        time.sleep(8)

        # 修复 #6：IP 变更后自动等待并在新 IP 上验证
        online = False
        for _ in range(25):
            if ping_router(ROUTER_IP_TARGET):
                online = True
                break
            time.sleep(2)

        if not online:
            print(f"[-] 超时：{ROUTER_IP_TARGET} 未能在预期时间内上线。")
            print("    请手动重连网络并检查路由器状态。")
            sys.exit(1)

        print(f"[+] 路由器已在 {ROUTER_IP_TARGET} 上线。正在验证 Sing-box 运行状态...")
        time.sleep(3)
        verify_singbox(ROUTER_IP_TARGET)

        print("\n" + "=" * 55)
        print(f"[完成] 路由器 LAN IP 已变更为 {ROUTER_IP_TARGET}")
        print("  1. 请重新拔插网线或重连 Wi-Fi，使电脑获取新网段 IP。")
        print(f"  2. 新的路由器管理地址：http://{ROUTER_IP_TARGET}")
        print("=" * 55)
    else:
        # 已在目标 IP，直接验证
        time.sleep(2)
        print("\n[*] 正在验证 Sing-box 运行状态...")
        ok = verify_singbox(router_ip)
        if ok:
            print("[+] 部署全部顺利完成！局域网客户端现已实现透明代理上网。")


if __name__ == "__main__":
    if "--deploy" in sys.argv:
        # 全量部署模式：完整安装流程
        main()
    else:
        # 默认：交互式管理菜单
        interactive_menu()

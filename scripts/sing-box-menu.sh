#!/bin/sh
# ==============================================================================
#  OpenWrt Sing-box 本地控制台日常管理工具 (sing-box-menu / sb)
#  无需 Python / SQLite，完全基于 OpenWrt 原生 ash Shell
# ==============================================================================

NODES_DIR="/etc/sing-box/nodes"
ACTIVE_FILE="/etc/sing-box/active_node.name"
CONFIG_FILE="/etc/sing-box/config.json"
mkdir -p "$NODES_DIR"

# 自动创建 GLibc 动态解释器软链接（防止 OpenWrt Musl 环境下 sing-box: not found 报错）
if [ ! -e /lib64/ld-linux-x86-64.so.2 ] && [ -f /lib/ld-musl-x86_64.so.1 ]; then
    mkdir -p /lib64
    ln -sf /lib/ld-musl-x86_64.so.1 /lib64/ld-linux-x86-64.so.2 2>/dev/null || true
fi

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

url_decode() {
    local str="$1"
    str="$(echo "$str" | tr '+' ' ')"
    printf '%b' "$(echo "$str" | sed 's/%/\\x/g')" 2>/dev/null || echo "$str"
}

json_escape() {
    local str="$1"
    printf '%s' "$str" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g' | tr -d '\r\n'
}

get_param() {
    local query="$1"
    local key="$2"
    echo "$query" | tr '&' '\n' | grep "^${key}=" | cut -d'=' -f2-
}

# POSIX 安全替代：获取第 N 个节点配置文件路径（消除 eval 动态变量）
get_nth_node_file() {
    local n="$1"
    ls -1 "$NODES_DIR"/*.json 2>/dev/null | sed -n "${n}p"
}

# 从 JSON 提取节点元数据（使用 OpenWrt 原生 jsonfilter 或 grep 降级）
get_node_info() {
    local file="$1"
    if command -v jsonfilter >/dev/null 2>&1; then
        INFO_TYPE="$(jsonfilter -i "$file" -e '@.outbounds[0].type' 2>/dev/null)"
        INFO_SERVER="$(jsonfilter -i "$file" -e '@.outbounds[0].server' 2>/dev/null)"
        INFO_PORT="$(jsonfilter -i "$file" -e '@.outbounds[0].server_port' 2>/dev/null)"
        INFO_SNI="$(jsonfilter -i "$file" -e '@.outbounds[0].tls.server_name' 2>/dev/null)"
    else
        INFO_TYPE="$(grep -o '"type": "[^"]*"' "$file" | head -2 | tail -1 | cut -d'"' -f4)"
        INFO_SERVER="$(grep -o '"server": "[^"]*"' "$file" | head -1 | cut -d'"' -f4)"
        INFO_PORT="$(grep -o '"server_port": [0-9]*' "$file" | head -1 | awk '{print $2}')"
        INFO_SNI="$(grep -o '"server_name": "[^"]*"' "$file" | head -1 | cut -d'"' -f4)"
    fi

    if [ "$INFO_TYPE" = "vless" ]; then
        PROTO_LABEL="VLESS/Reality"
    elif [ "$INFO_TYPE" = "naive" ]; then
        PROTO_LABEL="NaiveProxy"
    else
        PROTO_LABEL="${INFO_TYPE:-未知协议}"
    fi
}

print_node_card() {
    local bname="$1"
    local file="$2"
    get_node_info "$file"
    echo -e "${BLUE}┌─────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${BLUE}│${NC}  ${GREEN}节点名称${NC} : $bname"
    echo -e "${BLUE}│${NC}  ${GREEN}协议类型${NC} : ${MAGENTA}$PROTO_LABEL${NC}"
    echo -e "${BLUE}│${NC}  ${GREEN}服务器  ${NC} : $INFO_SERVER:$INFO_PORT"
    echo -e "${BLUE}│${NC}  ${GREEN}SNI 域名${NC} : $INFO_SNI"
    echo -e "${BLUE}└─────────────────────────────────────────────────────────────┘${NC}"
}

# 校验与解析 vless:// Reality URL
parse_vless_url() {
    local url="$1"
    url="$(echo "$url" | tr -d '\r\n ')"
    case "$url" in
        vless://*) ;;
        *) echo "ERR: 非法的 vless:// 链接"; return 1 ;;
    esac

    local name=""
    case "$url" in
        *#*)
            name="${url#*#}"
            name="$(url_decode "$name")"
            url="${url%%#*}"
            ;;
    esac

    local proto_body="${url#vless://}"
    local user_host_port="${proto_body%%?*}"
    local query=""
    case "$proto_body" in
        *\?*) query="${proto_body#*\?}" ;;
    esac

    local uuid="${user_host_port%%@*}"
    local host_port="${user_host_port#*@}"
    local server="${host_port%%:*}"
    local port="${host_port#*:}"

    local security="$(get_param "$query" "security")"
    if [ "$security" != "reality" ]; then
        echo "ERR: 仅支持 security=reality 协议 (当前: $security)"
        return 1
    fi

    local pbk="$(get_param "$query" "pbk")"
    local sid="$(get_param "$query" "sid")"
    local sni="$(get_param "$query" "sni")"
    local flow="$(get_param "$query" "flow")"
    local fp="$(get_param "$query" "fp")"

    [ -z "$flow" ] && flow="xtls-rprx-vision"
    [ -z "$fp" ] && fp="chrome"

    if [ -z "$uuid" ] || [ -z "$server" ] || [ -z "$port" ] || [ -z "$pbk" ] || [ -z "$sid" ] || [ -z "$sni" ]; then
        echo "ERR: Reality 节点参数不完整 (缺少 UUID/Server/Port/pbk/sid/sni)"
        return 1
    fi

    [ -z "$name" ] && name="Reality_${server}_${port}"
    name="$(echo "$name" | tr -cd 'a-zA-Z0-9_-')"
    [ -z "$name" ] && name="Reality_${port}"

    NODE_NAME="$name"
    NODE_TYPE="reality"
    NODE_SERVER="$server"
    NODE_PORT="$port"
    NODE_UUID="$uuid"
    NODE_FLOW="$flow"
    NODE_FP="$fp"
    NODE_SNI="$sni"
    NODE_PBK="$pbk"
    NODE_SID="$sid"
    return 0
}

# 校验与解析 NaiveProxy 启动命令
parse_naive_cmd() {
    local cmd="$1"
    cmd="$(echo "$cmd" | tr -d '\r\n')"
    case "$cmd" in
        *--proxy=*) ;;
        *) echo "ERR: 未找到 --proxy= 参数"; return 1 ;;
    esac

    local proxy_val="$(echo "$cmd" | tr ' ' '\n' | grep '^--proxy=' | cut -d'=' -f2-)"
    local rules_val="$(echo "$cmd" | tr ' ' '\n' | grep '^--host-resolver-rules=' | cut -d'=' -f2- | tr -d '"' | tr -d "'")"

    local body="${proxy_val#*://}"
    local userpass="${body%%@*}"
    local hostport="${body#*@}"

    local user="${userpass%%:*}"
    local pass="${userpass#*:}"
    local domain="${hostport%%:*}"
    local port="${hostport#*:}"

    local server="$domain"
    if [ -n "$rules_val" ]; then
        local map_ip="$(echo "$rules_val" | awk '{print $3}')"
        [ -n "$map_ip" ] && server="$map_ip"
    fi

    if [ -z "$user" ] || [ -z "$pass" ] || [ -z "$domain" ] || [ -z "$port" ]; then
        echo "ERR: NaiveProxy 参数不完整"
        return 1
    fi

    local name="Naive_${domain}_${port}"
    name="$(echo "$name" | tr -cd 'a-zA-Z0-9_-')"

    NODE_NAME="$name"
    NODE_TYPE="naive"
    NODE_SERVER="$server"
    NODE_PORT="$port"
    NODE_USER="$user"
    NODE_PASS="$pass"
    NODE_SNI="$domain"
    return 0
}

generate_config_json() {
    local type="$1"
    local outbound_block=""
    local udp_reject_rule=""

    local server_esc="$(json_escape "$NODE_SERVER")"
    local sni_esc="$(json_escape "$NODE_SNI")"
    local port_esc="$(json_escape "$NODE_PORT")"

    if [ "$type" = "reality" ]; then
        local uuid_esc="$(json_escape "$NODE_UUID")"
        local flow_esc="$(json_escape "$NODE_FLOW")"
        local fp_esc="$(json_escape "$NODE_FP")"
        local pbk_esc="$(json_escape "$NODE_PBK")"
        local sid_esc="$(json_escape "$NODE_SID")"

        outbound_block=$(cat <<EOF
    {
      "type": "vless",
      "tag": "proxy",
      "server": "$server_esc",
      "server_port": $port_esc,
      "uuid": "$uuid_esc",
      "flow": "$flow_esc",
      "tls": {
        "enabled": true,
        "server_name": "$sni_esc",
        "utls": {
          "enabled": true,
          "fingerprint": "$fp_esc"
        },
        "reality": {
          "enabled": true,
          "public_key": "$pbk_esc",
          "short_id": "$sid_esc"
        }
      }
    }
EOF
)
    else
        local user_esc="$(json_escape "$NODE_USER")"
        local pass_esc="$(json_escape "$NODE_PASS")"

        # NaiveProxy 不支持 UDP，拦截 UDP 443 (QUIC) 促使浏览器自动回退到 TCP (HTTP/2)
        udp_reject_rule=$(cat <<EOF
      {
        "network": "udp",
        "port": 443,
        "action": "reject"
      },
EOF
)

        outbound_block=$(cat <<EOF
    {
      "type": "naive",
      "tag": "proxy",
      "server": "$server_esc",
      "server_port": $port_esc,
      "username": "$user_esc",
      "password": "$pass_esc",
      "tls": {
        "enabled": true,
        "server_name": "$sni_esc"
      }
    }
EOF
)
    fi

    cat <<EOF
{
  "log": {
    "level": "info",
    "timestamp": true
  },
  "inbounds": [
    {
      "type": "tun",
      "tag": "tun-in",
      "interface_name": "tun0",
      "address": [
        "172.19.0.1/30"
      ],
      "auto_route": true,
      "auto_redirect": true,
      "strict_route": true,
      "stack": "system"
    },
    {
      "type": "direct",
      "tag": "dns-in",
      "listen": "127.0.0.1",
      "listen_port": 1053,
      "override_address": "8.8.8.8",
      "override_port": 53
    }
  ],
  "outbounds": [
$outbound_block,
    {
      "type": "direct",
      "tag": "direct"
    }
  ],
  "dns": {
    "servers": [
      {
        "type": "udp",
        "tag": "dns_domestic",
        "server": "223.5.5.5",
        "server_port": 53
      },
      {
        "type": "https",
        "tag": "dns_fallback",
        "server": "8.8.8.8",
        "server_port": 443,
        "path": "/dns-query",
        "tls": {
          "enabled": true,
          "server_name": "dns.google"
        },
        "detour": "proxy"
      }
    ],
    "rules": [
      {
        "domain_suffix": [
          ".lan"
        ],
        "server": "dns_domestic"
      },
      {
        "rule_set": "geosite-cn",
        "server": "dns_domestic"
      }
    ],
    "final": "dns_fallback",
    "strategy": "ipv4_only"
  },
  "route": {
    "default_domain_resolver": {
      "server": "dns_domestic"
    },
    "rules": [
      {
        "inbound": [
          "tun-in"
        ],
        "action": "sniff"
      },
      {
        "inbound": [
          "dns-in"
        ],
        "action": "hijack-dns"
      },
      {
        "protocol": "dns",
        "action": "hijack-dns"
      },
$udp_reject_rule
      {
        "ip_is_private": true,
        "outbound": "direct"
      },
      {
        "rule_set": "geoip-cn",
        "outbound": "direct"
      }
    ],
    "rule_set": [
      {
        "type": "local",
        "tag": "geosite-cn",
        "format": "binary",
        "path": "/etc/sing-box/geosite-cn.srs"
      },
      {
        "type": "local",
        "tag": "geoip-cn",
        "format": "binary",
        "path": "/etc/sing-box/geoip-cn.srs"
      }
    ],
    "final": "proxy",
    "auto_detect_interface": true
  },
  "experimental": {
    "cache_file": {
      "enabled": true,
      "path": "/tmp/sing-box-cache.db"
    }
  }
}
EOF
}

verify_config_file() {
    local file="$1"
    echo -e "${YELLOW}[*] 正在进行 Sing-box 配置语法校验...${NC}"
    if ! sing-box check -c "$file" >/tmp/sb_check.log 2>&1; then
        echo -e "${RED}[!] 错误：配置语法校验未通过，放弃应用！${NC}"
        echo -e "${RED}详细错误日志:${NC}"
        cat /tmp/sb_check.log
        return 1
    fi
    echo -e "${GREEN}[+] 语法校验通过。${NC}"
    return 0
}

# 菜单 1：粘贴导入节点
menu_import() {
    echo ""
    echo -e "${CYAN}── 导入节点 (OpenWrt 本地解析) ────────────────────${NC}"
    echo "支持格式："
    echo "  [A] NaiveProxy 命令   naive --proxy=https://user:pass@domain:port ..."
    echo "  [B] Reality 链接      vless://uuid@host:port?security=reality&...#名称"
    echo ""
    echo "请粘贴节点内容（粘贴后按回车，输入 q 取消）："
    read -r input_str
    [ "$input_str" = "q" ] && return

    if [ -z "$input_str" ]; then
        echo -e "${RED}[!] 未输入任何内容${NC}"
        return
    fi

    local res=""
    case "$input_str" in
        vless://*)
            res=$(parse_vless_url "$input_str")
            ;;
        *--proxy=*)
            res=$(parse_naive_cmd "$input_str")
            ;;
        *)
            echo -e "${RED}[!] 无法识别的节点类型，必须为 Naive 命令或 vless:// Reality 链接${NC}"
            return
            ;;
    esac

    if [ $? -ne 0 ]; then
        echo -e "${RED}$res${NC}"
        return
    fi

    echo ""
    echo -e "${GREEN}✅ 解析成功！${NC}"
    echo "  默认标识 : $NODE_NAME"
    echo "  协议类型 : $NODE_TYPE"
    echo "  服务器   : $NODE_SERVER:$NODE_PORT"
    echo "  SNI 域名 : $NODE_SNI"

    read -p "给节点起个易记的名称（直接回车使用 '$NODE_NAME'）: " custom_name
    if [ -n "$custom_name" ]; then
        NODE_NAME="$(echo "$custom_name" | tr -cd 'a-zA-Z0-9_-')"
    fi

    local target_file="$NODES_DIR/${NODE_NAME}.json"
    generate_config_json "$NODE_TYPE" > "$target_file"

    if ! verify_config_file "$target_file"; then
        rm -f "$target_file"
        return
    fi

    echo -e "${GREEN}[+] 节点配置已成功保存至: $target_file${NC}"

    read -p "是否立即切换并生效该节点？[Y/n] " sw
    if [ "$sw" != "n" ] && [ "$sw" != "N" ]; then
        cp "$target_file" "$CONFIG_FILE"
        echo "$NODE_NAME" > "$ACTIVE_FILE"
        print_node_card "$NODE_NAME" "$target_file"
        echo -e "${YELLOW}[*] 正在重启 sing-box...${NC}"
        /etc/init.d/sing-box restart
        sleep 2
        echo -e "${GREEN}[✓] 节点 [$NODE_NAME] 已生效！${NC}"
    fi
}

# 菜单 2：节点列表 & 切换 (彻底消除 eval)
menu_list_and_switch() {
    echo ""
    echo -e "${CYAN}── 保存的节点列表 & 切换 ──────────────────────────────${NC}"
    local active_name=""
    [ -f "$ACTIVE_FILE" ] && active_name="$(cat "$ACTIVE_FILE")"

    local files=$(ls -1 "$NODES_DIR"/*.json 2>/dev/null)
    if [ -z "$files" ]; then
        echo -e "${YELLOW}[!] 尚无保存的节点，请先选择 [1] 导入新节点。${NC}"
        return
    fi

    local i=1
    for f in $files; do
        local bname="$(basename "$f" .json)"
        get_node_info "$f"
        local tag=""
        if [ "$bname" = "$active_name" ]; then
            tag="${GREEN}[ACTIVE 当前在用]${NC}"
        fi
        echo -e "  [$i] ${CYAN}$bname${NC} ${YELLOW}[$PROTO_LABEL | $INFO_SERVER:$INFO_PORT | SNI: $INFO_SNI]${NC} $tag"
        i=$((i + 1))
    done
    local total=$((i - 1))

    echo ""
    read -p "请输入要切换的节点编号 [1-$total] (按回车返回): " choice
    [ -z "$choice" ] && return

    choice="$(echo "$choice" | tr -cd '0-9')"
    [ -z "$choice" ] && return

    local chosen_path="$(get_nth_node_file "$choice")"
    local chosen_name="$(basename "$chosen_path" .json 2>/dev/null)"

    if [ -z "$chosen_path" ] || [ ! -f "$chosen_path" ]; then
        echo -e "${RED}[!] 无效的选择${NC}"
        return
    fi

    if ! verify_config_file "$chosen_path"; then
        return
    fi

    cp "$chosen_path" "$CONFIG_FILE"
    echo "$chosen_name" > "$ACTIVE_FILE"
    print_node_card "$chosen_name" "$chosen_path"
    echo -e "${YELLOW}[*] 正在切换至 [$chosen_name] 并重启 sing-box...${NC}"
    /etc/init.d/sing-box restart
    sleep 2
    echo -e "${GREEN}[✓] 已成功切至节点 [$chosen_name]！${NC}"
}

# 菜单 3：重启
menu_restart() {
    if ! verify_config_file "$CONFIG_FILE"; then
        return
    fi
    local active_name="默认节点"
    [ -f "$ACTIVE_FILE" ] && active_name="$(cat "$ACTIVE_FILE")"
    print_node_card "$active_name" "$CONFIG_FILE"
    echo -e "${YELLOW}[*] 正在重启 sing-box 服务...${NC}"
    /etc/init.d/sing-box restart
    sleep 2
    local pid="$(pidof sing-box)"
    if [ -n "$pid" ]; then
        echo -e "${GREEN}[+] sing-box 运行正常 (PID: $pid)${NC}"
    else
        echo -e "${RED}[-] 警告: sing-box 启动失败，请查阅日志${NC}"
    fi
}

# 菜单 4：更新分流规则库
menu_update_rules() {
    echo -e "${CYAN}[*] 正在下载最新 GeoIP/GeoSite 规则库...${NC}"
    wget -O /tmp/geoip-cn.srs https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs 2>/dev/null || \
    curl -sSL -o /tmp/geoip-cn.srs https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs

    wget -O /tmp/geosite-cn.srs https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-cn.srs 2>/dev/null || \
    curl -sSL -o /tmp/geosite-cn.srs https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-cn.srs

    if [ -f /tmp/geoip-cn.srs ] && [ -f /tmp/geosite-cn.srs ]; then
        mv /tmp/geoip-cn.srs /etc/sing-box/geoip-cn.srs
        mv /tmp/geosite-cn.srs /etc/sing-box/geosite-cn.srs
        echo -e "${GREEN}[+] 规则库更新成功，正在重启 sing-box...${NC}"
        /etc/init.d/sing-box restart
    else
        echo -e "${RED}[-] 下载规则库失败，请检查路由器外网连接${NC}"
    fi
}

# 菜单 5：日志与状态
menu_status() {
    echo ""
    echo -e "${CYAN}── Sing-box 状态与日志 ──────────────────────────────${NC}"
    local pid="$(pidof sing-box)"
    if [ -n "$pid" ]; then
        echo -e "运行状态: ${GREEN}● 运行中 (PID: $pid)${NC}"
    else
        echo -e "运行状态: ${RED}✗ 未运行${NC}"
    fi
    local active_name="未知"
    [ -f "$ACTIVE_FILE" ] && active_name="$(cat "$ACTIVE_FILE")"
    print_node_card "$active_name" "$CONFIG_FILE"

    echo ""
    echo -e "${YELLOW}最近 25 行日志:${NC}"
    logread 2>/dev/null | grep -i sing-box | tail -n 25
}

# 菜单 6：删除节点 (彻底消除 eval)
menu_delete_node() {
    echo ""
    echo -e "${CYAN}── 删除节点 ─────────────────────────────────────────${NC}"
    local files=$(ls -1 "$NODES_DIR"/*.json 2>/dev/null)
    if [ -z "$files" ]; then
        echo -e "${YELLOW}[!] 尚无节点${NC}"
        return
    fi
    local i=1
    for f in $files; do
        get_node_info "$f"
        echo -e "  [$i] ${CYAN}$(basename "$f" .json)${NC} ${YELLOW}[$PROTO_LABEL | $INFO_SERVER:$INFO_PORT]${NC}"
        i=$((i + 1))
    done
    read -p "请输入要删除的节点编号: " choice
    choice="$(echo "$choice" | tr -cd '0-9')"
    [ -z "$choice" ] && return
    local chosen_del="$(get_nth_node_file "$choice")"
    if [ -n "$chosen_del" ] && [ -f "$chosen_del" ]; then
        rm -f "$chosen_del"
        echo -e "${GREEN}[+] 节点已删除${NC}"
    fi
}

# 主循环
while true; do
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║      OpenWrt Sing-box 本地控制台日常管理工具        ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
    echo "  1. 导入新节点 (NaiveProxy 命令 / Reality vless://)"
    echo "  2. 节点列表 & 切换节点"
    echo "  3. 重启 sing-box 服务"
    echo "  4. 更新 GeoIP / GeoSite 分流规则库"
    echo "  5. 查看运行状态 & 最近日志"
    echo "  6. 删除已保存的节点"
    echo "  0. 退出"
    echo ""
    read -p "请选择操作 [0-6]: " choice
    case "$choice" in
        1) menu_import ;;
        2) menu_list_and_switch ;;
        3) menu_restart ;;
        4) menu_update_rules ;;
        5) menu_status ;;
        6) menu_delete_node ;;
        0) echo "再见！"; exit 0 ;;
        *) echo -e "${RED}[!] 无效选项${NC}" ;;
    esac
done

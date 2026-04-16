# HomeProxy 优化与深度排障总结报告

这是一份关于 J4125 路由器 (ImmortalWrt) 上 HomeProxy 插件从故障到完美运行的排障记录与原理总结。

## 1. 核心问题复现
*   **启动故障**: Sing-box 报告 `unknown transport type: raw`，导致 HomeProxy 守护进程退出。
*   **分流故障**: 在“绕过中国大陆”模式下，国内流量（IP/域名）无法被正确识别，导致所有流量默认走 `main-out`（代理），引起国内访问延迟高。

## 2. 解决方案：`raw` 空协议兼容性修复
*   **故障根源**: 系统生成的配置文件中含有 `"type": "raw"`，这在 Sing-box 1.8.0 之后的版本中不再作为默认允许的空值。
*   **修复逻辑**: 修改 `/etc/homeproxy/scripts/generate_client.uc` 中的 `transport` 对象生成逻辑，增加条件判定：
    ```javascript
    transport: (!isEmpty(node.transport) && node.transport !== 'raw') ? { ... } : null
    ```
*   **效果**: 成功移除了无效的 `raw` 节点，Sing-box 恢复正常启动。

## 3. 解决方案：国内流量路由分流修复
*   **故障根源**: `generate_client.uc` 脚本在生成路由规则时，虽然定义了 `ruleset`，但未在 `config.route.rules` 中 `push` 针对 `geosite-cn` 和 `geoip-cn` 的路由动作。
*   **修复逻辑**: 在 `routing_mode === 'bypass_mainland_china'` 判断块内，手动注入路由指令：
    ```javascript
    push(config.route.rules, { rule_set: 'geosite-cn', action: 'route', outbound: 'direct-out' });
    push(config.route.rules, { rule_set: 'geoip-cn', action: 'route', outbound: 'direct-out' });
    ```
*   **效果**: 通过 `cat /var/run/homeproxy/sing-box-c.json` 确认规则已生效，国内 IP 访问恢复 `direct-out` 直连。

## 4. 持久化与工程化
为了确保在编译新固件后修复依然生效，已将上述 `sed` 修改指令集成至 GitHub Actions 的 `diy-part2.sh` 脚本中：
```bash
# 修改传输协议逻辑
sed -i 's/transport: !isEmpty(node.transport) ? {/transport: (!isEmpty(node.transport) \&\& node.transport !== "raw") ? {/' ...
# 注入路由分流逻辑
sed -i "/outbound: 'direct-out'/a ...push(config.route.rules...)" ...
```

---
**记录时间**: 2026-04-16
**状态**: 已解决 (Resolved)

## 1. 核心工作原理
HomeProxy 在系统中的运行流程如下：
- **配置源 (UCI)**：`/etc/config/homeproxy` 存储了 Web 界面的设置。
- **配置生成器 (uCode)**：位于 `/etc/homeproxy/scripts/generate_client.uc`。这是一个模板文件，负责将 UCI 配置转换为 Sing-box 的 JSON 格式。
- **执行内核 (Sing-box)**：动态生成的 `/var/run/homeproxy/sing-box-c.json` 是真正的运行大脑。

## 2. 三大核心故障与解决方案

### 故障 A：启动即崩溃 (Crash on Startup)
- **原因**：精简版固件缺少 `kmod-tun`、`ip-full`、`curl` 和 `ca-certificates`。
- **解决**：手动安装依赖。
- **持久化建议**：已更新 `openwrt-builder.yml` 编译脚本，确保下次编译时自动包含这些组件。

### 故障 B：DNS 查询异常 (DNS Leaks)
- **原因**：电脑浏览器默认开启了“安全 DNS (DoH)”，绕过了路由器的 DNS 劫持规则。
- **解决**：在浏览器设置中关闭“使用安全 DNS”。

### 故障 C：全局代理/分流失效 (Global Proxy Issue)
- **原因 (最硬核发现)**：`generate_client.uc` 脚本存在逻辑 Bug。当用户选择了主节点（梯子）时，脚本虽然定义了国内地图 (`geoip-cn`)，但**完全漏掉了**将对应规则推送到路由列表的代码。
- **解决**：使用 `sed` 对脚本进行了核心逻辑注入，代码如下：
  ```javascript
  if (routing_mode === 'bypass_mainland_china' && !isEmpty(main_node)) {
      push(config.route.rules, {
          rule_set: 'geosite-cn',
          action: 'route',
          outbound: 'direct-out'
      });
      // ... 等更多逻辑
  }
  ```

## 3. 分流验证方法
1. **浏览器测试**：打开隐身模式，访问 `ip138.com` 显示 ISP 原 IP，访问 Google/YouTube 正常显示梯子 IP。
2. **终端测试**：`curl -v4 ip138.com` 返回值需包含本地公网 IP 信息。

## 4. 维护建议
> [!IMPORTANT]
> **补丁持久性**：由于补丁是直接打在 `/etc/homeproxy/scripts/` 下的脚本里的，它会持续生效。但重刷固件或升级插件版本会覆盖此修改，届时需重新运行 `sed` 补丁。

---
*文档由 Antigravity AI 整理归纳时间：2026-04-13*

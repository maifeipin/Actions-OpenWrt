# J4125 主路由 + 物理2.5G交换机 + BE6500 AP 终极方案
> 该方案为家庭旗舰级零缺陷组网架构（无泄露 + IPv4/IPv6 双栈全网代理管控 + 米家智能家居完美正常 + 核心硬件零过载）

## 一、最终拓扑（唯一正确、行业标准、无任何妥协）

```text
光猫（桥接模式）
   ↓ [eth0 作为 WAN 口]
J4125 OpenWrt（主路由：PPPoE 拨号 + IPv6 PD获取 + 全局网关 + 双栈代理）
   ↓ [eth1 单口 LAN 接物理交换机]
2.5G 物理交换机（NAS / PC / 主机 全部插这里，原生线速硬件交换）
   ↓
BE6500（纯 AP 模式/有线中继，关闭 DHCP / 关闭 NAT / 关闭路由）

所有物理设备和 Wi-Fi 设备同一网段：192.168.2.0/24
```

## 二、角色分工（专业、干净、无冲突）

1. **J4125 OpenWrt (中枢大脑)**
   - WAN：eth0（负责 PPPoE 拨号）
   - LAN：eth1（单口单线，不开启软桥接，彻底释放 CPU 和中断资源）
   - 全局网关：192.168.2.253
   - 全局 DNS：由它自身负责防污染净化
   - 网络栈：完美接管分配 IPv4 + IPv6
   - 服务层：**HomeProxy** (基于 Sing-box 内核) 进行全局代理，完美契合 VLESS-REALITY 等现代防封锁协议。
   - 管控层：负责流控 / 监控 / 家长控制。处理纯计算业务，极度发挥 x86 核心算力。

2. **硬件 2.5G 交换机 (数据立交桥)**
   - 纯二层无差别极速转发。
   - 不消耗主路由 J4125 的任何性能。内网即使跑爆 2.5G (比如 NAS 与 PC 传文件)，也不会影响科学代理或外网速度。

3. **BE6500 (无线发射炮)**
   - 访问地址：192.168.2.1
   - 工作机制：极简。关闭内一切涉及到地址发放与路由调度的功能（无 DHCP / NAT / IPv6 RA）。
   - 角色：仅凭借其优秀的无线天线发射覆盖全家，做个老实的打工仔。

## 三、架构的优势体现

1. **绝对无 IPv6 泄露跳 ping**：HomeProxy 的现代 nftables 劫持完美统合双栈，Happy Eyeballs 极速首跳命中。
2. **极简低耗**：剔除臃肿的旧插件，拥抱轻量化 Sing-box，内存占用极低。
3. **软硬件各司其职**：消除 Linux 内核软桥接，物理流量交给物理交换。
4. **单广播域 L2 互通**：米家 APP 控制全屋智能设备天生完美无缝响应。

---

## 四、J4125 最终核心配置代码（防断网，防冲突）

### 4.1 网络底层配置（/etc/config/network）

```text
config interface 'wan'
    option ifname 'eth0'
    option proto 'pppoe'
    option username '在这里填入宽带账号'
    option password '在这里填入宽带密码'
    option ipv6 'auto'

# 绝对不添加无意义的 bridge 模式和错误的 0 路由
config interface 'lan'
    option ifname 'eth1'
    option proto 'static'
    option ipaddr '192.168.2.253'
    option netmask '255.255.255.0'
    option ip6assign '64'
```

### 4.2 DHCP 与网关分配（/etc/config/dhcp）

```text
config dnsmasq
    option domainneeded '1'
    option boguspriv '1'
    option localise_queries '1'
    option expandhosts '1'
    option authoritative '1'
    option readethers '1'
    option leasefile '/tmp/dhcp.leases'
    option resolvfile '/tmp/resolv.conf.d/resolv.conf.auto'

# 统一化下发方案
config dhcp 'lan'
    option interface 'lan'
    option start '100'
    option limit '150'
    option leasetime '12h'
    option dhcpv4 'server'
    option dhcpv6 'server'
    option ra 'server'
    option ra_management '1'
    option dns_service '1'

    list dhcp_option '3,192.168.2.253'
    list dhcp_option '6,192.168.2.253'
```

---

## 五、内外网节点分流策略 (基于 HomeProxy)

不再使用老旧方案中“篡改 DHCP 选项”来实现，这种漏洞百出的方式对 IPv6 根本无效。我们将利用 HomeProxy 基于 `nftables` 的纯净内核防火墙底部分流：

进入 HomeProxy 的 `路由设置`：
- **默认机制**：利用内置的 GeoSite/GeoIP 库，国内直连，海外走自建 REALITY 节点拦截（原生完美统合 IPv4 + IPv6）。
- **特权大流量设备（NAS / 游戏机）**：在局域网访问控制列表中，将这些极其看重最高带宽且无需出海的内网设备 IP 加入**直接放行 (Direct)**。此时这几个专属设备的流量将被 Linux 底层直接踢出代理圈，0 CPU 损耗直接上网。

---

## 六、小米 BE6500 AP 设定参考

1. 进入后台修改上网方式：从拨号更改为 **有线中继 / AP 模式**。
2. 将 LAN IP 调整固定为：`192.168.2.1`（以后通过这个进路由器管理）。
3. 核实确认：`DHCP` 和 `IPv6 通告` 必须处于关闭状态。
4. Wi-Fi SSID 设置好后保存，以后全宅网络调度全部交托 J4125。

---

## 七、无需额外购买交换机的隐藏接线福利 

如果你家里的有线网络设备（包含卧室网线、NAS、电脑等）**总插头不超过 3 个**，那么你**完全不需要单独购买物理 2.5G 交换机！**

**布线秘籍：**
用一根线将 J4125 的 `eth1` 连接到 BE6500 上的 2.5G 网口。此时把剩下的网线直接插满 BE6500 的余下 3 个借口。
*   **因为 BE6500 设置为 AP 后，它内部的四口是由专业 ASIC 硬件交换芯片管理的。这就相当于一台白嫖的高性能 2.5G 物理交换机！**
*   这几个口独立协商速率互不干扰（接百兆全家设备也不拖累 2.5G 的 NAS），且 NAS 和电脑互传数据走的是原生物理线速交换，**绝对不会绕回去消耗 J4125 的 CPU 算力**。

---

## 八、GitHub Actions 打包极简高稳 OpenWrt 指南 (基于 P3TERX)

我们将原本臃肿的插件生态大清扫，专精于 VLESS-REALITY 的高性能转发。在配置 `P3TERX/Actions-OpenWrt` 时，务必遵循下述超纯净定制作业：

### 8.1 切换为稳定的高配底层源码 (build-openwrt.yml)
编辑 `.github/workflows/build-openwrt.yml` 文件，将代码源换成公认非常稳定且驱动支持完美的 ImmortalWrt 官方分支：
```yaml
env:
  REPO_URL: https://github.com/immortalwrt/immortalwrt
  REPO_BRANCH: openwrt-23.05
```

### 8.2 预固化家庭网关 IP (diy-part2.sh)
编辑 `diy-part2.sh`，在末尾加入这行 `sed` 硬修改代码。让出炉的固件原生 IP 就锁定为 `192.168.2.253`，免去你第一次开机插着显示器敲命令行的痛苦：
```bash
# 固化网关 IP
sed -i 's/192.168.1.1/192.168.2.253/g' package/base-files/files/bin/config_generate
```

### 8.3 实操解析：如何利用 SSH 停顿定制配置文件 (.config)
这是防宕机、斩断祸根的重中之重。请紧跟以下操作序列：

**第一阶段：抓取 SSH 通道**
1. 在你的 GitHub 仓库顶部点击 `Actions` 标签页，在左侧选择 `OpenWrt Builder`。
2. 点击右侧的 `Run workflow` 按钮，**在弹出的面板中将 `ssh` 文本框改为 `true`**，然后点击绿色的运行按钮。
3. 点击正在执行的流水线任务进入内部，点开 `build` 模块查看**实时控制台日志**。
4. 盯住日志输出，当系统执行到 `SSH connection to Actions` 这一步时（通常在开始几分钟后），流水线会主动暂停。展开该步骤日志，你会看到一条黑底的连接命令（通常是 `ssh ...` 或 `tmate ...`）。
5. 复制这条命令，打开你电脑原生的终端（CMD / PowerShell / Mac Terminal），粘贴运行，你就直接连入了位于 GitHub 云端的编译服务器命令行后台！

**第二阶段：精简选配 (Menuconfig)**
连入云端服务器后，在黑框终端内输入以下命令唤出蓝底图形化菜单：
`cd openwrt && make menuconfig`
*(菜单中用方向键移动，按 `Y` 勾选变为 `[*]`，按 `N` 取消勾选致空 `[ ]`)*

1. **核心定位**：进入 Target System 选 `x86`, Subtarget 选 `x86_64`。
2. **底层格式包**：进入 Target Images，务必**保留勾选** `[*] Build EFI GRUB images` (J4125必须) 与 `[*] squashfs`。
3. **插件与依赖极简精修**：
   - **核心应用（进入 LuCI -> Applications 勾选）**：必须勾选 `luci-app-homeproxy` (基于 Sing-box，现代防封锁协议首选) 和 `luci-app-upnp` (主机游戏透传基础)。
   - **底层必备依赖（排雷：防止 HomeProxy 无网或无法启动）**：
     - **虚拟网卡支持**：进入 `Kernel modules -> Network Support` 勾选 `kmod-tun`（Sing-box 建立 TUN 接口必备）。
     - **高级路由策略**：进入 `Network -> Routing and Redirection` 勾选 `ip-full`（Homeproxy 需要完整的 ip 命令处理分流策略，有冲突时需取消 `ip-tiny`）。
     - **证书与下载环境**：进入 `Base system` 勾选 `ca-bundle` 和 `ca-certificates`；进入 `Network -> File Transfer` 勾选 `curl`。（严重警告：如缺少证书，HomeProxy 首次运行时将无法下载所需的 GeoIP/Geosite 规则数据库，导致 Sing-box 内核直接由于找不到 node / ruleset 报错崩溃并拒绝启动）。
   - **大扫除坚决剔除（按 N 致空，防死机绝招）**：绝不保留 `luci-app-passwall`（不要与HomeProxy冲突）、`luci-app-dockerman`(Docker)、`luci-app-qbittorrent`/`aria2`(下载软件)、`luci-app-samba4`(网络挂载)。

**第三阶段：保存并释放流水线**
1. 在键盘上狂按两次 `ESC` 键，系统弹窗问你 `Do you wish to save your new configuration?`，直接回车选 `Yes` 保存。
2. 退回到普通命令行后，输入让流水线放行的触发指令：
`touch /tmp/continue`
3. 敲完回车，云端服务器在接收到指令后会主动踢你的连接下线，此时返回 GitHub 网页，你会发现之前停顿的流水线瞬间火力全开，继续疯狂编译了。

> **拿货提示**：等待大约 1 ~ 2 个小时后，编译完成的固件（体积两三百兆内的“性能猛兽”）就会出现在该页面最底部的 `Artifacts` 区域，下载解压即可刷机。

---

## 九、从零开始：固件提取与写盘刷机实战 (PE 方案)

由于 J4125 是一台完整的 x86 电脑主板（通常直接插了一块 M.sata 或 NVMe 固态硬盘），最简单、不挑底层、且绝对不需要你动螺丝刀拆机的刷机方式，就是利用 **Windows PE U 盘** 引导并进行本地暴力写盘。

### 9.1 认准并提取“真命天子”镜像
1. 解压你从 GitHub `Artifacts` 下载的那个体积几十兆的压缩包。
2. 里面会有好几个不同后缀的庞然大物，我们需要准确定位到包含 `squashfs`、`combined` 和 `efi` 关键字的文件。
   **目标文件名通常类似于**：`immortalwrt-x86-64-generic-squashfs-combined-efi.img.gz`
   *(注：如果不带 efi，J4125 这种主流新主板会点不亮只能黑屏；而 squashfs 能让你直接拥有网页端的“恢复出厂设置”保命能力)*。
3. **隐藏的一步**：使用解压软件（如 7-Zip 或 WinRAR），把这个 `.img.gz` 格式的压缩包**再次右键解压一次**！你会得到一个纯粹以 `.img` 结尾（约两三百兆大小）的最终镜像源文件。

### 9.2 离线准备！断网前的三大法宝收集
> ⚠️ **强烈必读：进行到这一步时，你必须还在有网的环境下！务必收集齐以下东西并将它们放入 U 盘，因为一旦开始拆旧路由器和接小主机，你就会彻底断网且无法再查阅资料了！**

1. **法宝一（制作 PE 环境）**：用你目前上网的电脑搜索下载 **微PE工具箱 (WePE)**。插上一个闲置的普通 U 盘，打开 WePE，点击右下角的“安装进 U 盘”图标，一键将它做成可引导的 PE 启动盘。
2. **法宝二（暴力写盘软件）**：千万别下那种几十兆的商业备份软件！开源圈子用的都是不到 1MB 的超微型工具：去搜索下载 **Roadkil's DiskImage 1.6**，或者 **physdiskwrite**（最好找带 UI 界面的 physgui 版）。为了以防万一，把你刚说的 **Rufus 4.7** 的单文件版也一起放进 U 盘作为备胎。
3. **法宝三（真命天子固件）**：即刚才在 9.1 步骤中最后解压出来的、数百兆大小的 **`.img` 结尾的 OpenWrt 固件文件**。
4. **最后拼装**：进入“我的电脑”，把刚才收集的 **小工具们** 和 **法宝三(.img固件)**，直接拷贝到你刚做好的 PE U盘的剩余空间里（方便起见，可以在 U 盘根目录建个叫 `OpenWrt-Setup` 的文件夹放进去）。

### 9.3 无网实战：直写 J4125 内置硬盘
带着做好的万能 U 盘和自信，走到已经断网的 J4125 面前：
1. 将 U 盘插到 J4125 上，给机器临时接上一个普通的键盘和一台显示器，通电开机。
2. 一按下开机键，立刻有节奏地狂按 `F11` 或 `DEL` 或 `F2`（根据主板品牌不同，可多试几次），唤出 BIOS 引导快捷菜单。选择**从你的 U 盘启动 (带有 UEFI USB DISK 字样)**。
3. 稍微等待读条，进入类似传统 Windows 的 PE 微型桌面。
4. **开始写盘**（以下两种工具任选其一，推荐方法一）：
   * **方法一 (首选 Roadkil's / physgui)**：双击打开你备好的微型写盘软件。在磁盘选项中，**必须**选中 J4125 自带的那块物理固态硬盘。载入你解压好的巨大 `.img` 文件。点击写入（Write / Start）。
   * **方法二 (如果用 Rufus)**：打开 Rufus。注意，Rufus 为了保护用户，出厂默认**会隐藏系统内置的 SSD 硬盘**，你会发现设备列表里只有各种 U 盘！**千万不要直接选 U 盘写入！** 你必须在 Rufus 的界面上按下隐藏快捷键 `Alt + F` (开启显示本地固定磁盘)，或者在顶部的高级选项里勾选“显示 USB 外置硬盘等”，直到你选中了那块真实的 128G 固态硬盘，然后引导类型选你的 `.img` 镜像。开始以 DD 模式写入。
5. **🎯 军令状防呆验证**：在点击确认覆盖之前，反复看清你选中的目标容量是机器原生的主硬盘芯片（如 128G/256G），绝对不能是十几G/几十个G的 U 盘自己！
6. 十几秒钟后，进度条通常就会丝滑完成。直接拔掉机器的电源强行断电，温柔地拔下这根功德圆满的 U 盘。拆除刚才临时借用的显示器和键盘。

将 J4125 重新接回光猫弱电箱，通电唤醒，当网口的交互信号灯开始疯狂闪烁时，证明软路由的大脑已经轰鸣启动。请掏出网线连接电脑，大踏步进入第十章的凯旋门。

---

## 十、OpenWrt 刷机后极简开屏配置指南

得益于我们在上方执行的“极客级源码底层手术”，重获新生的 OpenWrt 出厂即自带有完整的 IPv6 分发环境和极净生态。你只需登录网页后台（LUCI）进行最后三下鼠标点击：

### 10.1 点亮宽带账号（IPv6 瞬间通车）
1. 电脑通过网线插入 J4125 的 `eth1` 接口。在浏览器输入我们在编译前硬编码的：`http://192.168.2.253`。
2. 导航至左侧的 `网络 -> 接口 (Interfaces)`。
3. 找到 **WAN** 接口点击修改。协议切换为 `PPPoE`，填好运营商的宽带账号和密码，最后点击右上角保存并应用。
   > **[巅峰时刻]**：因为 ImmortalWrt 的内核机制，跟其同生的 `wan6` 虚拟防线会自动追随 PPPoE 嗅探并获取公网 IPv6 PD 前缀，全家 IPv6 一秒打通，不需要你加补任何一行规则！

### 10.2 可选拔除：解除出厂“锅盖式软桥接”
刚刷好的 OpenWrt 系统如果看到有多物理网口，通常会好心地帮你把它们软桥接成一锅粥（`br-lan`）。如果你是原教旨极客主义，且坚定只用 `eth1` 接外设交换机，那你可以把它粉碎断开：
1. 编辑 **LAN** 接口。进入上方的 `物理设置 (Physical Settings)`。
2. **彻底取消勾选** `[✓] 启用桥接 (Enable bridge)` 选项。
3. 在下方的网卡矩阵里，只勾选留给唯一一根网线的 `eth1`。
4. 保存并应用。这会将网桥逻辑完全撕裂，将所有多网口并发时的 CPU 软件伪交换消耗降死为 0。

### 10.3 HomeProxy 现代代理与内网极速直连
由于 HomeProxy 的配置极低，并且天然用现代协议重写了解析机制：
1. 导航至 `系统 -> HomeProxy`，进入 `节点配置` 粘贴或手动填入你自建的 VLESS-REALITY 服务器信息。
2. **启动代理引擎**：回到 `基本设置` 把主开关打开。内置的 GeoIP 数据库会自动在内核级帮你决策国内流量直通与海外流量拦截。
3. **分配内网专属贵宾车道**：在 `路由设置 (Routing)` 面板中，拉到底部的**局域网直接连接选项 (LAN Bypass)**。把你那几台看重百兆/千兆满速国内传输的高压重器（如 群晖 NAS、PS5）加入列表。这部分流量会被直接引流给底层硬件交换，再也进不了耗能巨大的 Sing-box。

万事俱备，东风已起！拔下你的终端键盘，关上弱电箱门，尽情去享受属于你自己的赛博冲浪吧！
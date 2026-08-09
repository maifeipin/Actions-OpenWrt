**English** | [中文](https://p3terx.com/archives/build-openwrt-with-github-actions.html)

# Actions-OpenWrt

[![LICENSE](https://img.shields.io/github/license/mashape/apistatus.svg?style=flat-square&label=LICENSE)](https://github.com/P3TERX/Actions-OpenWrt/blob/master/LICENSE)
![GitHub Stars](https://img.shields.io/github/stars/P3TERX/Actions-OpenWrt.svg?style=flat-square&label=Stars&logo=github)
![GitHub Forks](https://img.shields.io/github/forks/P3TERX/Actions-OpenWrt.svg?style=flat-square&label=Forks&logo=github)

A template for building OpenWrt with GitHub Actions

## Usage

- Click the [Use this template](https://github.com/P3TERX/Actions-OpenWrt/generate) button to create a new repository.
- Generate `.config` files using [Lean's OpenWrt](https://github.com/coolsnowwolf/lede) source code. ( You can change it through environment variables in the workflow file. )
- Push `.config` file to the GitHub repository.
- Select `Build OpenWrt` on the Actions page.
- Click the `Run workflow` button.
- When the build is complete, click the `Artifacts` button in the upper right corner of the Actions page to download the binaries.

## Sing-box 透明代理与运维工具

本仓库集成并预装了 Sing-box 透明代理一键部署脚本及 OpenWrt 本地控制台管理工具：

### 1. 路由器本地控制台命令 (`sb`)
固件编译时已预装 `/usr/bin/sb`（及 `sing-box-menu` 软链接）。SSH 登录 OpenWrt 终端后直接输入：
```bash
sb
```
- **节点导入**：支持粘贴 NaiveProxy 启动命令或 `vless://` Reality 链接（无需 Python/SQLite，原生 POSIX ash 解析）。
- **多节点管理**：持久化保存节点，支持带协议标签与服务器 IP 的可视化节点列表及一键切换。
- **双重安全校验**：任何切换/导入前自动执行 `sing-box check` 语法校验，不通过则自动拦截，防止配置失效导致服务瘫痪。
- **服务维护**：内置服务重启、GeoIP/GeoSite 规则库在线更新及 logread 日志实时查看。

### 2. 远程一键部署脚本 (`scripts/install_singbox_openwrt.py`)
在电脑端运行，支持一键将 Sing-box 静态内核、Geo 规则库及 `sb` 控制台工具发布部署至目标 OpenWrt 路由器：
```bash
python scripts/install_singbox_openwrt.py --deploy  # 全量部署模式
python scripts/install_singbox_openwrt.py           # 远程管理菜单模式
```

## Tips

- It may take a long time to create a `.config` file and build the OpenWrt firmware. Thus, before create repository to build your own firmware, you may check out if others have already built it which meet your needs by simply [search `Actions-Openwrt` in GitHub](https://github.com/search?q=Actions-openwrt).
- Add some meta info of your built firmware (such as firmware architecture and installed packages) to your repository introduction, this will save others' time.

## Credits

- [Microsoft Azure](https://azure.microsoft.com)
- [GitHub Actions](https://github.com/features/actions)
- [OpenWrt](https://github.com/openwrt/openwrt)
- [coolsnowwolf/lede](https://github.com/coolsnowwolf/lede)
- [Mikubill/transfer](https://github.com/Mikubill/transfer)
- [softprops/action-gh-release](https://github.com/softprops/action-gh-release)
- [Mattraks/delete-workflow-runs](https://github.com/Mattraks/delete-workflow-runs)
- [dev-drprasad/delete-older-releases](https://github.com/dev-drprasad/delete-older-releases)
- [peter-evans/repository-dispatch](https://github.com/peter-evans/repository-dispatch)

## License

[MIT](https://github.com/P3TERX/Actions-OpenWrt/blob/main/LICENSE) © [**P3TERX**](https://p3terx.com)

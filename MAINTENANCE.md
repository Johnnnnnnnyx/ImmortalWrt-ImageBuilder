# Johnnywrt 固件维护与升级

跨电脑或新对话可直接给助手本分支链接，并说：**先读 AGENTS.md 和 MAINTENANCE.md，再按说明维护固件。**

## 维护入口

- 仓库：Johnnnnnnnyx/ImmortalWrt-ImageBuilder，定制分支：`Johnny`。
- 工作流：`.github/workflows/build-iso-25.12.x.yml`。
- 构建与首次启动配置：`x86-64/build25.sh`、`99-zz-bypass`、`99-zzz-johnnywrt`。
- 默认选择最新稳定版、1G、Docker=no；用户另有明确要求时按要求调整。
- 2026-10-28 核实官方最新稳定版为 ImmortalWrt 25.12.2，配套内核 6.12.103。用户选择稳定版，不使用内核 6.18.55 的 SNAPSHOT。以后必须重新查询官方版本。
- 同日 OpenWrt MeowX 签名源：插件/服务 0.1.8-r1、核心 0.3.9-r1。GitHub 应用版 0.4.3 是手机/桌面产品，不应混用。每次构建重新解析软件源，最终版本以发布 manifest 为准。

## AI 构建前必读清单

1. 先完整阅读根目录 `AGENTS.md` 与本文件，确认当前用户要求，再查看最近一次 Actions 结果；失败时先读失败步骤日志，不要直接重复运行。
2. 使用 `Johnny` 分支，核对最新稳定版、对应内核与签名软件源。当前升级基线为 x86/64、EFI/GPT、SquashFS、32 MiB 引导分区和 1024 MiB 根分区。
3. 检查本次修改的 Linux 脚本使用 LF 换行；Windows 网页上传会按原始字节提交，不能依赖 Git 自动转换 CRLF。上传后从远端读回核对内容。
4. 运行语法与回归检查，再启动完整构建。只有 UEFI 启动、BIOS 路径旧到新/新到新升级、实际 SSH 登录和配置保留检查全部通过，才可发布。
5. 发布备注必须列出准确文件名、实际软件版本、手动保留配置步骤、验证结果和未验证范围。目标设备上的 `sysupgrade -T` 只是校验，不能表述为已经升级成功。

### 已确认的问题与必要依赖

- 2026-10-28 第 6 次构建在模拟网卡检查处失败：`ip link add zttest001 type dummy` 报 `Unknown device type`，测试只安装了 `kmod-veth`，缺少 `kmod-dummy`。`smoke-test25.py` 必须在一次性测试虚拟机内安装 **kmod-veth 和 kmod-dummy**，使用当前内核对应的软件源，然后执行模拟 ZeroTier 接口和跨网段回包测试。不要删除测试或把失败当作通过。修复是否有效须看下一次完整运行结果。
- 当前 BusyBox 没有 `chpasswd`、`nohup`：测试密码通过串口向 `passwd` 输入；后台任务使用忽略 HUP 的子进程并重定向输入输出。不要把仅在桌面 Linux 上存在的命令直接搬入路由器。
- `jshn.sh` 不兼容直接开启 `set -u` 的调用方式；在线更新器使用 `set -e`，先加载 `/lib/functions.sh`，再加载 JSON 库。异常退出必须释放锁并清除半成品下载。
- `sysupgrade -T` 通过并不保证分区布局相同；在线更新还必须核对实际分区起点和大小。仅凭 FAT/GPT 也不能判断当前用 UEFI 启动，现有 BIOS 启动路径必须单独验证。
- 不把测试设备的密码、网络 ID、订阅、私钥或实际站点配置写进仓库、日志和公共镜像。实机配置备份只留在用户本机。

## 文件选择与 UEFI 全新安装

- `Johnnywrt-x86_64.iso`：UEFI 全新安装器。新建虚拟机选择 UEFI/OVMF，准备至少 8 GB 磁盘，挂载 ISO，启动后执行 `ddd` 选择安装盘；安装完成后卸载 ISO，再从硬盘 UEFI 启动。安装会清空所选磁盘。
- `Johnnywrt-x86_64-squashfs-combined-efi.img.gz`：EFI/GPT 硬盘固件。既用于网页升级，也可以解压为 `.img` 后直接写入新磁盘/导入虚拟机磁盘，再用 UEFI 启动。
- 镜像支持普通 UEFI；没有承诺 Secure Boot 签名支持。
- 每次发布附 `SHA256SUMS` 与 `.manifest`。ISO 内嵌的固件必须与通过测试的 `.img.gz` 解压内容一致。

## 已安装设备通过网页升级

本次起新增“系统 → Johnnywrt 在线更新”，固定仓库 `https://github.com/Johnnnnnnnyx/ImmortalWrt-ImageBuilder/releases`。点击检查、下载校验，再确认保留配置升级；不会无人值守自动刷机。

发布必须包含固定名 `Johnnywrt-x86_64-squashfs-combined-efi.img.gz`、`SHA256SUMS` 和 `firmware.json`。元数据记录版本、标签、源代码提交、x86/64 目标、EFI SquashFS 格式和根分区大小。在线更新拒绝不匹配格式/布局、预发布、跨大版本、缺少元数据或校验失败的包。

构建流程固定 1G 以兼容当前部署。更新状态和下载仅在 `/tmp/johnny-update`，重启后清除；API 限速/网络错误会显示错误，可再次检查。旧版尚无此入口，第一次使用下面的手动网页升级流程。

1. 在系统的备份页面下载配置备份，虚拟机另外做磁盘快照。
2. 确认当前是 x86/64、EFI/GPT 磁盘、SquashFS，并选择相同分区布局的版本（当前 32 MiB 引导分区、1024 MiB 根分区）。现有设备可继续沿用已验证的 BIOS 启动方式，升级时不要同时更改虚拟机启动方式。
3. 在“系统 → 备份/升级 → 更新固件”上传 `squashfs-combined-efi.img.gz`，**不要上传 ISO**。
4. 保留配置；系统校验不通过时不要强制刷写。自装插件不会自动全部保留，内置插件由新镜像重新提供。
5. 升级后检查 LAN、SSH、MeowX DNS/节点、ZeroTier。不要把能上传或 `sysupgrade -T` 通过等同于完整升级验证。

后续版本沿用同一格式并通过保留配置测试，可以继续使用此页面。更换架构、启动方式、文件系统、分区布局或跨系统大版本时须另做迁移评估，不能保证任意固件直接兼容。

实际部署补充：2026-10-28 读取启动状态发现现有设备以 BIOS 启动 EFI/GPT 磁盘（仅凭 FAT 引导分区不能判断为 UEFI 启动）。因此升级测试覆盖这条 BIOS 路径，独立启动测试覆盖 UEFI/OVMF。EFI combined 镜像可用于支持的两种引导路径，在线更新检查 GPT 与实际分区表，而非仅检查 `/sys/firmware/efi`。

## SSH 修复的原因与边界

原版 Dropbear 2025.89 默认给 SSH 握手/交互包加 AF21（IP TOS 0x48）标记。已在实际网络观察到握手异常，并验证清零该标记后恢复；具体异常网络设备/驱动没有定位，不应宣称 OpenWrt 内核故障。

`johnny-ssh-qos` 给官方启动命令加原生 `-z`，由 `99-zzz-johnnywrt` 在初次启动及保留配置升级后执行。只关闭 SSH IP 优先级标记，不改变认证和绑定。测试要求重复执行无额外变化，遇到上游脚本布局变化须失败并人工适配。

此前在设备上设置的网段限定 nftables 兼容规则不进入公共固件；升级时可能随用户备份保留，与 `-z` 并存不影响正常使用。

## 发布前验收

- `sh x86-64/test-ssh-qos.sh`、`test-custom25.sh`、`test-distfeeds.sh`。
- 工作流的语法检查、固定版本 QuickStart Go 测试、包清单检查。
- `smoke-test25.py`：UEFI 启动、原有功能、SSH `-z` 生效。
- `test-sysupgrade.py`：从上一版 ISO 提取出的硬盘镜像启动，通过真实 SSH 登录，在一次性虚拟机内执行旧到新、新到新的保留配置升级，并检查网络、密码/主机密钥、MeowX 订阅和 ZeroTier 身份配置。
- 校验 ISO 的 BIOS/UEFI 引导目录及内嵌镜像哈希；发布独立 UEFI `.img.gz`。
- 在授权目标设备上只执行 `sysupgrade -T` 检查最终文件。刷机必须另获用户明确指令。

上述测试是发布门槛，不代表未执行的构建已经成功。实际结果以对应 Actions 运行及发布记录为准。

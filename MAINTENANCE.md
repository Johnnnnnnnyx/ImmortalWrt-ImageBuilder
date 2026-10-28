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

- 第 12 次在旧到新升级等待 441 秒后恢复 SSH/overlay，但随后 `Retained settings changed`。因此不能把未通过项全部归因于等待时限，更不能据此称固件升级兼容性已通过。旧测试未保存逐文件 expected/actual，失败盘无法反推内存中的 baseline，这是诊断缺口。新增 baseline、每轮刷写前/恢复后文件哈希、UCI 字段哈希、shadow 各账号行哈希、mtime 和待提交 UCI 键；不记录密码/私钥值，也不重置 baseline 消除差异。用户要求：先定位差异来源并复现通过，再启动新的完整构建。
- 工作流 `diagnostic_run_id` 非空时，只复用该运行的测试镜像执行专项诊断，构建/发布 job 不运行且诊断 job 仅有读取权限。今后失败工件同时保存原始干净升级包，避免排查测试脚本时重复编译。旧工件只有失败磁盘时可清空其一次性 overlay 复用 ROM/GPT；恢复工具已用 #9 干净镜像验证解压内容完全不变，派生镜像只供诊断、不得发布。

- 第 11 次已通过编译、UEFI 启动、旧版普通重启及旧到新升级；第二轮新到新在 SSH 等待 240 秒后失败。串口确认两次写盘均完成，第二次已进入 Linux/procd，但截止时尚未启动 LAN。第一轮从下载到完成检查耗时约 253 秒，原时限包含约 90 秒的 1 GiB 写盘与后续启动，余量不足。下一轮将一次性 TCG 虚拟机的等待上限改为 600 秒，并每 30 秒记录状态、成功时记录实际耗时，以验证超时假设；仍必须满足新 boot ID、实际 SSH 认证、overlay 状态 2、配置与服务检查，持续未就绪必须失败。未经下一轮完整结果，不得称此问题已修复或归因于真实设备；不因此更改固件内核、网络或磁盘布局。

- 第 10 次构建通过编译和 UEFI 启动，但在第二次启动旧版 #5 的普通重启基线失败，尚未刷入新版。串口显示系统已正常启动，同时出现 `overlay filesystem has not been fully initialized yet`。测试此前只等 SSH 可登录就重启；OpenWrt 的 S95done 才标记 `/overlay/.fs_state -> 2`，fstools 下次启动会清理未就绪的 overlay，测试密码因此无法保留。`wait_ssh()` 必须同时检查新 boot ID（重启时）、实际 SSH 认证、overlay 状态为 2，并同步磁盘后才允许重启/升级；不能以固定等待 65 秒或端口打开代替。新增 `test-upgrade-readiness.py` 已先复现提前返回，再验证就绪等待和超时失败。此问题不同于之前 Q35 停在 BIOS 的症状，也不是 UEFI 镜像或新菜单导致。上游依据：[启动完成处理](https://github.com/openwrt/openwrt/blob/openwrt-25.12/package/base-files/files/etc/init.d/done)、[fstools 配置区状态处理](https://github.com/openwrt/fstools/blob/master/libfstools/overlay.c)。

- 2026-10-28 第 6 次构建在模拟网卡检查处失败：`ip link add zttest001 type dummy` 报 `Unknown device type`，测试只安装了 `kmod-veth`，缺少 `kmod-dummy`。`smoke-test25.py` 必须在一次性测试虚拟机内安装 **kmod-veth 和 kmod-dummy**，使用当前内核对应的软件源，然后执行模拟 ZeroTier 接口和跨网段回包测试。补齐后第 7 次完整 UEFI 启动测试已通过。不要删除测试或把失败当作通过。
- 第 7 次在 BIOS 升级后未恢复 SSH；第 8 次对照确认，未刷写新版时旧固件的普通重启也失败。Q35/SeaBIOS 测试虚拟机仍显示 running，但画面停在 `Guest has not initialized the display (yet)`，串口没有第二次引导输出。因此不能将其归因于新版刷写或分区大小。现有设备实际是 i440FX/BIOS，升级测试默认使用匹配的 `pc` 机型，并在编译前先跑旧版普通重启检查；`--machine q35 --reboot-only` 可复现原测试条件。Q35 重启故障的内部原因尚未确定，不得宣称所有 BIOS 机型兼容。完整旧到新、新到新升级门槛仍然保留。
- 失败时保留 QMP 启动画面、串口日志和一次性虚拟磁盘，先检查证据再重跑。小于 1 MiB 的 GRUB BIOS Boot 分区提示、旧盘已有的备用 GPT 提示，都不能单独当作根因；不要据此扩大分区。失败磁盘只允许含一次性 VM 测试数据，不得上传用户实机磁盘。
- 相关上游线索：[QEMU #766](https://gitlab.com/qemu-project/qemu/-/issues/766) 记录 Q35/TCG 在重置后因 SeaBIOS 状态无法更新而循环重启，KVM 不复现。它支持检查虚拟化环境，但仅凭相似症状不能认定本次就是同一个缺陷；不要把修改真实路由器内核或 GRUB 当作既定修复。
- 当前 BusyBox 没有 `chpasswd`、`nohup`：测试密码通过串口向 `passwd` 输入；后台任务使用忽略 HUP 的子进程并重定向输入输出。不要把仅在桌面 Linux 上存在的命令直接搬入路由器。
- 升级重启时 SSH 握手可能抛出独立的 `EOFError`，不属于 `SSHException` 或 `OSError`。`test-sysupgrade.py` 的重连等待必须同时重试这些临时断连异常；仍须以新的 boot ID、真实登录和配置校验确认升级完成，不能仅凭端口恢复判定成功。
- `jshn.sh` 不兼容直接开启 `set -u` 的调用方式；在线更新器使用 `set -e`，先加载 `/lib/functions.sh`，再加载 JSON 库。异常退出必须释放锁并清除半成品下载。
- 实机只读校验脚本若启用 `set -e` 后直接调用 `/lib/upgrade/common.sh` 的 `get_partitions`，需先设 `VERBOSE=1`；否则其日志函数 `v` 可因变量为空返回 1，让检查在读取分区表前退出。这是辅助脚本问题，不代表镜像不兼容。更新器中的调用有显式失败分支，且已在真实升级测试中验证，不能因辅助脚本退出就改动固件或跳过检查。
- `sysupgrade -T` 通过并不保证分区布局相同；在线更新还必须核对实际分区起点和大小。仅凭 FAT/GPT 也不能判断当前用 UEFI 启动，现有 BIOS 启动路径必须单独验证。
- 不把测试设备的密码、网络 ID、订阅、私钥或实际站点配置写进仓库、日志和公共镜像。实机配置备份只留在用户本机。

## 文件选择与 UEFI 全新安装

- `Johnnywrt-x86_64.iso`：UEFI 全新安装器。新建虚拟机选择 UEFI/OVMF，准备至少 8 GB 磁盘，挂载 ISO，启动后执行 `ddd` 选择安装盘；安装完成后卸载 ISO，再从硬盘 UEFI 启动。安装会清空所选磁盘。
- `Johnnywrt-x86_64-squashfs-combined-efi.img.gz`：EFI/GPT 硬盘固件。既用于网页升级，也可以解压为 `.img` 后直接写入新磁盘/导入虚拟机磁盘，再用 UEFI 启动。
- 镜像支持普通 UEFI；没有承诺 Secure Boot 签名支持。
- 每次发布附 `SHA256SUMS` 与 `.manifest`。ISO 内嵌的固件必须与通过测试的 `.img.gz` 解压内容一致。

## 已安装设备通过网页升级

在线更新位于“系统 → 备份与更新 → 更新固件”，固定仓库 `https://github.com/Johnnnnnnnyx/ImmortalWrt-ImageBuilder/releases`。点击检查、下载校验，再确认保留配置升级；不会无人值守自动刷机。旧版 #9 的入口是“系统 → Johnnywrt 在线更新”。

发布必须包含固定名 `Johnnywrt-x86_64-squashfs-combined-efi.img.gz`、`SHA256SUMS` 和 `firmware.json`。元数据记录版本、标签、源代码提交、x86/64 目标、EFI SquashFS 格式和根分区大小。在线更新拒绝不匹配格式/布局、预发布、跨大版本、缺少元数据或校验失败的包。

构建流程固定 1G 以兼容当前部署。更新状态和下载仅在 `/tmp/johnny-update`，重启后清除；API 限速/网络错误会显示错误，可再次检查。旧版尚无此入口，第一次使用下面的手动网页升级流程。

1. 在系统的备份页面下载配置备份，虚拟机另外做磁盘快照。
2. 确认当前是 x86/64、EFI/GPT 磁盘、SquashFS，并选择相同分区布局的版本（当前 32 MiB 引导分区、1024 MiB 根分区）。现有设备可继续沿用已验证的 BIOS 启动方式，升级时不要同时更改虚拟机启动方式。
3. 在“系统 → 备份/升级 → 更新固件”上传 `squashfs-combined-efi.img.gz`，**不要上传 ISO**。
4. 保留配置；系统校验不通过时不要强制刷写。自装插件不会自动全部保留，内置插件由新镜像重新提供。
5. 升级后检查 LAN、SSH、MeowX DNS/节点、ZeroTier。不要把能上传或 `sysupgrade -T` 通过等同于完整升级验证。

后续版本沿用同一格式并通过保留配置测试，可以继续使用此页面。更换架构、启动方式、文件系统、分区布局或跨系统大版本时须另做迁移评估，不能保证任意固件直接兼容。

实际部署补充：2026-10-28 读取启动状态发现现有设备以 BIOS 启动 EFI/GPT 磁盘（仅凭 FAT 引导分区不能判断为 UEFI 启动）。因此升级测试覆盖这条 BIOS 路径，独立启动测试覆盖 UEFI/OVMF。EFI combined 镜像可用于支持的两种引导路径，在线更新检查 GPT 与实际分区表，而非仅检查 `/sys/firmware/efi`。

## 菜单与默认主机名（2026-10-28 定制）

- 全新安装默认主机名为 **JohnnyWrt**，大小写必须一致。`99-zzz-johnnywrt` 只替换上游默认值或空值；保留配置升级保留用户原有名称，包括此前的 `Johnnywrt`。
- ZeroTier 与 MeowX 同属“服务”，顺序紧跟 MeowX。保留原页面、权限和配置，只搬菜单路径。LuCI 的 `scrubMenu()` 会自动隐藏空的 `firstchild` 分类；保留 VPN 父菜单定义，以便以后安装其他 VPN 插件时自动出现。不要永久删除 VPN 的 title。
- `johnny-ui-layout.uc` 在首次启动/保留配置升级时执行：为上游固件卡片嵌入 `johnny/update.js`，不替换原生备份、恢复或手动刷写处理函数。旧独立菜单文件保留为空 JSON，以取消旧入口。
- 上游 LuCI 固件页结构改变时，补丁必须明确失败，再人工适配；不得跳过检查或用整份旧页面覆盖上游。`test-ui-layout.sh` 在一次性 VM 的临时目录检验迁移、重复执行、其他 VPN 菜单和未知结构拒绝。
- 在线状态读取失败只影响在线更新区域，不能阻止备份/恢复/手动上传页面显示。`test-update-ui.js` 检查按钮状态、只读权限、错误隔离、单独确认升级，以及保存备份设置重新渲染后只有一组状态轮询。升级测试另用实际安装的 LuCI 代码和菜单验证空 VPN 隐藏、新插件恢复可见。
- 本节描述本次实现；完整发布结果另行记录，不能仅凭这些备注宣称新镜像构建成功。

## SSH 修复的原因与边界

原版 Dropbear 2025.89 默认给 SSH 握手/交互包加 AF21（IP TOS 0x48）标记。已在实际网络观察到握手异常，并验证清零该标记后恢复；具体异常网络设备/驱动没有定位，不应宣称 OpenWrt 内核故障。

`johnny-ssh-qos` 给官方启动命令加原生 `-z`，由 `99-zzz-johnnywrt` 在初次启动及保留配置升级后执行。只关闭 SSH IP 优先级标记，不改变认证和绑定。测试要求重复执行无额外变化，遇到上游脚本布局变化须失败并人工适配。

此前在设备上设置的网段限定 nftables 兼容规则不进入公共固件；升级时可能随用户备份保留，与 `-z` 并存不影响正常使用。

## 发布前验收

- `sh x86-64/test-ssh-qos.sh`、`test-custom25.sh`、`test-distfeeds.sh`。
- `node --test x86-64/test-update-ui.js`、`python3 x86-64/test-upgrade-readiness.py`；实际安装的菜单过滤检查包含在升级测试中。
- 工作流的语法检查、固定版本 QuickStart Go 测试、包清单检查。
- `smoke-test25.py`：UEFI 启动、原有功能、SSH `-z` 生效。
- `test-sysupgrade.py`：从上一版 ISO 提取出的硬盘镜像启动，通过真实 SSH 登录，在一次性虚拟机内执行旧到新、新到新的保留配置升级，并检查网络、密码/主机密钥、MeowX 订阅和 ZeroTier 身份配置。
- 校验 ISO 的 BIOS/UEFI 引导目录及内嵌镜像哈希；发布独立 UEFI `.img.gz`。
- 在授权目标设备上只执行 `sysupgrade -T` 检查最终文件。刷机必须另获用户明确指令。

上述测试是发布门槛，不代表未执行的构建已经成功。实际结果以对应 Actions 运行及发布记录为准。

## 2026-10-28 已完成的发布与验证

- 发布：[Johnnywrt-ISO-25.12.2-9](https://github.com/Johnnnnnnnyx/ImmortalWrt-ImageBuilder/releases/tag/Johnnywrt-ISO-25.12.2-9)，源码 `643692e5a4a4efc870d37bac110ea6e9103ba675`；[完整构建 #9](https://github.com/Johnnnnnnnyx/ImmortalWrt-ImageBuilder/actions/runs/40632600623) 成功。
- 已通过脚本回归、软件包检查、UEFI 启动、i440FX/BIOS 普通重启、旧版 #5 到新版 #9 及新版 #9 再升级的两轮保留配置测试；每轮都实际认证 SSH 并检查配置和服务。
- ISO 同时有 BIOS/UEFI 引导目录，其内嵌硬盘镜像与已测试固件解压后的 SHA256 完全一致。安装器沿用固定上游版本；未声称已在每种实机上走完 ISO 交互安装。
- 最终升级包 SHA256：`261941783b08270b075483220e093759405852e069d05a4965e0974c26adb441`。两台授权目标设备均通过此文件的传输哈希、实际分区起点/大小和 `sysupgrade -T` 校验；前后 boot ID 相同，未刷写、未重启。实机报告和配置备份只保存在用户本机。
- 实际版本：ImmortalWrt 25.12.2 / Linux 6.12.103，MeowX 插件 0.1.8-r1 / 核心 0.3.9-r1。固件含固定仓库的在线更新入口。
- 现有 BIOS 设备手动上传 `.img.gz` 并保留配置，保持原启动方式；全新 UEFI 安装使用 ISO 或写入解压后的 EFI 硬盘镜像。通过虚拟机和只读实机校验，不等于已经完成用户实机升级，也不能保证任意硬件或未来跨版本兼容。

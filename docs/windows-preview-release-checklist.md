# Windows 预览版发布核查

## 当前证据与边界

- `v0.1.0-preview.1` 的 GitHub CI 已通过 Web、Core 与 Windows/macOS/Linux 桌面代码检查；[补传任务](https://github.com/yangwenbin19961109/LoreDock/actions/runs/35482550239) 在 Windows runner 上从该 tag 构建 MSI/NSIS，并通过打包 Core 的启动、鉴权、导入索引与退出烟雾测试。
- [预发布页](https://github.com/yangwenbin19961109/LoreDock/releases/tag/v0.1.0-preview.1) 提供 Windows x64 MSI 和 NSIS。它们未签名，不是正式发布版。
- CI 构建成功和 Core 烟雾测试不等于安装包已在干净机器上完成安装、覆盖升级、卸载、用户数据保留与人工界面验收。

## 第三方声明待核对项

当前安装包包含项目 PolyForm 许可证和[直接依赖清单](dependency-licenses.md)，但不能将其视为完整传递依赖声明。2026-09-20 的本地只读预审结果如下；“没有独立许可证文件”只描述本地包缓存或发行元数据，不推断上游没有许可证。

- `cargo metadata --manifest-path apps/desktop/src-tauri/Cargo.toml --format-version 1 --locked` 解析出 430 个第三方包，含其他平台及构建依赖。`cargo tree --manifest-path apps/desktop/src-tauri/Cargo.toml --target x86_64-pc-windows-msvc --edges normal --prefix none --locked` 的保守 Windows 树中有 218 个不同包（含项目自身）；其中以下 10 个第三方包的本地 crate 根目录没有 `LICENSE*`、`LICENCE*`、`COPYING*` 或 `NOTICE*` 文件：`alloc-stdlib 0.2.4`、`selectors 0.36.1`、`unic-char-property 0.9.0`、`unic-char-range 0.9.0`、`unic-common 0.9.0`、`unic-ucd-ident 0.9.0`、`unic-ucd-version 0.9.0`、`webview2-com 0.38.2`、`webview2-com-macros 0.8.1`、`webview2-com-sys 0.38.2`。`selectors` 的 Cargo 元数据声明为 `MPL-2.0`，需按 [Mozilla 的发行说明](https://www.mozilla.org/en-US/MPL/2.0/FAQ/)单独核对实际发行义务。
- `core/.venv` 中安装了 73 个 Python 发行包，包含开发与打包依赖。除项目自身外，`flatbuffers 25.12.19`、`httpx 0.28.1`、`onnxruntime 1.29.0`、`protobuf 7.36.1`、`pywin32-ctypes 0.2.3`、`sqlite-vec 0.1.9`、`tokenizers 0.23.1` 的本地发行元数据未列出 `License-File`。正式声明须按锁文件与实际打包内容复核，不应直接把全部开发依赖当成运行时内容。
- Web 安装包以已构建的前端资产分发；其直接运行时依赖与 `scheduler` 已在[直接依赖清单](dependency-licenses.md)登记。仍须确认实际分发资产中需保留的版权与许可证文本。

下一步先从上述包的上游发行物取得所需声明，按实际安装包内容汇总并随包提供；然后重新构建一个新预览 tag。不要移动或重写已有 tag，也不要把现有预发布包标记为正式发布。

## 干净 Windows 虚拟机验收

必须使用可丢弃、可还原快照的干净 Windows 虚拟机；不要在有真实 LoreDock 数据的开发机上运行安装/卸载脚本。MSI 和 NSIS 各从独立干净快照开始，先下载对应 tag 的安装包，并在虚拟机中取得同 tag 的仓库脚本。

在 PowerShell 中分别执行（路径替换为虚拟机内的实际下载位置）：

```powershell
./scripts/test-windows-installer.ps1 -InstallerType msi -CurrentInstaller 'C:\Temp\LoreDock_0.1.0_x64_en-US.msi' -AcknowledgeDisposableMachine
./scripts/test-windows-installer.ps1 -InstallerType nsis -CurrentInstaller 'C:\Temp\LoreDock_0.1.0_x64-setup.exe' -AcknowledgeDisposableMachine
```

脚本验证安装登记、启动、卸载后数据标记保留及无残留进程。还需人工检查首次启动、主要页面和卸载入口。覆盖升级测试需要**旧版与新版两个不同安装包**；首个 tag 只有一个版本，不得用同版本重装冒充升级验收。得到下一版后，从旧版安装快照分别传入 `-PreviousInstaller` 与 `-CurrentInstaller` 执行脚本，再记录结果、Windows 版本、安装包版本及失败截图。

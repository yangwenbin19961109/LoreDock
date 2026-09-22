# Windows 预览版发布核查

## 当前证据与边界

- `v0.1.0-preview.1` 的 GitHub CI 已通过 Web、Core 与 Windows/macOS/Linux 桌面代码检查；[补传任务](https://github.com/yangwenbin19961109/LoreDock/actions/runs/35482550239) 在 Windows runner 上从该 tag 构建 MSI/NSIS，并通过打包 Core 的启动、鉴权、导入索引与退出烟雾测试。
- [预发布页](https://github.com/yangwenbin19961109/LoreDock/releases/tag/v0.1.0-preview.1) 提供 Windows x64 MSI 和 NSIS。它们未签名，不是正式发布版。
- CI 构建成功和 Core 烟雾测试不等于安装包已在干净机器上完成安装、覆盖升级、卸载、用户数据保留与人工界面验收。

## 第三方声明待核对项

当前安装包包含项目 PolyForm 许可证和[直接依赖清单](dependency-licenses.md)，但不能将其视为完整传递依赖声明。2026-09-20 的本地只读预审结果如下；“没有独立许可证文件”只描述本地包缓存或发行元数据，不推断上游没有许可证。

后续 Windows 构建现会运行 `scripts/generate-windows-notices.py`，把本地可读取的声明文本汇总为安装资源 `licenses/third-party/THIRD_PARTY_NOTICES.txt`，并把缺失项写入 `licenses/third-party/REVIEW_NEEDED.txt`。本机重建确认 MSI 与 NSIS 打包脚本均包含两份文件，打包 Core 烟雾测试通过。这是声明收集的进展，不表示 2026-09-20 已发布的首个预览安装包被更新，也不表示许可证复核完成。

- `cargo metadata --manifest-path apps/desktop/src-tauri/Cargo.toml --format-version 1 --locked` 解析出 430 个第三方包，含其他平台及构建依赖。`cargo tree --manifest-path apps/desktop/src-tauri/Cargo.toml --target x86_64-pc-windows-msvc --edges normal --prefix none --locked` 的保守 Windows 树中有 218 个不同包（含项目自身）；其中以下 10 个第三方包的本地 crate 根目录没有 `LICENSE*`、`LICENCE*`、`COPYING*` 或 `NOTICE*` 文件：`alloc-stdlib 0.2.4`、`selectors 0.36.1`、`unic-char-property 0.9.0`、`unic-char-range 0.9.0`、`unic-common 0.9.0`、`unic-ucd-ident 0.9.0`、`unic-ucd-version 0.9.0`、`webview2-com 0.38.2`、`webview2-com-macros 0.8.1`、`webview2-com-sys 0.38.2`。`selectors` 的 Cargo 元数据声明为 `MPL-2.0`，需按 [Mozilla 的发行说明](https://www.mozilla.org/en-US/MPL/2.0/FAQ/)单独核对实际发行义务。
- `core/.venv` 中安装了 73 个 Python 发行包，包含开发与打包依赖。除项目自身外，`flatbuffers 25.12.19`、`httpx 0.28.1`、`onnxruntime 1.29.0`、`protobuf 7.36.1`、`pywin32-ctypes 0.2.3`、`sqlite-vec 0.1.9`、`tokenizers 0.23.1` 的本地发行元数据未列出 `License-File`。正式声明须按锁文件与实际打包内容复核，不应直接把全部开发依赖当成运行时内容。
- Web 安装包以已构建的前端资产分发；其直接运行时依赖与 `scheduler` 已在[直接依赖清单](dependency-licenses.md)登记。仍须确认实际分发资产中需保留的版权与许可证文本。

本机生成结果共收集 293 个依赖条目（包含部分构建依赖），有 13 项没有可读取的本地声明文本：上述 10 个 Rust 包，以及 `flatbuffers 25.12.19`、`sqlite-vec 0.1.9`、`tokenizers 0.23.1`。其余先前未在 Python `License-File` 元数据中列出的包，在安装文件中找到了可读取的声明文本。不同系统或依赖缓存可能得到不同的未决清单，应以对应安装包内的 `REVIEW_NEEDED.txt` 为准。

## 上游声明补齐

2026-10-02 已补齐上述 13 项的声明文本，来源与核对结论如下：

- 生成脚本 `scripts/generate-windows-notices.py` 新增 `licenses/upstream/{ecosystem}/{name}/{version}/` 回退目录：本地包内读不到声明文本时，使用仓库内已提交的上游文本，并在条目中标注 `upstream/...` 文件名。脚本以 `core/.venv` 解释器运行（否则会收集到全局 Python 环境里的无关包，例如占位包 `bs4 0.0.2`）。
- Rust 包 `alloc-stdlib 0.2.4`（BSD-3-Clause，来自 dropbox/rust-alloc-no-stdlib）、`webview2-com 0.38.2`、`webview2-com-macros 0.8.1`、`webview2-com-sys 0.38.2`（MIT，来自 wravery/webview2-rs/）已取得对应 MIT/BSD 许可文本。
- `unic-char-property`、`unic-char-range`、`unic-common`、`unic-ucd-ident`、`unic-ucd-version`（均为 0.9.0，MIT/Apache-2.0，来自 open-i18n/rust-unic）已同时取得 `LICENSE-MIT` 与 `LICENSE-APACHE` 两份文本。
- `selectors 0.36.1` 为 MPL-2.0（servo/stylo 仓库根目录没有单独 LICENSE 文件，README 声明整个 Stylo 项目按 MPL-2.0 授权）。MPL-2.0 §3.3 要求发布者让接收者能够获取许可文本：本包随安装资源提供来自 SPDX license-list 的 MPL-2.0 官方全文（`MPL-2.0.txt`），并保留 crate 元数据中的 `MPL-2.0` 标识，满足该项义务。
- Python 包 `flatbuffers 25.12.19`（Apache-2.0，来自 google/flatbuffers）、`sqlite-vec 0.1.9`（MIT/Apache-2.0，来自 asg017/sqlite-vec，含 `LICENSE-MIT` 与 `LICENSE-APACHE`）、`tokenizers 0.23.1`（Apache-2.0，来自 huggingface/tokenizers）已取得对应文本。
- 重新运行后：本机收集 293 个依赖条目，`REVIEW_NEEDED.txt` 为空。新版包内的 `THIRD_PARTY_NOTICES.txt` 包含上述 13 项的 `upstream/` 文本块。

下一步从该状态重建安装资源并创建新预览 tag；不要移动或重写已有 tag，也不要把现有预发布包标记为正式发布。

## 干净 Windows 虚拟机验收

必须使用可丢弃、可还原快照的干净 Windows 虚拟机；不要在有真实 LoreDock 数据的开发机上运行安装/卸载脚本。MSI 和 NSIS 各从独立干净快照开始，先下载对应 tag 的安装包，并在虚拟机中取得同 tag 的仓库脚本。

在 PowerShell 中分别执行（路径替换为虚拟机内的实际下载位置）：

```powershell
./scripts/test-windows-installer.ps1 -InstallerType msi -CurrentInstaller 'C:\Temp\LoreDock_0.1.0_x64_en-US.msi' -AcknowledgeDisposableMachine
./scripts/test-windows-installer.ps1 -InstallerType nsis -CurrentInstaller 'C:\Temp\LoreDock_0.1.0_x64-setup.exe' -AcknowledgeDisposableMachine
```

脚本验证安装登记、启动、卸载后数据标记保留及无残留进程。还需人工检查首次启动、主要页面和卸载入口。覆盖升级测试需要**旧版与新版两个不同安装包**；首个 tag 只有一个版本，不得用同版本重装冒充升级验收。得到下一版后，从旧版安装快照分别传入 `-PreviousInstaller` 与 `-CurrentInstaller` 执行脚本，再记录结果、Windows 版本、安装包版本及失败截图。

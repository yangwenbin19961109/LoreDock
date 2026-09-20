# 第三方依赖与素材许可证记录

本文件记录 LoreDock 源码仓库及当前 Windows 本地版直接使用的第三方依赖、模型和素材。精确的完整依赖树仍以 `pnpm-lock.yaml`、`core/uv.lock` 与 `apps/desktop/src-tauri/Cargo.lock` 为准。

版本号是 2026-09-18 对当前锁文件的核对结果。升级锁文件后应同步更新本表。只有通过包管理器安装、未复制进仓库的依赖，不等同于仓库内重新分发了其源码；构建并分发安装包时，仍须按实际打包内容保留上游要求的许可证与声明。

## 项目许可证

LoreDock 当前使用 [PolyForm Noncommercial License 1.0.0](../LICENSE.md)。该许可证允许公开源码、修改和非商业使用，但不是 OSI 批准的开源许可证。除非项目负责人更换许可证，项目对外应称为“源码可用”或“源码公开的非商业项目”，不应称为“开源项目”。

## Python 运行时

| 依赖 | 锁定版本 | 用途 | 来源 | 上游许可证 |
| --- | ---: | --- | --- | --- |
| FastAPI | 0.141.1 | HTTP API | [fastapi/fastapi](https://github.com/fastapi/fastapi) | MIT |
| HTTPX | 0.28.1 | HTTP 与 MCP bridge 请求 | [encode/httpx](https://github.com/encode/httpx) | BSD-3-Clause |
| keyring | 25.7.0 | 系统凭据存储 | [jaraco/keyring](https://github.com/jaraco/keyring) | MIT |
| lxml | 6.1.2 | DOCX/PPTX/XLSX XML 解析 | [lxml/lxml](https://github.com/lxml/lxml) | BSD-3-Clause |
| MCP Python SDK | 1.29.1 | 本地 stdio MCP bridge | [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) | MIT |
| NumPy | 2.5.2 | ONNX 张量、池化和归一化 | [numpy/numpy](https://github.com/numpy/numpy) | BSD-3-Clause；发行包还包含其元数据列出的 0BSD、MIT、Zlib、CC0-1.0 组件 |
| ONNX Runtime | 1.29.0 | 本地 Embedding 推理 | [microsoft/onnxruntime](https://github.com/microsoft/onnxruntime) | MIT |
| Pydantic | 2.13.5 | API 与进程边界数据校验 | [pydantic/pydantic](https://github.com/pydantic/pydantic) | MIT |
| pydantic-settings | 2.15.0 | Core 配置校验 | [pydantic/pydantic-settings](https://github.com/pydantic/pydantic-settings) | MIT |
| pypdf | 6.16.2 | PDF 文本解析 | [py-pdf/pypdf](https://github.com/py-pdf/pypdf) | BSD-3-Clause |
| python-docx | 1.2.0 | DOCX 文本解析 | [python-openxml/python-docx](https://github.com/python-openxml/python-docx) | MIT |
| python-multipart | 0.0.32 | 文件上传表单解析 | [Kludex/python-multipart](https://github.com/Kludex/python-multipart) | Apache-2.0 |
| sqlite-vec | 0.1.9 | SQLite 向量检索扩展 | [asg017/sqlite-vec](https://github.com/asg017/sqlite-vec) | MIT OR Apache-2.0 |
| Hugging Face Tokenizers | 0.23.1 | 本地模型分词 | [huggingface/tokenizers](https://github.com/huggingface/tokenizers) | Apache-2.0 |
| Uvicorn | 0.52.4 | 本地 ASGI 服务 | [encode/uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause |

## Web 运行时

工作区内的 `@loredock/contracts` 与 `@loredock/ui` 是 LoreDock 自有代码，不作为第三方依赖列出。

| 依赖 | 锁定版本 | 用途 | 来源 | 上游许可证 |
| --- | ---: | --- | --- | --- |
| `@tauri-apps/api` | 2.11.1 | Web 与桌面壳交互 | [tauri-apps/tauri](https://github.com/tauri-apps/tauri) | MIT OR Apache-2.0 |
| React | 19.2.8 | UI | [facebook/react](https://github.com/facebook/react) | MIT |
| React DOM | 19.2.8 | UI 渲染 | [facebook/react](https://github.com/facebook/react) | MIT |
| Scheduler | 0.27.0 | React DOM 运行时依赖 | [facebook/react](https://github.com/facebook/react) | MIT |

Vite、TypeScript、Vitest、Playwright、ESLint 和 Prettier 只参与开发、测试或构建，不作为应用运行时依赖列入本表。若将其本体随发行物重新分发，应另行保留对应声明。

## 桌面运行时

| 依赖 | 锁定版本 | 用途 | 来源 | 上游许可证 |
| --- | ---: | --- | --- | --- |
| Serde | 1.0.229 | Rust 数据序列化 | [serde-rs/serde](https://github.com/serde-rs/serde) | MIT OR Apache-2.0 |
| serde_json | 1.0.151 | JSON 处理 | [serde-rs/json](https://github.com/serde-rs/json) | MIT OR Apache-2.0 |
| Tauri | 2.11.5 | 桌面壳 | [tauri-apps/tauri](https://github.com/tauri-apps/tauri) | MIT OR Apache-2.0 |
| tauri-build | 2.6.3 | 桌面构建 | [tauri-apps/tauri](https://github.com/tauri-apps/tauri) | MIT OR Apache-2.0 |
| UUID | 1.26.0 | 运行标识生成 | [uuid-rs/uuid](https://github.com/uuid-rs/uuid) | MIT OR Apache-2.0 |

## 打包工具

| 依赖 | 锁定版本 | 用途 | 来源 | 上游许可证 |
| --- | ---: | --- | --- | --- |
| PyInstaller | 6.22.2 | 构建独立 Core 与 MCP bridge | [pyinstaller/pyinstaller](https://github.com/pyinstaller/pyinstaller) | GPL-2.0-or-later with Bootloader Exception |

PyInstaller 是构建依赖；其 bootloader exception 允许分发由 PyInstaller 构建的非自由程序。发行包仍应包含适用的 PyInstaller 版权与许可证声明。

## 运行时下载模型

模型文件不提交到仓库，也不预装在当前安装包中；用户在应用内选择安装时，Core 从下列固定来源下载。

| 模型 | 固定 revision | 下载文件 | 来源 | 上游许可证 |
| --- | --- | --- | --- | --- |
| multilingual-e5-small | `614241f622f53c4eeff9890bdc4f31cfecc418b3` | `onnx/model_qint8_avx512_vnni.onnx`、`onnx/tokenizer.json` | [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3) | MIT |

应用或文档应保留模型名称、来源链接和许可证。模型下载页给出的论文引用是推荐引用，不替代 MIT 许可证记录。

## 字体与评测资料

| 内容 | 仓库用途 | 来源 | 许可证或说明 |
| --- | --- | --- | --- |
| Noto Sans SC | `evals/fixtures/documents/recovery-guide.pdf` 中的嵌入字体子集 | [notofonts/noto-cjk](https://github.com/notofonts/noto-cjk) | SIL Open Font License 1.1 |
| Microsoft YaHei 字体名称 | DOCX 评测夹具的字体引用 | Windows 字体选择 | 字体文件未提交、未嵌入或随 LoreDock 分发 |
| `evals/fixtures/` 内的文字与 Office/PDF 测试资料 | 检索评测 | LoreDock 项目生成 | 由项目许可证覆盖；PDF 中的 Noto 字体子集按上项处理 |

## 项目图标与图片

项目负责人于 2026-09-20 确认：下列图标、UI mockup 和测试图片均为 LoreDock 项目专门生成，并非从第三方素材网站复制。它们作为 LoreDock 自有素材，由项目的 [PolyForm Noncommercial License 1.0.0](../LICENSE.md) 覆盖。

- `assets/loredock-icon-1024.png`
- `assets/loredock-icon-source.png`
- `assets/loredock-octopus-icon-1024.png`
- `assets/loredock-octopus-icon.svg`
- `assets/mockups/loredock-main-library-ui-v1.png`
- `apps/web/public/loredock-icon.png`
- `apps/desktop/src-tauri/icons/` 下由项目图标生成的各平台尺寸文件
- `apps/web/e2e/fixtures/folder-import/cover.png`

## 发布检查结论

- 当前直接依赖和运行时下载模型均能定位到上游来源及许可证，未发现与 PolyForm Noncommercial 项目分发直接冲突的许可证。
- 项目负责人已确认项目图标与图片为 LoreDock 专门生成的自有素材，并决定保留 PolyForm Noncommercial，不将项目称为 OSI 定义下的开源软件。
- 后续 Windows 构建已增加 `scripts/generate-windows-notices.py`，从本地锁定依赖树收集可读取的声明文本并随包提供，同时单列缺失项；详见 [Windows 预览版发布核查](windows-preview-release-checklist.md)。当前仍有未决声明文本和实际打包内容复核，本文件的直接依赖表及自动收集结果都不能单独证明完整合规。已发布的 `v0.1.0-preview.1` 安装包未包含这一新增收集结果。
- 不要把依赖缓存、下载模型、私人资料、数据库、日志或凭据提交到仓库。

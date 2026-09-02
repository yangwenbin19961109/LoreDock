# Phase 0 依赖与许可证记录

本表记录 Phase 0 的直接生产依赖。精确解析版本由 `pnpm-lock.yaml`、`core/uv.lock` 与 `Cargo.lock` 固定。

| 生态 | 依赖 | 用途 | 上游许可证 |
| --- | --- | --- | --- |
| Python | FastAPI | HTTP API | MIT |
| Python | Pydantic / pydantic-settings | 配置与契约校验 | MIT |
| Python | Uvicorn | ASGI 服务 | BSD-3-Clause |
| Python | pypdf | PDF 文本解析 | BSD-3-Clause |
| Python | python-docx / lxml | DOCX 文本解析 | MIT / BSD-3-Clause |
| Python | sqlite-vec | SQLite 向量检索扩展 | MIT OR Apache-2.0 |
| Python | ONNX Runtime | 本地 Embedding 模型推理 | MIT |
| Python | NumPy | ONNX 张量、池化和归一化 | BSD-3-Clause |
| Python | Hugging Face Tokenizers | 本地模型分词 | Apache-2.0 |
| Web | React / React DOM | UI | MIT |
| Web | Vite | Web 构建 | MIT |
| Desktop | Tauri | 桌面壳 | MIT OR Apache-2.0 |
| Packaging | PyInstaller | 将 Python Core 构建为独立桌面 sidecar；仅开发依赖 | GPL-2.0-or-later with Bootloader Exception |
| Evaluation asset | Noto Sans SC | 评测 PDF 内嵌字体子集 | SIL Open Font License 1.1 |

引入新依赖时必须记录来源、用途和许可证，并由依赖审查工作流检查已知漏洞与许可证变化。不得加入与项目非商业许可证或分发目标冲突的依赖。

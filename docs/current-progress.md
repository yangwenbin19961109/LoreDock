# LoreDock 当前开发进度

- 记录日期：2026-09-03
- 当前分支：`main`
- 当前里程碑：Phase 2.5 主路径完成，Phase 3 前十二批完成，安全富文档预览与明暗主题走查已完成

## 已完成

### Core 与检索

- 知识库和资料的创建、读取、重命名、删除及完整数据清理。
- Markdown、TXT、PDF、DOCX 导入、解析、分块、持久化任务与失败重试。
- SQLite FTS5、sqlite-vec、BM25-only 降级、向量召回和 RRF 混合检索。
- Child 排名、Parent/相邻 Child 按需上下文扩展和精确引用范围。
- multilingual-e5-small INT8 ONNX 本地 Provider、模型资产安装与校验。
- 14 份资料、100 条问题的固定检索评测集和多策略对照。
- 资料列表服务端 keyset 游标分页、筛选与排序。

### Web 与桌面

- 按既有 UI 渲染图实现左侧导航、中间资料工作区、右侧预览详情的三栏界面。
- 创建、切换、重命名和删除知识库；选择、拖放、导入和删除资料。
- 混合搜索、BM25-only 开关、结果上下文展开、引用定位和原文高亮。
- 任务进度轮询、失败提示与重试。
- 资料列表服务端筛选、排序及每页 10 条游标分页。
- Tauri 自动启动 Core、动态回环端口、一次性 Bearer Token、API 版本握手和优雅关闭。
- Windows PyInstaller 独立 Core 构建及 Tauri resource 装配。
- Windows MSI 与 NSIS 本地验收包构建。
- Core 异常退出后的三次有界自动恢复、状态诊断、诊断复制和人工重启。
- Windows MSI/NSIS 的一次性虚拟机验收脚本和人工验收矩阵。
- Core 持久化的首次启动状态、明暗主题和默认搜索方式，以及对应桌面设置界面。
- 默认本地模型状态、磁盘预检、固定版本下载、SHA-256 校验和启用提示。
- 持久化模型下载任务、真实字节进度、暂停、重试、进程中断恢复和 HTTP Range 断点续传。
- 保留引用偏移的结构化文档预览，以及不执行资料 HTML/脚本的安全渲染。
- `system` 主题跟随系统偏好，明暗主题三栏界面已完成真实资料视觉走查。

## 已验证

- Python：Ruff、Pyright 和 43 项 pytest 测试通过。
- Web：Prettier、ESLint、TypeScript、12 项 Vitest 测试和生产构建通过。
- Rust：`cargo check`、`cargo test` 和 Tauri Release 构建通过。
- 独立 Core：动态端口、401 鉴权、健康检查、创建知识库、Markdown 导入/索引和优雅退出通过。
- 发行目录桌面程序：确认从 Tauri resource 启动独立 `loredock-core.exe`，关闭后无残留进程。
- 故障恢复：强制终止 ready Core 后以新 PID 和动态端口恢复；持续启动失败在三次恢复后停止，无无限重启或孤儿进程。
- Windows 构建产物：MSI 和 NSIS 均成功生成；二进制产物位于 Git 忽略目录，不提交到仓库。

## 当前限制

- Phase 2.5 评测仍需从 100 条扩展到 200～500 条，并完成 1 万真实 E5 分块性能验证。
- Windows 安装包尚未完成代码签名；安装、升级、卸载和数据保留矩阵已工程化，但仍需在干净虚拟机实际执行。
- macOS、Linux 的独立 Core、桌面打包和生命周期尚未验证。
- 多模型切换与 PDF/DOCX 原始版面还原尚未实现；当前提供安全的结构化文本预览。
- MCP 与 Agent 接入仍属于 Phase 4，尚未开始实现。

## 下一步执行顺序

1. 在干净 Windows 虚拟机运行现有 MSI/NSIS 验收脚本，记录安装、升级、卸载与用户数据保留结果，再规划代码签名。
2. 完成 Phase 3 剩余安装与跨平台验收；代码侧下一阶段进入 Phase 4 只读 MCP 契约与服务实现。
3. 并行补齐 Phase 2.5 的 200～500 条评测集和 1 万真实 E5 分块性能报告。
4. Phase 3 达到首次验收门槛后进入 Phase 4，实现只读 MCP 工具和 Codex/Cursor 接入向导。

详细设计和验收条件以 [技术架构](technical-architecture.md)、[开发计划](development-plan.md)、[Phase 2.5 交付记录](phase-2.5-delivery.md)和 [Phase 3 交付记录](phase-3-delivery.md)为准。

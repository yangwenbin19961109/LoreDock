# LoreDock 当前开发进度

- 记录日期：2026-09-02
- 当前分支：`main`
- 当前里程碑：Phase 2.5 主路径完成，Phase 3 前六批完成，Windows 本地验收包可构建

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

## 已验证

- Python：Ruff、Pyright 和 34 项 pytest 测试通过。
- Web：Prettier、ESLint、TypeScript、7 项 Vitest 测试和生产构建通过。
- Rust：`cargo check`、`cargo test` 和 Tauri Release 构建通过。
- 独立 Core：动态端口、401 鉴权、健康检查、创建知识库、Markdown 导入/索引和优雅退出通过。
- 发行目录桌面程序：确认从 Tauri resource 启动独立 `loredock-core.exe`，关闭后无残留进程。
- Windows 构建产物：MSI 和 NSIS 均成功生成；二进制产物位于 Git 忽略目录，不提交到仓库。

## 当前限制

- Phase 2.5 评测仍需从 100 条扩展到 200～500 条，并完成 1 万真实 E5 分块性能验证。
- Core 意外崩溃后还不会自动恢复，界面诊断信息也不够具体。
- Windows 安装包尚未完成代码签名及干净虚拟机上的安装、升级、卸载和数据保留矩阵。
- macOS、Linux 的独立 Core、桌面打包和生命周期尚未验证。
- 模型管理、常规设置、深色主题和富文档版面预览尚未实现。
- MCP 与 Agent 接入仍属于 Phase 4，尚未开始实现。

## 下一步执行顺序

1. 为 Tauri Core 进程增加有界自动恢复：只处理异常退出，限制重启次数并使用退避，正常退出不重启。
2. 增加桌面运行状态契约：`starting`、`ready`、`recovering`、`failed`，并向 Web UI 暴露稳定错误码和可理解诊断。
3. 增加“重新启动 Core”人工恢复入口和诊断信息复制能力，同时避免输出一次性令牌、完整路径和私人内容。
4. 添加 Rust 生命周期单元测试与 Windows 崩溃恢复烟雾测试，确认不会产生孤儿进程或无限重启。
5. 在干净 Windows 虚拟机完成 MSI/NSIS 安装、升级、卸载与用户数据保留测试，再规划代码签名。
6. 并行补齐 Phase 2.5 的 200～500 条评测集和 1 万真实 E5 分块性能报告。
7. Phase 3 达到首次验收门槛后进入 Phase 4，实现只读 MCP 工具和 Codex/Cursor 接入向导。

详细设计和验收条件以 [技术架构](technical-architecture.md)、[开发计划](development-plan.md)、[Phase 2.5 交付记录](phase-2.5-delivery.md)和 [Phase 3 交付记录](phase-3-delivery.md)为准。

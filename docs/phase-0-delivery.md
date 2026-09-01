# Phase 0 交付记录

## 已完成

- pnpm Monorepo：`apps/web`、`apps/desktop`、`packages/ui`、`packages/contracts`。
- Python Core：FastAPI 应用、环境配置、安全的本地监听约束、版本化健康接口。
- 领域契约：Library、Source、Artifact、Chunk、Job、ModelProfile。
- API 契约：`/api/v1` 版本规则、统一错误结构和游标分页结构。
- React Web：设计 Token、共享 Button、Core 连通状态和 Phase 0 应用壳。
- Tauri 2：Windows、macOS、Linux 桌面壳配置与原生图标资源。
- 质量门禁：Prettier、ESLint、TypeScript、Vitest、Playwright、Ruff、Pyright、Pytest、rustfmt、Clippy。
- CI：Web/Core 检查、三桌面平台 Tauri 编译、依赖漏洞与许可证审查。
- 工程决策：四项首批 ADR、依赖许可证记录和检索评测数据 Schema。
- 可复现环境：Node、Python、Rust 版本文件，以及 pnpm、uv、Cargo 锁文件。

## Phase 0 验证命令

```powershell
./scripts/check.ps1
```

首次拉取仓库时先运行：

```powershell
./scripts/bootstrap.ps1
```

## 有意留到后续阶段的内容

- Core sidecar 的打包、随机端口、一次性令牌和生命周期管理在桌面集成阶段实现。
- SQLite schema、解析器和检索实现从 Phase 1 的实验结果反推，不在 Phase 0 提前固化。
- Docker、远程认证和 Streamable HTTP MCP 属于服务器阶段。
- 项目不提供移动端应用或移动端构建目标。

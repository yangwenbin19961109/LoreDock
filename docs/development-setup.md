# LoreDock 开发环境

## 1. 基础工具

- Node.js 22
- pnpm 11
- Python 3.12
- uv
- Rust 1.97.1（包含 rustfmt 与 clippy）

Windows 桌面构建还需要 Microsoft C++ Build Tools 与 WebView2；macOS 需要 Xcode Command Line Tools；Linux 需要 Tauri 对应的 WebKitGTK 系统依赖。

## 2. 初始化

Windows PowerShell：

```powershell
./scripts/bootstrap.ps1
```

macOS / Linux：

```sh
./scripts/bootstrap.sh
```

## 3. 本地开发

分别启动 Core 与 Web：

```powershell
pnpm dev:core
pnpm dev
```

启动 Tauri 桌面壳：

```powershell
pnpm dev:desktop
```

Core 默认监听 `127.0.0.1:49321`。该端口仅用于开发；正式桌面版由壳层选择空闲端口并通过一次性令牌约束本机访问。

## 4. 质量检查

Windows：

```powershell
./scripts/check.ps1
```

macOS / Linux：

```sh
./scripts/check.sh
```

检查内容包括格式、ESLint、TypeScript、Vitest、Ruff、Pyright、Pytest、rustfmt 与 Clippy。

## 5. 工程边界

- `core/`：Python 业务核心、HTTP API 与未来的 MCP 服务。
- `apps/web/`：React Web 管理界面，也是桌面端的 UI 来源。
- `apps/desktop/src-tauri/`：只负责桌面生命周期、系统能力和 Core sidecar 管理。
- `packages/contracts/`：前端使用的跨进程契约与常量。
- `packages/ui/`：设计令牌和共享组件。
- `evals/`：检索质量评测数据及其 Schema。

跨边界变更必须先更新契约或 ADR，禁止让 UI 直接读写 SQLite。

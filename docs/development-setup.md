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

单独运行 Core 时默认监听 `127.0.0.1:49321`。`pnpm dev:desktop` 会自动使用仓库内的 Python 虚拟环境启动 Core，由 Tauri 选择动态回环端口、生成一次性令牌并在窗口关闭时请求优雅退出，因此无需同时执行 `pnpm dev:core`。

设置 `LOREDOCK_CORE_EXECUTABLE` 可以测试独立 Core 可执行文件。Windows 可使用以下命令构建并验证不依赖系统 Python 的 Core，以及生成包含该 Core 的 MSI 和 NSIS 安装包：

```powershell
pnpm build:core:windows
pnpm test:core:windows
pnpm build:desktop:windows
```

生成目录 `core/dist/`、`core/build/` 和 Tauri `target/` 均被 Git 忽略。安装包尚未签名，不能直接作为正式下载版本发布。

### 本地真实 Embedding

开发测试默认使用确定性哈希 Provider，保证安装和 CI 不依赖网络。需要验证真实语义检索时执行：

```powershell
python -m uv run --directory core loredock-model install-e5 --directory models/multilingual-e5-small
python -m uv run --directory core loredock-model smoke-e5 --directory models/multilingual-e5-small
$env:LOREDOCK_MODEL_DIR = "models/multilingual-e5-small"
pnpm dev:core
```

模型目录已被 Git 忽略。Core 启用真实模型后，Embedding 标识或维度变化会触发派生索引重建。

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

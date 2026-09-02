<p align="center">
  <img src="assets/loredock-icon-1024.png" width="128" height="128" alt="LoreDock icon">
</p>

# LoreDock（知坞）

LoreDock 是一个轻量、本地优先的个人知识库。它帮助普通用户导入、整理和检索资料，并通过 MCP 将可信、可引用的知识连接到 Codex、Cursor 等 AI Agent。

> A lightweight, local-first knowledge hub with hybrid search and MCP access for AI agents.

## 产品目标

- 对非技术用户提供开箱即用的知识库管理体验。
- 支持 Windows、macOS、Linux，以及服务器 Web 部署。
- 默认本地存储、离线可用，用户拥有原始资料和索引。
- 通过全文检索、向量召回和可选重排兼顾速度与准确率。
- 通过标准 MCP 接口连接不同 Agent，避免绑定单一模型或客户端。

## 规划中的形态

- 桌面端：Tauri + React，内置 LoreDock Core。
- 服务器端：Docker 部署，浏览器管理，多设备访问。
- Agent 接入：本地 stdio MCP 与远程 Streamable HTTP MCP。

## 文档

- [技术架构与开发方案](docs/technical-architecture.md)
- [分阶段开发计划](docs/development-plan.md)
- [当前开发进度与下一步](docs/current-progress.md)
- [开发环境与质量检查](docs/development-setup.md)
- [HTTP API 契约](docs/api-contracts.md)
- [架构决策记录](docs/decisions/README.md)

## 品牌资源

- `assets/loredock-icon-source.png`：批准版本的原始尺寸透明 PNG。
- `assets/loredock-icon-1024.png`：项目主用的 1024 × 1024 透明 PNG。

## 当前状态

Phase 0～2 Core 闭环和 Phase 2.5 分层混合检索主路径已经完成。Phase 3 已完成前七批：三栏知识库 UI、资料管理与搜索、服务端游标分页、Tauri Core 生命周期、有界异常恢复与诊断，以及 Windows 独立 Core、MSI 和 NSIS 本地验收包构建。下一步是安装升级矩阵和剩余桌面产品化体验；安装包签名、跨平台验证和 MCP 接入尚未完成。

初始化开发环境：

```powershell
./scripts/bootstrap.ps1
```

运行完整质量检查：

```powershell
./scripts/check.ps1
```

## 许可协议

LoreDock 以 [PolyForm Noncommercial License 1.0.0](LICENSE.md) 提供源码，仅授权非商业用途。个人学习、研究、实验和业余项目可以使用、修改和分发；商业使用需要另行取得授权。

由于该协议限制商业用途，LoreDock 属于“源码可用（source-available）”项目，不属于 OSI 定义下的开源软件。

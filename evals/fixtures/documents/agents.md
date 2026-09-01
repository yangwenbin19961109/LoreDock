# Agent 接入

LoreDock 计划通过标准 MCP 协议连接 Codex、Cursor 等 Agent。默认 MCP 工具只读，并对返回内容设置边界。

本地 MCP 使用 stdio bridge 或仅监听回环地址的 Core 连接。远程 MCP 必须启用 HTTPS 和身份认证。

# Phase 2 Core MVP 交付记录

## 已完成的 Core 闭环

LoreDock Core 现在可以完全通过 `/api/v1` 完成：

1. 创建、列出、读取、重命名和删除知识库。
2. 上传 Markdown、TXT、PDF、DOCX，并限制单文件最大 100 MiB。
3. 复制原始资料、计算 SHA-256、检测同库重复内容。
4. 解析、结构化分块、生成稳定 Chunk ID 和精确引用位置。
5. 写入每库独立的 SQLite FTS5 与 sqlite-vec 索引。
6. 执行 BM25 + Vector + RRF 或 BM25-only 检索。
7. 按字符范围读取解析后的来源内容。
8. 同步删除来源副本、解析产物、Chunk、FTS 和向量。
9. 持久化任务状态、进度、尝试次数、租约和 heartbeat。
10. Core 重启时把中断任务恢复为明确失败，并允许有限重试。

## 存储布局

```text
data/
├── app.sqlite
└── libraries/{library_id}/
    ├── raw/{source_id}.{ext}
    ├── artifacts/{source_id}.txt
    ├── index.sqlite
    └── manifest.json
```

`app.sqlite` 使用 schema version 2。Phase 2 交付时索引使用 build contract version 2；Phase 2.5 已将派生索引升级至 version 3。不同维度或模型不能混用，旧索引通过旁路重建后原子切换。

## 当前实现边界

- 上传请求目前同步完成索引，同时写入完整 Job 状态。后台 worker 调度可在不改变 API 契约的情况下接入。
- 默认仍使用 Phase 1 的确定性哈希向量提供器，因此工程闭环可离线验证，但不能视为最终语义模型。
- 管理 UI、拖放导入和任务进度页面属于 Phase 3。
- MCP 接入属于 Phase 4。

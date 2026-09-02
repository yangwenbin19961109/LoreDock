# LoreDock 技术架构与开发方案

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 产品名称 | LoreDock（知坞） |
| 产品定位 | 面向普通用户、可供 AI Agent 使用的本地优先知识中心 |
| 文档状态 | 初始技术方案 |
| 目标阶段 | 检索原型、桌面 MVP、服务器版本 |

## 2. 设计目标

LoreDock 不只是一个向量数据库管理界面，而是资料从导入、解析、索引、检索、引用到 Agent 接入的完整产品。

核心目标：

1. **轻量**：个人版不要求用户安装数据库、Python、Docker或模型服务。
2. **准确**：默认采用全文与向量混合召回，可选 Reranker，并始终返回来源定位。
3. **本地优先**：原始资料和索引默认保存在用户设备，离线仍可检索。
4. **跨平台**：桌面端覆盖 Windows、macOS、Linux；服务器端支持 Docker 和浏览器访问。
5. **开放**：通过 MCP 和 HTTP API 服务不同 Agent，不绑定特定客户端或模型提供商。
6. **可演进**：SQLite 是默认实现，但文档解析、模型、向量索引和存储均通过接口隔离。

## 3. 非目标

首个 MVP 暂不实现：

- 企业级多租户和复杂组织权限。
- 知识图谱自动构建。
- 百万级以上分块的单机向量服务。
- 多人实时协同编辑。
- iOS、Android 或其他移动端客户端。
- Agent 对知识库的任意写入权限。

## 4. 总体架构

```text
┌──────────────────────────────────────────────────────────┐
│                    LoreDock Clients                      │
│          Desktop (Tauri)          Web Browser            │
└───────────────────┬───────────────────┬──────────────────┘
                    │                   │
                    └────── HTTP API ───┘
                                │
┌───────────────────────────────▼──────────────────────────┐
│                    LoreDock Core                         │
│  Library │ Ingestion │ Search │ Models │ Jobs │ MCP/API │
└──────┬──────────┬─────────┬────────┬────────┬────────────┘
       │          │         │        │        │
       ▼          ▼         ▼        ▼        ▼
  Raw files   Parsers   SQLite    ONNX/API  MCP clients
                        FTS5 +
                        sqlite-vec
```

桌面端通过 Tauri sidecar 启动本地 Core；服务器端在 Docker 中运行相同 Core，并由浏览器访问 Web 管理界面。项目不开发或维护移动端客户端。

## 5. 技术选型

### 5.1 应用层

| 模块 | 首选技术 | 原因 |
|---|---|---|
| Web UI | React + TypeScript + Vite | 生态成熟、组件丰富、可复用到桌面端 |
| 桌面外壳 | Tauri 2 | 安装包和运行内存低于 Electron，系统能力完整 |
| 核心服务 | Python 3.12 + FastAPI + Pydantic | RAG、文档解析和模型生态成熟，迭代速度快 |
| 服务器部署 | Docker Compose | 普通用户和轻量服务器易部署 |

Python Core 以独立进程运行，桌面端不要求系统预装 Python。发行包使用 PyInstaller 或 Nuitka 构建平台专属 sidecar，并只携带 ONNX Runtime，避免打包完整 PyTorch。

### 5.2 数据与检索

| 模块 | 首选技术 | 说明 |
|---|---|---|
| 业务数据 | SQLite + WAL | 零运维、事务可靠、便于备份 |
| 全文检索 | SQLite FTS5 | BM25、前缀和短语检索 |
| 中文检索 | Unicode 规范化 + CJK 分词/字符 n-gram | 补足默认 tokenizer 的中文能力 |
| 向量检索 | sqlite-vec | 本地零服务；通过适配器隔离其 pre-v1 API |
| 向量距离 | Cosine | 与主流文本 Embedding 模型匹配 |
| 任务系统 | SQLite 持久化任务表 | 支持崩溃恢复、进度展示和幂等重试 |

推荐每个知识库使用独立目录：

```text
libraries/{library_id}/
├── raw/                 # 用户导入的原始资料或可信副本
├── artifacts/           # Markdown、OCR、缩略图等衍生文件
├── index.sqlite         # 分块、FTS、向量和索引元数据
└── manifest.json        # 构建契约与版本信息
```

主应用另有一个 `app.sqlite`，存放知识库列表、设置、模型配置和任务摘要。原始资料是事实来源；`artifacts` 和 `index.sqlite` 均应可重建。

### 5.3 模型

提供面向普通用户的预设，而不是直接暴露复杂模型参数：

| 模式 | Embedding | 维度 | Reranker | 场景 |
|---|---|---:|---|---|
| 快速 | multilingual-e5-small INT8 ONNX | 384 | 无 | 普通电脑、默认本地模式 |
| 均衡 | BGE-M3 ONNX | 1024 | 可选 | 中文、多语言、长文档 |
| 高精度 | BGE-M3 或云端模型 | 1024 | bge-reranker-v2-m3 | 服务器或高性能设备 |

模型不能只保存显示名称。每个索引必须持久化以下构建契约：

```json
{
  "embedding_model": "intfloat/multilingual-e5-small",
  "model_checksum": "...",
  "dimensions": 384,
  "distance": "cosine",
  "normalize": true,
  "query_prefix": "query: ",
  "document_prefix": "passage: ",
  "chunker_version": 1,
  "index_schema_version": 1
}
```

更换模型、维度、归一化规则或关键分块算法时必须重建索引。产品应在后台建立新索引，完成验证后原子切换，避免搜索长时间不可用。

## 6. 文档摄取管线

```text
导入来源
  → 保存原件/网页快照
  → 类型识别与安全检查
  → 提取结构化文本
  → 清洗与规范化
  → 按标题/段落/页码分块
  → 生成 Embedding
  → 单文档事务写入 FTS 与向量
  → 完整性检查
  → 标记 ready
```

首批支持格式：Markdown、TXT、PDF、DOCX、PPTX、XLSX、HTML、URL 和纯文本笔记。扫描 PDF 的 OCR 作为可选能力，避免拖慢基础安装包。

任务状态建议：

```text
pending → snapshotting → parsing → chunking → embedding → ready
                                      └───────────────→ failed
任意状态 → deleting → removed
```

任务必须具备：

- 持久化状态与进度。
- 内容 hash 去重。
- 同一来源重复导入的冲突策略。
- 单文档更新事务。
- 崩溃后的安全恢复。
- 用户可理解的错误信息和重试入口。
- 删除原件、衍生物、FTS 与向量的完整清理。

## 7. 分块策略

默认使用结构感知分块：

1. 优先保留 Markdown 标题、段落、列表、表格和代码块边界。
2. 超长段落再按句子和 token 数切分。
3. 保存标题路径、页码、字符偏移和前后相邻块 ID。
4. 默认目标约 400～700 tokens，重叠 10%～15%，实际参数由评测确定。
5. 表格、代码和问答数据使用专用策略，不强行套用普通段落分块。

每个检索单元至少保存：

```text
chunk_id, source_id, content_hash, text, title_path,
page, char_start, char_end, previous_id, next_id, metadata
```

### 7.1 父子上下文模型

混合索引与父子索引解决不同问题，不能互相替代：混合索引负责提高召回质量，父子结构负责在命中后补足上下文。LoreDock 采用“子块参与排名、父块按需返回”的组合方式，不默认对整份文件生成父向量。

```text
Source
└── Parent Section
    ├── Child Chunk 1
    ├── Child Chunk 2
    └── Child Chunk 3
```

- Parent 是可重建的章节、页面组、表格、代码作用域、问答单元或消息会话，不是新的事实来源。
- Child 是 FTS5 与向量召回的主要检索单元，保留较小粒度和精确引用。
- Parent 保存完整上下文范围；Child 保存 `parent_id`、顺序和相邻关系。
- 短笔记和天然完整的问答可以只有一个 Child，不强制制造父层级。
- 整份文件通常过大且主题过多，不作为默认 Parent 返回，也不建立默认父向量。

建议的可重建索引结构：

```text
parents:
  parent_id, source_id, kind, title_path,
  char_start, char_end, page_start, page_end, metadata

chunks:
  chunk_id, parent_id, source_id, ordinal,
  previous_id, next_id, content_hash, text,
  char_start, char_end, page, title_path, metadata
```

引入该结构时必须提升 index build contract 版本并重建索引，不能让缺少父子字段的旧索引与新查询逻辑混用。

## 8. 检索管线

```text
用户查询
  ├── FTS5 / BM25 候选 40～80
  └── 向量候选 40～80
             ↓
       Reciprocal Rank Fusion
             ↓
    来源过滤、Child 去重与分组
             ↓
  按需扩展 Parent 或相邻 Child
             ↓
   可选 Reranker / 上下文裁剪
             ↓
 返回命中 Child、上下文与精确引用
```

设计原则：

- 永远保留 BM25-only 降级路径。
- 使用 RRF 融合不同分数量纲，初始权重向量 0.5、BM25 0.5。
- Reranker 失败时返回融合结果，不让整个搜索失败。
- 查询先按知识库、路径、类型、时间、标签等元数据过滤。
- 对同一来源连续命中的分块执行相邻上下文扩展。
- 不把相似度分数直接解释为概率。

### 8.1 上下文扩展规则

扩展必须发生在 Child 排名之后，不能用更大的 Parent 文本替换原始匹配分数：

1. FTS5 与向量分别召回 Child，并通过 RRF 融合。
2. 对相同 `chunk_id` 去重，并按 `source_id + parent_id` 分组。
3. 命中内容已经完整时，只返回 Child。
4. 命中位于句子、列表、表格或代码边界时，扩展前后相邻 Child。
5. 同一 Parent 有多个连续 Child 进入高位结果时，合并为 Parent 或连续范围。
6. Parent 超过上下文预算时，只保留命中 Child、必要邻块和标题路径。
7. Reranker 只处理数量受限的融合候选；失败时继续返回融合与扩展结果。

首次搜索结果必须区分“参与排名的内容”和“最终返回的上下文”：

```json
{
  "matched_chunk_id": "child-id",
  "context_id": "parent-or-range-id",
  "source_id": "source-id",
  "matched_range": { "char_start": 1200, "char_end": 1680 },
  "context_range": { "char_start": 800, "char_end": 2400 },
  "title_path": ["检索", "故障降级"]
}
```

MCP 首次搜索默认返回紧凑 Child 与有限邻块，并提供继续读取 Parent 或来源范围的句柄，避免一次返回整篇长文档。桌面 UI 可以先展示命中 Child，高亮 `matched_range`，用户展开时再读取 `context_range`。

### 8.2 按资料类型选择层级策略

| 资料类型 | 检索与上下文策略 |
|---|---|
| 短笔记 | 混合检索 Child，不强制创建 Parent |
| FAQ | 一个问答作为 Parent/Child 单元，通常不扩展 |
| Markdown 技术文档 | 标题章节为 Parent，段落组为 Child |
| PDF、DOCX | 章节或页面组为 Parent，段落为 Child |
| 表格 | 整表或逻辑区域为 Parent，行组为 Child |
| 代码 | 文件、类或函数为 Parent，语义代码块为 Child |
| 聊天记录 | 会话或话题窗口为 Parent，消息窗口为 Child |

父子策略必须通过固定评测集比较，而不是默认扩大上下文。除 Recall@K、MRR 和引用正确率外，还要记录 context precision、平均返回 tokens、重复率、扩展延迟和 Agent 任务成功率。

## 9. SQLite 规模策略

SQLite 是个人版与轻量服务器版的默认实现：

- 10 万分块以内作为首个重点目标。
- 10 万～50 万分块必须进行目标设备基准测试并依赖过滤和分库。
- 超过预设阈值时提示拆分知识库或使用服务器向量后端。
- 百万级分块或较高并发通过 `VectorIndex` 适配器切换 Qdrant 等服务。

核心接口示例：

```python
class VectorIndex(Protocol):
    def upsert(self, records: Sequence[VectorRecord]) -> None: ...
    def delete_by_source(self, source_id: str) -> None: ...
    def search(self, query: VectorQuery) -> list[VectorHit]: ...
    def rebuild(self) -> None: ...
```

首个版本实现 `SQLiteVectorIndex`，服务器规模版可增加 `QdrantVectorIndex`，业务层不感知具体后端。

## 10. MCP 设计

首个版本仅提供只读工具：

| Tool | 用途 |
|---|---|
| `search_knowledge` | 混合检索一个或多个知识库 |
| `read_source` | 按来源和定位读取原文 |
| `list_libraries` | 列出 Agent 可访问的知识库 |
| `list_sources` | 浏览知识库资料 |
| `get_source_info` | 获取来源、状态和元数据 |
| `get_index_status` | 检查索引是否就绪 |

本地桌面端提供 stdio MCP bridge，连接本机 Core；远程服务器采用 Streamable HTTP、HTTPS 和 OAuth 2.1。MCP 响应必须包含稳定 ID、来源标题、定位信息和可继续读取原文的参数。

写入、删除和刷新工具后续按能力授权单独开放，不与只读权限混合。

## 11. API 与模块边界

建议的 Python 包结构：

```text
src/loredock/
├── api/                 # HTTP API 与 DTO
├── mcp/                 # MCP tools、resources、transports
├── domain/              # Library、Source、Chunk、Job 实体
├── application/         # 用例和编排
├── ingestion/
│   ├── parsers/
│   ├── chunkers/
│   └── pipeline.py
├── retrieval/
│   ├── lexical.py
│   ├── vector.py
│   ├── fusion.py
│   └── rerank.py
├── models/              # Embedding/Reranker providers
├── storage/             # SQLite repositories 与 migrations
├── jobs/                # 持久化任务执行器
└── security/
```

模块之间使用明确接口：

- `DocumentParser`
- `Chunker`
- `EmbeddingProvider`
- `Reranker`
- `VectorIndex`
- `KnowledgeRepository`
- `SearchPipeline`
- `McpToolService`

禁止 API 层直接操作 SQLite 或模型，禁止检索模块直接依赖某个云模型提供商。

## 12. 安全与隐私

- 默认绑定 `127.0.0.1`，不自动暴露局域网端口。
- API Key 使用系统钥匙串；服务器使用加密密钥存储。
- 所有相对路径在访问文件系统前执行规范化和根目录约束。
- 限制上传大小、压缩包展开大小、URL 重定向与内网访问，防范 zip bomb 和 SSRF。
- HTML 和 Markdown 预览进行内容净化。
- MCP 工具按知识库授权，默认只读。
- 日志不得记录 API Key、完整私人文档或未脱敏查询。
- 索引删除必须覆盖原件副本、衍生文件、FTS、向量及缓存。

## 13. 备份与迁移

- 备份以原始资料、应用数据库和 manifest 为核心。
- SQLite 使用在线 backup API 或一致性快照，不能在 WAL 活跃时只复制主文件。
- 索引默认可排除并在恢复后重建；若携带索引，必须校验 schema、模型和构建契约。
- 数据格式与应用版本分离，所有 schema 使用显式版本号。
- 导出应优先提供可读的 Markdown/JSON，避免形成产品锁定。

## 14. 质量与评测

建立包含 200～500 个真实中文问题的基准集，每条记录期望来源和段落。持续测量：

- Recall@5 / Recall@10
- MRR
- nDCG@10
- 首条正确结果比例
- 来源与页码准确率
- 查询 P50 / P95 延迟
- 每秒索引分块数
- 索引大小和峰值内存
- 崩溃恢复和删除一致性

每次变更模型、分块算法、融合权重或 tokenizer，都必须跑同一评测集。模型选择以目标设备上的质量、延迟和体积综合结果为准，而不是只看公开排行榜。

## 15. 开发阶段

实施阶段以 [分阶段开发计划](development-plan.md) 为准，本文只保留架构层摘要，避免两份路线图产生不同编号。

| 阶段 | 架构目标 |
|---|---|
| Phase 0 | 建立 Monorepo、Python Core、React Web、Tauri 桌面壳、共享契约、ADR 与 CI |
| Phase 1 | 用固定基准集验证解析、分块、Embedding、混合检索及目标规模延迟 |
| Phase 2 | 实现知识库、来源、任务、SQLite 索引和可定位引用的 Core MVP |
| Phase 2.5 | 以 Child 混合召回、Parent/相邻块按需扩展完善分层上下文检索，并通过评测确定预算 |
| Phase 3 | 完成面向普通用户的 Web/桌面知识库管理体验 |
| Phase 4 | 提供本地 MCP、接入向导、权限、审计和诊断能力 |
| Phase 5 | 完成 Windows、macOS、Linux 的安装、更新、迁移和发布 |
| Phase 6 | 增加 Docker、认证与远程 Web/MCP 服务器部署 |
| Phase 7 | 在评测证明必要时优化规模、检索质量与可替换后端 |

## 16. 首个里程碑验收标准

- 新用户在不使用命令行的情况下创建知识库并导入文档。
- 1 万分块知识库在推荐设备上达到预设 P95 查询延迟。
- 基准集 Recall@10 达到项目设定目标。
- 每条结果可定位到来源文件和具体内容。
- Embedding 或 Reranker 不可用时，BM25 检索仍正常工作。
- 应用异常退出后任务不会永久卡死，也不会生成混合的新旧索引。
- Codex 与 Cursor 能通过 MCP 搜索并继续读取命中文档。
- 用户能够导出原始资料和可读元数据，删除后不残留索引内容。

## 17. 关键决策记录

| 决策 | 当前选择 | 重新评估条件 |
|---|---|---|
| 核心语言 | Python | Sidecar 打包、运行性能或桌面跨平台交付成为主要瓶颈 |
| 桌面框架 | Tauri 2 | sidecar 生命周期无法达到稳定要求 |
| 默认数据库 | SQLite | 单库规模或并发超过目标范围 |
| 默认向量引擎 | sqlite-vec | API 稳定性、性能或跨平台构建不达标 |
| 默认搜索 | BM25 + Vector + RRF | 自有评测证明其他融合方式显著更优 |
| 上下文策略 | Child 混合召回 + 按需 Parent/邻块扩展 | 固定评测证明平铺 Chunk 或其他层级方案质量更优 |
| 默认模型候选 | multilingual-e5-small INT8 | 需在 200～500 条人工集完成同设备对比后转为正式默认值；BGE-M3 仅作为质量上限候选 |

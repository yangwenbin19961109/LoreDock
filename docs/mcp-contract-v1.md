# MCP v1 兼容性基线

状态：2026-09-04 固定首版候选基线，尚未正式发布。不等于 Phase 4 全部验收通过。

## 范围与权威定义

本基线针对六个只读 MCP 工具，不是 MCP 协议版本号，也不是应用版本号。输入及结果字段、类型、必填项、默认值和约束的精确定义见 [schema 快照](../core/tests/fixtures/mcp-v1.json)，由 [兼容性测试](../core/tests/test_mcp_contract_snapshot.py) 对照当前模型和实际 SDK 工具发现检查。

当前工具发现只发布 `inputSchema`，未发布 `outputSchema`。结果模型是服务层投影，不能将快照测试描述为 bridge 已对每个成功响应执行结果 schema 校验。bridge 当前校验内部响应封装及体积；成功结果语义由服务层与集成测试保障。

## 工具与预算

| 工具 | 请求 | 成功结果与边界 |
| --- | --- | --- |
| `list_libraries` | 可选 `after_id`、`limit`（默认 20，1～50） | `items` 中为 `id/name`；`next_after_id` 为下一页游标或 null。只列授权库，按 ID 排序 |
| `search_knowledge` | 必填 `library_id/query`；`limit` 默认 8，1～10；`lexical_only` 默认 false | `items` 为带来源 ID、文本、score、引用位置及 `read_reference` 的命中；每条文本最多 1600 字符 |
| `read_source` | 必填 `library_id/source_id`；`start` 默认 0，非负；`length` 默认 4000，1～8000 | `library_id/source_id/text/char_start/char_end/next_start`；可继续读取，末尾 next_start 为 null |
| `list_sources` | 必填 `library_id`；`limit` 默认 20，1～50；可选 `cursor` | `items/next_cursor`；游标绑定知识库，不能跨库复用 |
| `get_source_info` | 必填 `library_id/source_id` | `id/library_id/name/media_type/status/size_bytes/created_at/updated_at`，不暴露内部路径或原始错误 |
| `get_index_status` | 必填 `library_id` | 来源总数及 ready/failed/pending 数量、索引存在性、模型标识、是否生产 Embedding；不是索引完整性检查 |

所有请求禁止未知字段，使用严格类型，不将字符串数字或布尔值隐式转换为整数。查询长度 1～2000；来源和知识库请求 ID 长度 1～128。精确约束以快照为准。

命中 `char_start/char_end` 表示已返回片段的半开字符范围，不是字节或 UTF-16 偏移；`matched_char_end` 保留原命中结束位置，`truncated` 表示显示文本截断。使用 `read_reference` 继续读取；来源内容更新后应重新检索，引用不是不可变历史版本。score 用于当前检索排序，不是概率或可跨模型比较的相似度百分比。

来源名最多 240 字符，media_type 最多 120，标题路径最多 8 层、每层 200 字符。内部 HTTP 请求限制 32 KiB，bridge 响应限制 512 KiB；超限返回错误而非无界全文。正文自身可能包含路径等用户文本，不承诺自动删除正文中的私人信息。

## 返回封装与错误

MCP 返回 `isError`、`structuredContent`，并在一个 text content 中提供同一数据的 JSON；错误数据固定为 `code/message`。客户端根据 code 分支，不依赖英文 message 的逐字内容。固定错误测试也验证正文、异常信息不会泄露。

- 参数与分发：`unknown_tool`、`invalid_arguments`。
- 服务：`access_denied`、`library_not_found`、`source_not_found`、`source_not_ready`、`invalid_cursor`、`invalid_query`、`invalid_range`、`internal_error`。
- bridge：`agent_auth_required`、`core_request_failed`、`response_too_large`、`core_timeout`、`core_unavailable`、`invalid_core_response`。
- 持久连接发现与凭据：`core_discovery_unavailable`、`credential_missing`、`credential_store_unavailable`。

拒绝/撤销后不可继续访问；重新创建连接或解锁凭据需由用户操作。Core 不在线时提示启动 LoreDock，不在 bridge 中自动启动或用旧结果冒充新调用。多个错误同时存在时不保证错误优先级；例如 Core 未启动时可能先返回发现失败，而非参数错误。

## 兼容性规则

1. 不删除或重命名现有工具、字段及错误码，不改变字段类型、引用语义、默认值或现有参数范围。
2. 新增可选输入、结果字段或错误码必须明确评估旧客户端；客户端应容忍未知结果字段，并为未知错误提供通用失败提示。当前内部模型的 extra-forbid 不代表外部客户端可假定永不增量扩展。
3. schema 快照变化必须进行人工差异审查，记录兼容性结论及测试证据，不可为消除失败而盲目刷新。
4. 破坏性变更需要 ADR 和迁移方案，提供版本化入口或兼容过渡期；不能只修改应用版本号后直接替换旧契约。
5. owner-only 连接管理 HTTP API 与 MCP 工具分开演进。setup 的 `configurations` 是增量字段，保留 `instructions/runtime`；它包含本机启动路径，不属于只读资料结果，也不应公开分享。

## 尚未覆盖

快照不证明模型使用效果、所有错误可达性、安装包行为或跨平台兼容。现有授权/分页/引用/重连集成测试继续保留；Cursor 实机验收暂缓，桌面手动配置与 P4-A01 复验、干净安装矩阵另见 [交付记录](phase-4-delivery.md)。

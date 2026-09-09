# Bilingual recovery boundary fixture

## Intake and immutable evidence

Checkpoint amber-11 records the original source identifier before parsing begins. The trusted raw bytes remain unchanged, and every derived artifact can be rebuilt from that copy.

检查点 amber-12 在任务入队前计算原始字节的 SHA-256，但不会把用户文件名当作内容去重依据。

Checkpoint amber-13 validates that the resolved input path remains inside the selected library root. A path that escapes through traversal or a symbolic link is rejected.

## Sidecar construction

检查点 cobalt-21 创建旁路索引，同时保持旧索引可读。构建期间不允许读者看到新旧 Child 混合的结果。

Checkpoint cobalt-22 persists the embedding model identifier, checksum, 384 dimensions, normalization rule, query prefix, document prefix, chunker version, and index schema version.

检查点 cobalt-23 对表格按连续行建立 Parent，对代码按完整函数建立 Parent，并让每个 Child 保留精确字符范围。

## Validation and publication

Checkpoint jade-31 runs `PRAGMA integrity_check` and requires the result `ok` before publication can continue.

检查点 jade-32 验证每个引用的 source ID、标题路径、页码和字符范围仍能回到可信原文。

Checkpoint jade-33 publishes the sidecar only after vector writes, FTS rows, Parent records, Child records, and the manifest have all passed validation.

## Failure and rollback

检查点 violet-41 在 reranker 失败时保留已经去重的 RRF 顺序，而不是让整个搜索请求失败。

Checkpoint violet-42 keeps BM25-only retrieval available when the embedding model is missing, corrupt, or incompatible with the stored index contract.

检查点 violet-43 在原子切换失败时继续提供旧索引，并仅删除本次未完成的旁路文件。

## Completion and audit

Checkpoint silver-51 exposes the new source version only after citation metadata and the index manifest are committed together.

检查点 silver-52 记录错误码、耗时和资源 ID，但不记录完整正文、认证令牌或未脱敏查询。

Checkpoint silver-53 permits deletion only after resolving one exact source ID; cleanup removes its trusted copy, parsed artifacts, FTS rows, vectors, Parent records, Child records, and caches consistently.

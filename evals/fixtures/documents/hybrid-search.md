# 混合检索

LoreDock 的默认检索路径结合 BM25 全文召回与向量召回，再使用 Reciprocal Rank Fusion 合并排名。默认 RRF K 为 60。

Embedding 模型不可用时，系统必须降级到 BM25-only 模式，而不是让搜索整体失败。可选 Reranker 失败时同样返回融合结果。

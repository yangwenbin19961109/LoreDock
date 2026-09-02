# 插件与路径安全代码示例

## 路径检查

下面的示例表达文件导入边界。解析后的路径必须位于知识库根目录之内：

```python
def ensure_inside_library(candidate: Path, library_root: Path) -> Path:
    resolved = candidate.resolve(strict=True)
    root = library_root.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("path_outside_library")
    return resolved
```

禁止先校验一个路径，再使用未经校验的原始字符串打开文件。符号链接和 `..` 必须在解析后的绝对路径上判断。

## RRF 融合

RRF 不要求比较 BM25 与向量分数的数值尺度。每条候选的贡献是 `1 / (k + rank)`，LoreDock 初始使用 `k = 60`。

```python
score[item] += 1.0 / (60 + rank)
```

相同候选出现在多个排名列表时贡献相加，最终再按融合分数排序。

## 失败降级

```python
try:
    return reranker.rerank(query, candidates)
except Exception:
    return candidates
```

Reranker 异常时返回已经融合的候选，不能返回空列表，也不能删除精确引用字段。

## 原子替换

新索引先写入旁路文件，完整构建并校验成功后才用 `os.replace` 切换。构建失败时删除临时派生文件，继续保留旧索引。

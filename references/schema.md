# 索引字段说明

每个 `documents` 项包含以下主要字段：

| 字段 | 含义 |
|---|---|
| `id` | 基于正文内容生成的稳定文献标识 |
| `title` | 恢复后的文献标题；无法恢复时保留文件编号 |
| `title_source` | 标题来源：`front_matter`、`label`、`heading`、`filename` 或 `filename_identifier` |
| `title_confidence` | 标题置信度：`high`、`medium` 或 `low` |
| `relative_path` | 相对于语料根目录的路径 |
| `collection` | 文献集合或期刊目录 |
| `language` | 当前索引识别出的主要语言类别 |
| `characters` | Markdown 字符数 |
| `summary` | 用于候选检索的短摘要 |

索引顶层的 `counts` 还会记录 PDF 数量、已索引 Markdown 数量、跳过原因、集合分布和估算覆盖率。

如果配置了 `report_path`，覆盖率报告会写入该路径；相对路径以配置文件所在目录为基准。

公开分发时只保留相对路径和示例数据，不要把 `absolute_path` 或包含个人机器路径的完整索引提交到仓库。

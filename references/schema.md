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

## 公开目录字段

`public-catalog.json` 的每个文献项只包含：

- `id`：由 PDF 相对路径生成的稳定标识；
- `title`、`title_source`、`title_confidence`：标题及其可靠程度；
- `collection`：文献集合或期刊目录；
- `relative_path`：语料库内部的相对文件名；
- `abstract`：明确识别出的摘要，没有则为空；
- `keywords`：明确识别出的关键词，没有则为空；
- `summary`：摘要或已标注的短 Markdown 摘录；
- `content_level`：`metadata_abstract`、`metadata_summary` 或 `metadata_only`；
- `content_note`：说明内容是正式摘要、短摘录还是仅元数据。

公开目录不包含 `absolute_path`、`text` 或 PDF 二进制内容。

公开分发时只保留相对路径和示例数据，不要把 `absolute_path` 或包含个人机器路径的完整索引提交到仓库。

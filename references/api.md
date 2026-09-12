# 文献检索 API

这是一个无第三方依赖的最小 HTTP API。它读取本地生成的 `corpus-index.json`，让获得授权的调用者远程检索你的文献库。

## 启动

本机测试：

```text
python scripts/api_server.py --index references/corpus-index.json
```

服务器部署：

```text
LIT_API_KEY=<LONG_RANDOM_SECRET> python scripts/api_server.py --host 0.0.0.0 --port 8765 --index references/corpus-index.json
```

公开目录模式（只提供标题、摘要、关键词等信息）：

```text
LIT_API_KEY=<LONG_RANDOM_SECRET> python scripts/api_server.py --host 0.0.0.0 --port 8765 --index references/corpus-index.json --catalog public-catalog.json
```

向公网开放前，应在 HTTPS 反向代理后运行，并限制来源、端口和访问频率。不要把 API Key 写入仓库、URL 或前端代码。

## 接口

### 健康检查

```text
GET /health
```

### 文献检索

```text
GET /api/v1/search?q=志愿者领导力&limit=8
```

可选参数：`collection`、`language`。

### 证据片段

```text
GET /api/v1/evidence?q=志愿者领导力&limit=5
```

在公开目录模式下，返回明确识别出的正式摘要、关键词中的证据片段和来源路径；没有摘要的文献不会被补写摘录，不返回 PDF 或完整 Markdown。

### 文献详情

```text
GET /api/v1/documents/<document-id>
```

只有启动时显式加入 `--allow-full-text`，并且调用者通过 API Key 验证后，才可以使用 `?include_text=1` 请求完整 Markdown。PDF 文件不会由此 API 直接下载。

## API 与 Skill

Skill 可以把 API 作为远程语料入口：先调用 `/search` 筛选，再调用 `/evidence` 核对正文，最后生成带来源路径的回答。API 不改变“证据不足时明确说明”的规则。

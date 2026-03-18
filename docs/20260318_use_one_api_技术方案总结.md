# Use One API 技术方案总结

## 目录

1. [背景与目标](#1-背景与目标)
2. [整体架构](#2-整体架构)
3. [配置层（config.py）](#3-配置层)
4. [GeminiProxy 服务](#4-geminiproxy-服务)
5. [DoubaoService（AI面试对话引擎）](#5-doubaoservice-ai面试对话引擎)
6. [EmbeddingService（向量生成服务）](#6-embeddingservice-向量生成服务)
7. [认证方式对比](#7-认证方式对比)
8. [环境变量配置示例](#8-环境变量配置示例)
9. [调用链路图](#9-调用链路图)
10. [注意事项与已知问题](#10-注意事项与已知问题)

---

## 1. 背景与目标

**One-API** 是一个统一的大模型 API 管理网关（开源项目），部署在 `http://104.197.139.51:3000`，对外暴露 **OpenAI 兼容接口**。  
通过它可以将后端对多个大模型（Gemini、豆包、GPT 等）的调用统一为一套标准接口，降低切换模型的成本，同时集中管理 API Key、配额、负载均衡。

**引入 One-API 的主要目的：**
- 解决 Gemini 直连限制（IP 封禁、地区访问限制）
- 统一不同模型的 API 格式，代码侵入性小
- 支持多模型热切换，仅改环境变量无需重新部署代码
- 实现 API 用量的集中监控

---

## 2. 整体架构

```
业务服务（FastAPI）
    │
    ├─ GeminiProxyClient      ──────┐
    │   (文本生成 / 图片分析)         │
    │                               ▼
    ├─ DoubaoService           One-API 网关
    │   (AI面试对话引擎)          (104.197.139.51:3000)
    │                               │
    └─ EmbeddingService             ├── Gemini Flash（文本/视觉）
        (向量化)                    ├── Gemini Embedding
                                    └── 其他模型（可扩展）
```

所有模块均通过 `USE_ONE_API` 开关控制：
- `USE_ONE_API=true`：走 One-API 网关（OpenAI 兼容格式）
- `USE_ONE_API=false`：走原有直连方式（Gemini 原生格式 / 豆包 API）

---

## 3. 配置层

**文件路径：** `AuraRecruit/backend/app/core/config.py`

### 核心配置项

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `USE_ONE_API` | `false` | 总开关，是否启用 One-API 模式 |
| `ONE_API_BASE_URL` | `http://104.197.139.51:3000/v1` | One-API 服务地址（含 `/v1` 后缀） |
| `ONE_API_KEY` | `None` | One-API 访问令牌（格式：`sk-...`） |
| `ONE_API_GEMINI_MODEL` | `gemini-3-flash-preview` | 文本任务使用的模型名 |
| `ONE_API_GEMINI_VISION_MODEL` | `gemini-3-flash-preview` | 图片分析使用的模型名 |
| `ONE_API_EMBEDDING_MODEL` | `text-embedding-004` | Embedding 模型名 |
| `EMBEDDING_PROVIDER` | `ONEAPI` | Embedding 提供商（`ONEAPI`/`GOOGLE`/`DASHSCOPE`/`OPENAI`） |

### 注意事项
- `ONE_API_KEY` 格式为 `sk-Nz1...`，与 Google 原生 Key（`AIzaSy...`）不同
- 配置通过加密文件 `.env.production.encrypted` 加载，不直接明文存储
- 启动时会校验 `GEMINI_API_KEY` 开头，`sk-Nz1`（One-API）或 `AIzaSy`（Google 直连）均可

---

## 4. GeminiProxy 服务

**文件路径：** `AuraRecruit/backend/app/services/gemini_proxy.py`

### 两种模式的实现差异

#### One-API 模式（`USE_ONE_API=true`）

使用 `openai` Python SDK，指向 One-API 的 base_url：

```python
import openai

client = openai.OpenAI(
    api_key=self.api_key,       # ONE_API_KEY
    base_url=self.api_base      # ONE_API_BASE_URL
)

# 文本生成
response = client.chat.completions.create(
    model=self.text_model,      # gemini-3-flash-preview
    messages=[{"role": "user", "content": prompt}],
    temperature=temperature,
    max_tokens=8192
)

# 图片分析（Vision）
response = client.chat.completions.create(
    model=self.vision_model,
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}}
        ]
    }],
    temperature=0.2,
    max_tokens=2000
)
```

#### 原生模式（`USE_ONE_API=false`）

使用 `requests` 库，调用 Google Generative Language API（原始格式）：

```python
# 文本：POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=API_KEY
# 图片：同上，在 parts 中携带 inline_data（base64 图片）
response = requests.post(
    f"{self.text_api_url}?key={self.api_key}",
    json={"contents": [{"parts": [{"text": prompt}]}]},
    timeout=60
)
text = result["candidates"][0]["content"]["parts"][0]["text"]
```

### 核心方法

| 方法 | 说明 |
|------|------|
| `generate_content(prompt)` | 纯文本生成（简历解析、JD 分析） |
| `analyze_image(image_bytes, mime_type)` | 图片分析（面试情绪检测） |
| `chat_completion(messages, system_prompt)` | 非流式聊天（One-API 模式专用） |
| `chat_completion_stream(messages, system_prompt)` | 流式聊天（One-API 模式专用） |

### 降级策略
- 所有调用均有 try/except
- One-API 图片分析失败时返回预设的模拟数据（模拟情绪分析结果）
- 原始模式遇到 401/403/429 时返回 mock 数据，避免前端报错

---

## 5. DoubaoService（AI面试对话引擎）

**文件路径：** `AuraRecruit/backend/app/services/doubao_service.py`

### 三种运行模式

```
DoubaoService
    ├── OneAPI 模式（推荐）: USE_ONE_API=true
    │     → 使用 Gemini 模型，Bearer Token 认证
    │     → endpoint: ONE_API_BASE_URL/chat/completions
    │
    ├── 豆包 API Key 模式: USE_ONE_API=false, DOUBAO_API_KEY 存在
    │     → Bearer Token 认证
    │     → endpoint: https://ark.cn-beijing.volces.com/api/v3/chat/completions
    │
    └── 豆包 AK/SK 模式: USE_ONE_API=false, DOUBAO_ACCESS_KEY+SECRET_KEY 存在
          → 火山引擎 HMAC-SHA256 签名认证（类 AWS SigV4 规范）
          → endpoint: 同上
```

### One-API 模式请求头

```python
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {ONE_API_KEY}"
}
```

### 请求体格式（OpenAI 兼容）

```python
{
    "model": "gemini-3-flash-preview",
    "messages": [
        {"role": "system", "content": "面试官系统提示词..."},
        {"role": "user", "content": "候选人回答..."},
        ...  # 最近10轮对话
    ],
    "temperature": 0.7,
    "max_tokens": 500,
    "stream": false  # 或 true（流式）
}
```

### 流式输出（SSE 解析）

```python
async for line in response.aiter_lines():
    if line.startswith("data: "):
        data = line[6:]
        if data == "[DONE]":
            break
        chunk = json.loads(data)
        content = chunk["choices"][0]["delta"].get("content", "")
        if content:
            yield content
```

---

## 6. EmbeddingService（向量生成服务）

**文件路径：** `AuraRecruit/backend/app/services/knowledge_base/embedding_service.py`

### 四种 Embedding 提供商

| `EMBEDDING_PROVIDER` | 模型 | 维度 | 说明 |
|---------------------|------|------|------|
| `ONEAPI`（默认） | `text-embedding-004` | 768 | 经 One-API 网关调用 Google Embedding |
| `GOOGLE` | `gemini-embedding-001` | 768 | 直连 Google API（适用于无法访问 One-API 的节点） |
| `DASHSCOPE` | `text-embedding-v4` | 768 | 阿里云百炼 |
| `OPENAI` | `text-embedding-3-small` | 1536 | OpenAI 官方 |

### ONEAPI 模式调用（OpenAI 兼容）

```python
# 端点: ONE_API_BASE_URL/embeddings
POST /v1/embeddings
Authorization: Bearer sk-...

{
    "model": "text-embedding-004",
    "input": "需要向量化的文本"
}

# 响应
{
    "data": [{"embedding": [0.1, 0.2, ...], "index": 0}],
    "usage": {"prompt_tokens": 10, "total_tokens": 10}
}
```

### GOOGLE 直连模式

```python
# 端点: generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent
POST .../embedContent?key=AIzaSy...

{
    "model": "models/gemini-embedding-001",
    "content": {"parts": [{"text": "..."}]},
    "outputDimensionality": 768
}

# 响应
{
    "embedding": {"values": [0.1, 0.2, ...]}
}
```

---

## 7. 认证方式对比

| 模式 | 认证方式 | Header | 适用场景 |
|------|---------|--------|---------|
| One-API | Bearer Token | `Authorization: Bearer sk-...` | 统一网关，推荐生产 |
| Gemini 直连 | Query Param | `?key=AIzaSy...` | 无法访问 One-API 的节点 |
| 豆包 API Key | Bearer Token | `Authorization: Bearer ep-...` | 简单直接，无复杂签名 |
| 豆包 AK/SK | HMAC-SHA256 签名 | 多个签名 Header | 安全要求高，火山引擎 IAM |

---

## 8. 环境变量配置示例

### 启用 One-API（推荐生产配置）

```env
# 总开关
USE_ONE_API=true

# One-API 服务地址（不含尾部斜杠）
ONE_API_BASE_URL=http://104.197.139.51:3000/v1

# One-API 访问令牌
ONE_API_KEY=sk-Nz1xxxxxxxxxxxxxxxxxx

# 模型名称（在 One-API 后台配置的模型别名）
ONE_API_GEMINI_MODEL=gemini-3-flash-preview
ONE_API_GEMINI_VISION_MODEL=gemini-3-flash-preview
ONE_API_EMBEDDING_MODEL=text-embedding-004

# Embedding 提供商
EMBEDDING_PROVIDER=ONEAPI
```

### 关闭 One-API（降级到直连）

```env
USE_ONE_API=false

# Gemini 直连
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxx
GEMINI_BASE_URL=https://generativelanguage.googleapis.com
GEMINI_TEXT_MODEL=gemini-2.0-flash

# Embedding 直连 Google
EMBEDDING_PROVIDER=GOOGLE
GOOGLE_EMBEDDING_MODEL=gemini-embedding-001
```

---

## 9. 调用链路图

### 文本生成链路

```
FastAPI 路由
    │
    └── GeminiProxyClient.generate_content(prompt)
            │
            ├─ [USE_ONE_API=true]
            │   openai.OpenAI(base_url=ONE_API_BASE_URL).chat.completions.create()
            │       → One-API 网关 → Gemini Flash API → 返回文本
            │
            └─ [USE_ONE_API=false]
                requests.post(GEMINI_TEXT_API_URL?key=GEMINI_API_KEY)
                    → Google Generative Language API → 返回 candidates[0].content
```

### 面试对话链路

```
WebSocket / HTTP 面试接口
    │
    └── DoubaoService.generate_response(history, context)
            │
            ├─ [use_one_api=true]
            │   httpx.AsyncClient.post(ONE_API_BASE_URL/chat/completions)
            │   Header: Authorization: Bearer ONE_API_KEY
            │   Body: {model, messages, temperature, max_tokens}
            │       → One-API → Gemini → choices[0].message.content
            │
            └─ [use_one_api=false]
                httpx.AsyncClient.post(DOUBAO_ENDPOINT)
                    ├─ Bearer Token: Authorization: Bearer DOUBAO_API_KEY
                    └─ AK/SK 签名: VolcengineSignature.sign()
```

### 向量生成链路

```
知识库索引 / 语义搜索
    │
    └── EmbeddingService.get_embedding(text)
            │
            ├─ [EMBEDDING_PROVIDER=ONEAPI]
            │   httpx.post(ONE_API_BASE_URL/embeddings)
            │   Header: Authorization: Bearer ONE_API_KEY
            │       → One-API → Google text-embedding-004 → 768维向量
            │
            ├─ [EMBEDDING_PROVIDER=GOOGLE]
            │   httpx.post(generativelanguage.googleapis.com/embedContent?key=...)
            │       → Google embedContent API → 768维向量
            │
            └─ [EMBEDDING_PROVIDER=DASHSCOPE]
                httpx.post(dashscope.aliyuncs.com/embeddings)
                    → 阿里云百炼 → text-embedding-v4 → 768维向量
```

---

## 10. 注意事项与已知问题

### 关键注意事项

1. **One-API 中的模型名称** 必须与 One-API 后台配置的**渠道模型别名**完全一致，不能使用 Google 原生模型 ID（如 `gemini-2.0-flash`），需使用在 One-API 中配置的别名（如 `gemini-3-flash-preview`）

2. **openai 库版本依赖**：One-API 模式依赖 `pip install openai`，如果 `import openai` 失败会直接抛出 `ImportError`

3. **Embedding 维度统一**：Milvus 集合固定为 **768 维**，切换 Embedding 提供商时需确保维度一致，否则会导致向量存储失败

4. **GEMINI_API_KEY 格式校验**：启动时会检查 key 前缀，`sk-Nz1`（One-API）和 `AIzaSy`（Google 直连）均合法，其他格式会阻止服务启动

5. **并发限制**：One-API 网关自身有并发和 QPS 限制，高并发场景（如批量简历解析）建议加队列保护

6. **降级策略**：图片分析（情绪检测）在 One-API 调用失败时会返回预设的 mock 数据，不影响面试流程，但日志会记录错误

### 双节点差异

| 服务器 | 推荐配置 | 原因 |
|--------|---------|------|
| `34.150.56.28`（主服务器） | `USE_ONE_API=true`, `EMBEDDING_PROVIDER=ONEAPI` | 网络可访问 One-API 网关 |
| `34.133.47.117`（推送服务） | `USE_ONE_API=false`, `EMBEDDING_PROVIDER=GOOGLE` | 直连 Google 更稳定，避免中转延迟 |

### 切换模式的操作步骤

1. 修改本地 `.env.production`，更新 `USE_ONE_API` 和相关变量
2. 执行加密：`python3 encrypt_env_file.py`（在 `backend/` 目录）
3. 上传加密文件：`scp .env.production.encrypted support@34.150.56.28:/home/support/AuraRecruit/backend/`
4. 重启后端：`bash AuraRecruit/restart_backend.sh`
5. 验证日志：查看 `[GeminiProxy] 🔧 初始化配置` 输出，确认 `USE_ONE_API` 值符合预期

# 补丁：Google Gemini 专属 + One-API 代理修复

**日期：** 2026-03-21
**影响文件：** `web/app.py`, `web/static/index.html`

---

## 问题描述

1. 主页 LLM Provider 下拉菜单包含 OpenAI、Anthropic、Google 三个选项，实际只使用 Google Gemini。
2. 选择 Google 后分析报错：`API key required for Gemini Developer API`。原因是 `GoogleClient` 使用 `ChatGoogleGenerativeAI`（原生 Google SDK），要求 `GOOGLE_API_KEY` 环境变量，但服务器通过 One-API 网关代理 Gemini，不使用原生 API Key。

## 修改内容

### 1. `web/static/index.html` — UI 精简

**Before:**
```html
<select id="llm-provider">
  <option value="openai">OpenAI / One-API</option>
  <option value="anthropic">Anthropic</option>
  <option value="google">Google</option>
</select>
```

**After:**
```html
<select id="llm-provider">
  <option value="google" selected>Google Gemini</option>
</select>
```

### 2. `web/app.py` — 默认 provider + One-API 路由

- `AnalysisRequest.llm_provider` 默认值从 `"openai"` 改为 `"google"`。
- `build_config()` 中增加逻辑：当 `ONE_API_BASE_URL` 环境变量存在时，将 `llm_provider` 强制设为 `"openai"`，通过 OpenAI 兼容接口调用 One-API 网关，由网关转发至 Gemini，从而绕过原生 `GOOGLE_API_KEY` 的要求。

**调用链路：**
```
UI (google) → build_config() 检测 ONE_API_BASE_URL
  → llm_provider 改为 "openai"
  → OpenAIClient(base_url=ONE_API_BASE_URL, api_key=ONE_API_KEY)
  → One-API 网关 → Gemini
```

## 验证

- 服务重启后无报错，`systemctl status tradingagents` 正常
- 主页下拉仅显示 "Google Gemini"
- 分析请求通过 One-API 代理正常调用 Gemini 模型

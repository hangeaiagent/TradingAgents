# AgentPit OAuth2 SSO 接入计划

## 背景和要求

### 背景
TradingAgents 是一个多 Agent LLM 股票分析框架，已部署在 `https://trading.agentpit.io/`，通过 FastAPI 提供 Web API 和前端页面。现在需要接入 AgentPit 应用市场的 OAuth2 单点登录（SSO），使 AgentPit 平台用户能够授权后使用股票分析功能。当前 Web 模块（`web/app.py` + `web/static/index.html`）没有任何身份验证机制，所有端点均为公开访问。

### 要求
- **OAuth2 授权码模式（Authorization Code Flow）**接入 AgentPit SSO
- **OAuth2 端点**：
  - 授权地址：`https://agentpit.io/api/oauth/authorize`
  - Token 地址：`https://agentpit.io/api/oauth/token`
  - 用户信息：`https://agentpit.io/api/oauth/userinfo`
- **OAuth2 凭证**：
  - Client ID：`cmmvv7gpd000560c8yixfhvp4`
  - Client Secret：`cmmvv7gpd000660c8mq0xfjk2`
- **回调地址**：`https://trading.agentpit.io/api/auth/callback`（需要在 AgentPit 后台将原来注册的 `https://me.candaigo.com/api/auth/agentpit/callback` 更新为此地址）
- **登录按钮名称**：「agentpit 授权登陆」
- **访问控制**：未登录用户无法访问任何分析功能，只能看到登录页面
- **用户数据**：不需要持久化存储，仅在会话期间保留登录状态
- **凭证安全**：Client ID 和 Client Secret 通过环境变量配置，不硬编码在代码中

## 实施步骤

### Phase 1: 后端 — OAuth2 基础设施

- [ ] 在 `pyproject.toml` 的 `dependencies` 中添加 `httpx>=0.28.0`（用于向 AgentPit Token/UserInfo 端点发起 HTTP 请求）
- [ ] 在 `web/app.py` 中添加 OAuth2 配置常量，从环境变量读取
  - [ ] 新增环境变量：`AGENTPIT_CLIENT_ID`、`AGENTPIT_CLIENT_SECRET`、`AGENTPIT_REDIRECT_URI`
  - [ ] 定义 OAuth2 端点常量：`AUTHORIZE_URL`、`TOKEN_URL`、`USERINFO_URL`
- [ ] 在 `web/app.py` 中集成 Starlette `SessionMiddleware`
  - [ ] 使用 `starlette.middleware.sessions.SessionMiddleware` 挂载到 FastAPI app
  - [ ] Session secret key 从环境变量 `SESSION_SECRET_KEY` 读取，提供默认值
  - [ ] Cookie 配置：`httponly=True`、`samesite="lax"`，生产环境 `secure=True`

### Phase 2: 后端 — OAuth2 路由

- [ ] 在 `web/app.py` 中实现 `GET /api/auth/login` 路由
  - [ ] 生成随机 `state` 参数写入 session，用于 CSRF 防护
  - [ ] 拼接 AgentPit 授权 URL：`AUTHORIZE_URL?response_type=code&client_id=...&redirect_uri=...&state=...`
  - [ ] 返回 302 重定向到该 URL
- [ ] 在 `web/app.py` 中实现 `GET /api/auth/callback` 路由
  - [ ] 从 query 参数提取 `code` 和 `state`
  - [ ] 校验 `state` 与 session 中存储的值一致，不一致返回 400 错误
  - [ ] 使用 `httpx.AsyncClient` 向 `TOKEN_URL` 发送 POST 请求，交换 `code` 获取 `access_token`
    - [ ] 请求体：`grant_type=authorization_code`、`code`、`redirect_uri`、`client_id`、`client_secret`
  - [ ] 将 `access_token` 存入 session，标记用户已登录
  - [ ] 重定向到 `/`（分析页面）
- [ ] 在 `web/app.py` 中实现 `GET /api/auth/logout` 路由
  - [ ] 清除 session
  - [ ] 重定向到 `/`（将显示登录页面）

### Phase 3: 后端 — 访问控制

- [ ] 创建 FastAPI 依赖函数 `require_auth(request: Request)`
  - [ ] 检查 `request.session` 中是否存在 `access_token`
  - [ ] 未登录时抛出 `HTTPException(status_code=401)`
- [ ] 将 `require_auth` 依赖添加到以下路由：
  - [ ] `POST /api/analyze/sync`
  - [ ] `POST /api/analyze`
- [ ] 修改 `GET /` 路由
  - [ ] 检查 session 登录状态
  - [ ] 已登录：返回现有的 `index.html`（分析页面）
  - [ ] 未登录：返回登录页面（`login.html`）

### Phase 4: 前端 — 登录页面

- [ ] 创建 `web/static/login.html` 登录页面
  - [ ] 视觉风格与现有 `index.html` 保持一致（深色主题、相同的渐变背景和配色）
  - [ ] 页面中央显示 TradingAgents Logo/标题
  - [ ] 下方放置「agentpit 授权登陆」按钮，点击跳转 `/api/auth/login`
  - [ ] 按钮样式突出，使用主题色（`#4ecdc4` 渐变）
- [ ] 在现有 `web/static/index.html` 的 header 区域添加用户状态和登出按钮
  - [ ] 在 `.header` 右侧添加「退出」按钮，点击跳转 `/api/auth/logout`

### Phase 5: 环境变量与部署配置

- [ ] 在项目根目录 `.env.example` 中添加新的环境变量说明：
  ```
  # AgentPit OAuth2 SSO
  AGENTPIT_CLIENT_ID=your_client_id
  AGENTPIT_CLIENT_SECRET=your_client_secret
  AGENTPIT_REDIRECT_URI=https://trading.agentpit.io/api/auth/callback
  SESSION_SECRET_KEY=your_random_secret_key
  ```
- [ ] 确认在 AgentPit 后台将 OAuth2 回调地址更新为 `https://trading.agentpit.io/api/auth/callback`（当前注册的是 `https://me.candaigo.com/api/auth/agentpit/callback`，需修改）

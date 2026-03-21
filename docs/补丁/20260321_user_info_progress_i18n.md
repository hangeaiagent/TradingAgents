# 补丁：用户信息、分析进度展示、账单明细、中英双语

**日期：** 2026-03-21
**影响文件：** `web/app.py`, `web/static/index.html`, `web/static/login.html`

---

## 新增功能

### 1. 登录用户信息展示

- OAuth 回调时调用 AgentPit userinfo 端点，获取用户名、邮箱、头像
- 将用户信息存入 session，页面加载时通过 `GET /api/user/info` 获取
- Header 右侧显示用户头像 + 名称 + 邮箱

### 2. 账单明细与汇总

- 新增 `GET /api/user/info` API，返回用户信息和用量汇总
- 新增内存 + 文件持久化的用量跟踪系统（`data/web_usage.json`）
- 每次分析完成后自动记录：ticker、日期、决策、token 用量、LLM 调用次数、耗时、模型
- 页面顶部显示用量汇总栏：分析次数、输入/输出 Token、LLM 调用
- 可展开查看历史明细表格（最近 50 条记录）
- 分析结束后显示本次 Token 用量详情栏

### 3. 分析过程实时展示

- 后端改用 `graph.stream()` 替代 `graph.invoke()`，通过 `queue.Queue` 桥接线程与异步生成器
- 分析开始时发送 `pipeline` SSE 事件，包含完整的阶段和智能体列表
- 分析过程中检测状态变化，发送 `progress` SSE 事件，附带智能体名称和内容预览
- 前端渲染垂直时间线，5 个阶段：
  - 数据分析（Market / Social / News / Fundamentals Analyst）
  - 研究辩论（Bull / Bear Researcher + Research Manager）
  - 交易方案（Trader）
  - 风险评估（Aggressive / Conservative / Neutral Debater）
  - 最终决策（Portfolio Manager）
- 智能体状态：待处理（空心圆）→ 进行中（旋转动画）→ 已完成（对勾 + 内容预览）

### 4. 中英双语支持（i18n）

- 全部静态文本通过 `I18N` 字典管理，支持 `zh` / `en` 切换
- 语言偏好存储在 `localStorage('ta_lang')`，跨会话保持
- 覆盖范围：Header、表单标签、进度面板、决策标签、用量统计、历史表格、报告标题、智能体名称
- 登录页同步支持双语

---

## 技术实现

### 后端 (`web/app.py`)

| 变更 | 说明 |
|------|------|
| `auth_callback` | OAuth 回调后调用 `AGENTPIT_USERINFO_URL` 获取用户资料 |
| `GET /api/user/info` | 新端点：返回用户信息 + 用量统计 |
| `_usage_store` | `defaultdict(list)` + JSON 文件持久化 |
| `_record_usage()` | 分析完成后记录用量并保存 |
| `_detect_progress()` | 比较流式状态，检测智能体完成事件 |
| `get_pipeline_stages()` | 根据分析深度生成阶段定义 |
| `sse()` 辅助函数 | 统一 SSE 格式化 |
| `/api/analyze` 重写 | 使用 `graph.stream()` + `ThreadPoolExecutor` + `queue.Queue` 实现实时进度推送 |

### 前端 (`web/static/index.html`)

| 组件 | 说明 |
|------|------|
| `user-chip` | Header 用户信息展示（头像 + 名称） |
| `lang-switch` | ZH / EN 语言切换按钮 |
| `usage-bar` | 用量汇总栏（可展开历史明细表格） |
| `progress-panel` + `timeline` | 分析进度垂直时间线 |
| `token-bar` | 单次分析 Token 用量详情 |
| `I18N` / `NAMES` | 完整的中英翻译字典 |
| `renderTimeline()` | 动态渲染时间线，自动标记进行中的智能体 |

### 登录页 (`web/static/login.html`)

- 新增 ZH / EN 语言切换
- 标题、提示文字、按钮文字均支持双语

---

## SSE 事件流

```
POST /api/analyze
  → pipeline: {stages: [...]}           # 阶段定义
  → status: {message: "Initializing..."}
  → progress: {agent, stage, preview}    # 每个智能体完成时
  → progress: {agent, stage, preview}
  → ...
  → result: {report, decision, usage}    # 最终结果 + 用量
  → done
```

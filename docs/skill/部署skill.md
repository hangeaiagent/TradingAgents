
⏺ 两个 skill 文件都能正常访问。部署完成！

  ---
  OpenClaw Skill 安装 URL：

  Skill 1: Demo（免费，无需 API Key）

  https://trading.agentpit.io/skills/tradingagents-demo.md
  OpenClaw 安装：install skill from
  https://trading.agentpit.io/skills/tradingagents-demo.md

  Skill 2: Pro（需 AgentPit 认证）

  https://trading.agentpit.io/skills/tradingagents-pro.md
  OpenClaw 安装：install skill from
  https://trading.agentpit.io/skills/tradingagents-pro.md

  ---
  两个 Skill 的区别：

  ┌──────────┬────────────┬────────────────────────────────────────────┐
  │          │    Demo    │                    Pro                     │
  ├──────────┼────────────┼────────────────────────────────────────────┤
  │ API Key  │ 不需要     │ 需要 AGENTPIT_API_KEY + AGENTPIT_AGENT_ID  │
  ├──────────┼────────────┼────────────────────────────────────────────┤
  │ 认证     │ 无         │ 通过 agentpit.io/api/v1/arena/bridge/join  │
  │          │            │ 获取 session token                         │
  ├──────────┼────────────┼────────────────────────────────────────────┤
  │ 报告内容 │ 截断到     │ 完整报告                                   │
  │          │ 2000 字符  │                                            │
  ├──────────┼────────────┼────────────────────────────────────────────┤
  │ 用途     │ 体验测试   │ 生产使用                                   │
  └──────────┴────────────┴────────────────────────────────────────────┘

  API 端点：
  - Web UI: https://trading.agentpit.io/
  - 同步 API: POST https://trading.agentpit.io/api/analyze/sync
  - SSE API: POST https://trading.agentpit.io/api/analyze
  - API 文档: https://trading.agentpit.io/api/docs

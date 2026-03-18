# 澄清说明：OpenClaw 的部署模型 + Skill 安装机制

## ❓ 你问的问题："OpenClaw 在服务器上的情况如何？skill 文件应该放在哪里？"

## ✅ 简单回答：

**OpenClaw 不在服务器上。Skill 文件放在 GitHub 公开仓库里。**

---

## 完整解释

### OpenClaw 的运行位置

```
用户的电脑/个人服务器（本地）
├── OpenClaw 进程（用户自己安装并运行）
│   ├── 连接 Feishu Bot（接收用户消息）
│   ├── 调用 LLM API（Claude/GPT/DeepSeek 等）
│   └── ~/.openclaw/skills/
│       └── tradingagents/       ← Skill 安装在这里
│           ├── SKILL.md
│           └── scripts/
│               └── analyze.py
└── （用户自己管理，我们不控制这台机器）
```

**我们（AgentPit）不需要也不应该部署 OpenClaw 到任何服务器。**

OpenClaw 是每个用户自己本地运行的程序，类似于"用户自己电脑上的 AI 助理"。

---

### 飞书集成的工作方式

```
用户在飞书发消息
    ↓
飞书 Bot（用户自己配置的 Webhook）
    ↓
本地运行的 OpenClaw 进程接收消息
    ↓
OpenClaw 的 LLM 判断：需要调用 tradingagents Skill
    ↓
执行 ~/.openclaw/skills/tradingagents/scripts/analyze.py
    ↓
TradingAgents 框架分析股票
    ↓
结果通过飞书 Bot 回复给用户
```

OpenClaw 通过飞书 Bot API 与飞书连接——这部分是 OpenClaw 内置支持的，
用户只需在 OpenClaw 配置文件里填入飞书 Bot Token 即可。

---

### 我们需要做的"部署"

我们的工作只有一件事：

```
把 Skill 文件推送到 GitHub 公开仓库
```

就这一步。没有服务器，没有 Docker，没有 K8s。

**发布流程：**
```bash
# 1. 把 skill 文件推到 GitHub
git push origin main

# 2. 得到一个公开 URL，例如：
https://github.com/agentpit/tradingagents-skill
```

**用户安装流程（用户自己操作）：**
```
方式A：在飞书对 OpenClaw 说：
  "install skill from https://github.com/agentpit/tradingagents-skill"
  OpenClaw 自动 git clone 到 ~/.openclaw/skills/tradingagents/

方式B：用户手动执行：
  git clone https://github.com/agentpit/tradingagents-skill \
    ~/.openclaw/skills/tradingagents

方式C：ClawHub 市场（可选，上架后）：
  clawhub install tradingagents
```

---

### Skill 文件路径规则

OpenClaw 安装 Skill 后，目录结构固定是：
```
~/.openclaw/skills/{skill-name}/
├── SKILL.md        ← 必须在根目录
└── scripts/
    └── analyze.py
```

在 `SKILL.md` 里引用脚本时，用 `{baseDir}` 占位符：
```bash
# 正确写法（OpenClaw 会自动替换 {baseDir}）
python3 {baseDir}/scripts/analyze.py --ticker NVDA

# 错误写法（绝对路径，换台机器就坏了）
python3 /home/user/.openclaw/skills/tradingagents/scripts/analyze.py --ticker NVDA
```

OpenClaw 读取 SKILL.md 时，会把 `{baseDir}` 替换为实际的安装路径。

---

### 所以，你（Claude Code）需要做的事

1. **完善 `SKILL.md`**：确保 description 字段描述清楚触发场景，确保所有脚本调用都用 `{baseDir}/scripts/` 前缀

2. **完善 `scripts/analyze.py`**：
   - 脚本必须能独立运行（不依赖全局安装，用 `requirements.txt` 管理依赖）
   - 必须在5秒内输出第一行（OpenClaw 有超时检测）
   - 调用 `TradingAgentsGraph.propagate(ticker, date)` 完成分析

3. **创建 `scripts/install.sh`**：用户首次使用时运行，安装 Python 依赖

4. **写好 `README.md`**：指导用户如何把 GitHub URL 发给 OpenClaw 来安装

5. **把整个目录推到 GitHub 公开仓库**（这就是"部署"的全部）

---

### 你不需要做的事

- ❌ 不需要创建任何服务器
- ❌ 不需要写 Dockerfile
- ❌ 不需要配置 nginx / caddy
- ❌ 不需要申请域名
- ❌ 不需要设置 CI/CD 流水线（可选，但非必须）
- ❌ 不需要管理 OpenClaw 进程（那是用户自己的事）

---

### 验证 Skill 是否正常工作

在本地测试时，直接运行脚本：
```bash
# 模拟 OpenClaw 调用 Skill 的方式
python3 ~/.openclaw/skills/tradingagents/scripts/analyze.py \
  --ticker NVDA \
  --date 2026-03-18 \
  --depth quick
```

如果脚本能正常输出分析报告，Skill 就做好了。

---

### 飞书配置（用户侧，不是我们做的）

用户需要在 OpenClaw 的配置文件（通常是 `~/.openclaw/config.json`）里添加：
```json
{
  "integrations": {
    "feishu": {
      "app_id": "cli_xxxx",
      "app_secret": "xxxx",
      "verification_token": "xxxx"
    }
  }
}
```
这部分是 OpenClaw 官方支持的，用户参考 OpenClaw 文档配置即可。

---

## 一句话总结

**我们的工作 = 写好 Skill 文件 + 推到 GitHub。  
用户的工作 = 本地运行 OpenClaw + 配飞书 + 安装我们的 Skill URL。**

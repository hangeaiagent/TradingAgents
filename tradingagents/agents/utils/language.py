"""Language helper for multi-language agent output.

When output_language == 'zh', agents use fully translated Chinese prompts
instead of appending a small suffix to English prompts.
"""


def is_chinese(config: dict | None) -> bool:
    """Return True when the user requested Simplified Chinese output."""
    if not config:
        return False
    return config.get("output_language") == "zh"


# ------------------------------------------------------------------
# Shared boilerplate for analyst agents (ChatPromptTemplate system msg)
# ------------------------------------------------------------------

ANALYST_BOILERPLATE_ZH = (
    "【核心规则】你必须始终使用简体中文输出所有内容，包括思考过程、工具调用说明和最终报告。"
    "仅保留股票代码（如 AAPL、600588.SS）、技术指标名称（如 RSI、MACD）和数值为英文原文。"
    "严禁使用英文描述你的分析过程或计划。\n\n"
    "你是一个有用的 AI 助手，正在与其他助手协作完成任务。"
    "请使用提供的工具逐步回答问题。"
    "如果你无法完全回答，没关系；另一位助手会接手你未完成的部分。"
    "请尽你所能推动进展。"
    "如果你或其他助手得出了最终交易建议，"
    "请在回复开头加上 FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**，让团队知道可以停止了。"
    " 你可以使用以下工具：{tool_names}。\n"
    "供参考，当前日期为 {current_date}。"
)

ANALYST_BOILERPLATE_EN = (
    "You are a helpful AI assistant, collaborating with other assistants."
    " Use the provided tools to progress towards answering the question."
    " If you are unable to fully answer, that's OK; another assistant with different tools"
    " will help where you left off. Execute what you can to make progress."
    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
    " You have access to the following tools: {tool_names}.\n"
    "For your reference, the current date is {current_date}."
)


def get_analyst_boilerplate(config: dict | None) -> str:
    return ANALYST_BOILERPLATE_ZH if is_chinese(config) else ANALYST_BOILERPLATE_EN

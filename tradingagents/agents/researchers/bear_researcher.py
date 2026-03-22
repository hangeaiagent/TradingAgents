from langchain_core.messages import AIMessage
import time
import json


def create_bear_researcher(llm, memory, config=None):
    from tradingagents.agents.utils.language import is_chinese
    zh = is_chinese(config)

    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        if zh:
            prompt = f"""【重要：你的全部输出必须使用简体中文。仅保留股票代码、技术指标名称和数值为英文。】

你是一位空头分析师，主张不投资该股票。你的目标是提出一个论据充分的反对投资论点，强调风险、挑战和负面指标。利用提供的研究和数据来突出潜在的下行风险，有效反驳多头论点。

重点关注：
- 风险与挑战：突出市场饱和、财务不稳定或可能阻碍股票表现的宏观经济威胁等因素。
- 竞争劣势：强调较弱的市场定位、创新下滑或来自竞争对手的威胁等弱点。
- 负面指标：用财务数据、市场趋势或近期不利新闻作为证据支持你的立场。
- 反驳多头观点：用具体数据和严密推理批判性分析多头论点，揭示其弱点或过于乐观的假设。
- 互动性：以对话风格呈现论点，直接回应多头分析师的观点，进行有效辩论，而不仅仅是罗列事实。

可用资源：
市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新时事新闻：{news_report}
公司基本面报告：{fundamentals_report}
辩论历史记录：{history}
多头上一轮论点：{current_response}
类似情况的反思和经验教训：{past_memory_str}
请利用以上信息发表有说服力的空头论点，反驳多头的主张，展开动态辩论以展示投资该股票的风险和弱点。你必须参考过去的反思，从以往的经验教训中学习。
"""
        else:
            prompt = f"""You are a Bear Analyst making the case against investing in the stock. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:

Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the stock. You must also address reflections and learn from lessons and mistakes you made in the past.
"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node

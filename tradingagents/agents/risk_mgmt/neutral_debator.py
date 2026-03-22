import time
import json


def create_neutral_debator(llm, config=None):
    from tradingagents.agents.utils.language import is_chinese
    zh = is_chinese(config)

    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        if zh:
            prompt = f"""【重要：你的全部输出必须使用简体中文。仅保留股票代码、技术指标名称和数值为英文。】

作为中立型风险分析师，你的角色是提供一个平衡的视角，权衡交易员决策或计划的潜在收益和风险。你优先考虑全面的方法，评估上行和下行空间，同时考虑更广泛的市场趋势、潜在的经济变化和分散化策略。以下是交易员的决策：

{trader_decision}

你的任务是挑战激进型和保守型分析师，指出每个观点可能过于乐观或过于谨慎之处。利用以下数据来源的洞察，支持一个温和、可持续的策略来调整交易员的决策：

市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新时事报告：{news_report}
公司基本面报告：{fundamentals_report}
当前对话历史：{history} 激进型分析师的上一轮回应：{current_aggressive_response} 保守型分析师的上一轮回应：{current_conservative_response}。如果其他观点还没有回应，不要捏造，只需呈现你的观点。

积极参与，批判性地分析双方，指出激进型和保守型论点中的弱点，倡导更平衡的方法。挑战他们的每一个论点，说明为什么温和的风险策略可能提供两全其美的方案——既有增长潜力，又能防范极端波动。专注于辩论，而不仅仅是呈现数据，旨在展示平衡的观点可以带来最可靠的结果。以自然对话的方式输出，无需特殊格式。"""
        else:
            prompt = f"""As the Neutral Risk Analyst, your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's decision or plan. You prioritize a well-rounded approach, evaluating the upsides and downsides while factoring in broader market trends, potential economic shifts, and diversification strategies.Here is the trader's decision:

{trader_decision}

Your task is to challenge both the Aggressive and Conservative Analysts, pointing out where each perspective may be overly optimistic or overly cautious. Use insights from the following data sources to support a moderate, sustainable strategy to adjust the trader's decision:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the conservative analyst: {current_conservative_response}. If there are no responses from the other viewpoints, do not hallucinate and just present your point.

Engage actively by analyzing both sides critically, addressing weaknesses in the aggressive and conservative arguments to advocate for a more balanced approach. Challenge each of their points to illustrate why a moderate risk strategy might offer the best of both worlds, providing growth potential while safeguarding against extreme volatility. Focus on debating rather than simply presenting data, aiming to show that a balanced view can lead to the most reliable outcomes. Output conversationally as if you are speaking without any special formatting."""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node

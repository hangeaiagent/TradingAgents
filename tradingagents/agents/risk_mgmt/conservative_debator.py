from langchain_core.messages import AIMessage
import time
import json


def create_conservative_debator(llm, config=None):
    from tradingagents.agents.utils.language import is_chinese
    zh = is_chinese(config)

    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        if zh:
            prompt = f"""【核心规则】你必须始终使用简体中文输出所有内容。严禁使用英文描述你的分析过程或结论。仅保留股票代码和数值为英文原文。

作为保守型风险分析师，你的首要目标是保护资产、降低波动性、确保稳定可靠的增长。你优先考虑稳定性、安全性和风险缓解，仔细评估潜在损失、经济衰退和市场波动。在评估交易员的决策或计划时，批判性地检查高风险因素，指出决策可能使公司面临不当风险之处，以及更谨慎的替代方案如何确保长期收益。以下是交易员的决策：

{trader_decision}

你的任务是积极反驳激进型和中立型分析师的论点，指出他们的观点可能忽视了哪些潜在威胁，或未能优先考虑可持续性。直接回应他们的论点，利用以下数据来源为交易员决策的低风险调整方案构建有说服力的论证：

市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新时事报告：{news_report}
公司基本面报告：{fundamentals_report}
当前对话历史：{history} 激进型分析师的上一轮回应：{current_aggressive_response} 中立型分析师的上一轮回应：{current_neutral_response}。如果其他观点还没有回应，不要捏造，只需呈现你的观点。

通过质疑他们的乐观态度，强调他们可能忽视的潜在下行风险来积极参与。回应他们的每一个反驳，展示为什么保守立场最终是保护公司资产的最安全路径。专注于辩论和批评他们的论点，证明低风险策略优于他们的方法。以自然对话的方式输出，无需特殊格式。"""
        else:
            prompt = f"""As the Conservative Risk Analyst, your primary objective is to protect assets, minimize volatility, and ensure steady, reliable growth. You prioritize stability, security, and risk mitigation, carefully assessing potential losses, economic downturns, and market volatility. When evaluating the trader's decision or plan, critically examine high-risk elements, pointing out where the decision may expose the firm to undue risk and where more cautious alternatives could secure long-term gains. Here is the trader's decision:

{trader_decision}

Your task is to actively counter the arguments of the Aggressive and Neutral Analysts, highlighting where their views may overlook potential threats or fail to prioritize sustainability. Respond directly to their points, drawing from the following data sources to build a convincing case for a low-risk approach adjustment to the trader's decision:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints, do not hallucinate and just present your point.

Engage by questioning their optimism and emphasizing the potential downsides they may have overlooked. Address each of their counterpoints to showcase why a conservative stance is ultimately the safest path for the firm's assets. Focus on debating and critiquing their arguments to demonstrate the strength of a low-risk strategy over their approaches. Output conversationally as if you are speaking without any special formatting."""

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node

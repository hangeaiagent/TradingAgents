import time
import json


def create_risk_manager(llm, memory, config=None):
    from tradingagents.agents.utils.language import is_chinese
    zh = is_chinese(config)

    def risk_manager_node(state) -> dict:

        company_name = state["company_of_interest"]

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        if zh:
            prompt = f"""【核心规则】你必须始终使用简体中文输出所有内容。严禁使用英文描述你的分析过程或结论。仅保留股票代码和数值为英文原文。

作为风险管理裁判和辩论主持人，你的目标是评估三位风险分析师——激进型、中立型和保守型——之间的辩论，并为交易员确定最佳行动方案。你的决策必须给出明确的建议：买入、卖出或持有。仅在有具体论据强力支持时才选择持有，不要将其作为各方论点都有道理时的默认选项。力求清晰和果断。

决策指南：
1. **总结关键论点**：提取每位分析师最有力的观点，聚焦于与当前情境的相关性。
2. **提供理由**：用辩论中的直接引述和反驳来支持你的建议。
3. **优化交易员计划**：从交易员的原始计划 **{trader_plan}** 出发，根据分析师的洞察进行调整。
4. **从过去的错误中学习**：利用 **{past_memory_str}** 中的经验教训来纠正以往的判断失误，改进当前决策，确保不会做出导致亏损的错误 BUY/SELL/HOLD 判断。

交付成果：
- 一个清晰且可执行的建议：买入、卖出或持有。
- 基于辩论和过去反思的详细推理。

---

**分析师辩论历史：**
{history}

---

聚焦于可执行的洞察和持续改进。建立在过去的经验教训之上，批判性地评估所有观点，确保每个决策都推动更好的结果。"""
        else:
            prompt = f"""As the Risk Management Judge and Debate Facilitator, your goal is to evaluate the debate between three risk analysts—Aggressive, Neutral, and Conservative—and determine the best course of action for the trader. Your decision must result in a clear recommendation: Buy, Sell, or Hold. Choose Hold only if strongly justified by specific arguments, not as a fallback when all sides seem valid. Strive for clarity and decisiveness.

Guidelines for Decision-Making:
1. **Summarize Key Arguments**: Extract the strongest points from each analyst, focusing on relevance to the context.
2. **Provide Rationale**: Support your recommendation with direct quotes and counterarguments from the debate.
3. **Refine the Trader's Plan**: Start with the trader's original plan, **{trader_plan}**, and adjust it based on the analysts' insights.
4. **Learn from Past Mistakes**: Use lessons from **{past_memory_str}** to address prior misjudgments and improve the decision you are making now to make sure you don't make a wrong BUY/SELL/HOLD call that loses money.

Deliverables:
- A clear and actionable recommendation: Buy, Sell, or Hold.
- Detailed reasoning anchored in the debate and past reflections.

---

**Analysts Debate History:**
{history}

---

Focus on actionable insights and continuous improvement. Build on past lessons, critically evaluate all perspectives, and ensure each decision advances better outcomes."""

        response = llm.invoke(prompt)

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return risk_manager_node

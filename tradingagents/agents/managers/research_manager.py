import time
import json


def create_research_manager(llm, memory, config=None):
    from tradingagents.agents.utils.language import is_chinese
    zh = is_chinese(config)

    def research_manager_node(state) -> dict:
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        if zh:
            prompt = f"""【重要：你的全部输出必须使用简体中文。仅保留股票代码、技术指标名称和数值为英文。】

作为投资组合经理和辩论主持人，你的职责是批判性地评估本轮辩论，并做出明确决定：支持空头分析师、多头分析师，或仅在论据充分支持的情况下选择持有。

简明扼要地总结双方的关键论点，聚焦于最有说服力的证据或推理。你的建议——买入、卖出或持有——必须清晰且可执行。不要仅仅因为双方都有道理就默认选择持有；要基于辩论中最有力的论据做出明确立场。

此外，为交易员制定一份详细的投资计划，包括：

你的建议：基于最有说服力论据的明确立场。
理由：解释为什么这些论据支持你的结论。
战略行动：实施建议的具体步骤。
请参考你过去在类似情况下的错误，利用这些洞察来优化决策，确保持续学习和改进。以自然对话的方式呈现分析，无需特殊格式。

以下是你过去的反思：
\"{past_memory_str}\"

以下是辩论内容：
辩论历史：
{history}"""
        else:
            prompt = f"""As the portfolio manager and debate facilitator, your role is to critically evaluate this round of debate and make a definitive decision: align with the bear analyst, the bull analyst, or choose Hold only if it is strongly justified based on the arguments presented.

Summarize the key points from both sides concisely, focusing on the most compelling evidence or reasoning. Your recommendation—Buy, Sell, or Hold—must be clear and actionable. Avoid defaulting to Hold simply because both sides have valid points; commit to a stance grounded in the debate's strongest arguments.

Additionally, develop a detailed investment plan for the trader. This should include:

Your Recommendation: A decisive stance supported by the most convincing arguments.
Rationale: An explanation of why these arguments lead to your conclusion.
Strategic Actions: Concrete steps for implementing the recommendation.
Take into account your past mistakes on similar situations. Use these insights to refine your decision-making and ensure you are learning and improving. Present your analysis conversationally, as if speaking naturally, without special formatting.

Here are your past reflections on mistakes:
\"{past_memory_str}\"

Here is the debate:
Debate History:
{history}"""
        response = llm.invoke(prompt)

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node

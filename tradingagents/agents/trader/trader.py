import functools
import time
import json


def create_trader(llm, memory, config=None):
    from tradingagents.agents.utils.language import is_chinese
    zh = is_chinese(config)

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "无历史记录。" if zh else "No past memories found."

        if zh:
            context = {
                "role": "user",
                "content": f"基于分析师团队的全面分析，以下是为 {company_name} 量身定制的投资计划。该计划融合了当前技术市场趋势、宏观经济指标和社交媒体情绪的洞察。请以此为基础评估你的下一步交易决策。\n\n建议的投资计划：{investment_plan}\n\n请利用这些洞察做出明智且具有战略性的决策。",
            }
            system_content = f"""【核心规则】你必须始终使用简体中文输出所有内容。严禁使用英文描述你的分析过程或结论。仅保留股票代码和数值为英文原文。

你是一位交易代理，负责分析市场数据并做出投资决策。基于你的分析，提供具体的买入、卖出或持有建议。以明确的决策结束，并始终在回复末尾加上 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**' 来确认你的建议。不要忘记利用过去决策的经验教训来学习和改进。以下是你在类似交易情境中的反思和经验教训：{past_memory_str}"""
        else:
            context = {
                "role": "user",
                "content": f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {company_name}. This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next trading decision.\n\nProposed Investment Plan: {investment_plan}\n\nLeverage these insights to make an informed and strategic decision.",
            }
            system_content = f"""You are a trading agent analyzing market data to make investment decisions. Based on your analysis, provide a specific recommendation to buy, sell, or hold. End with a firm decision and always conclude your response with 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**' to confirm your recommendation. Do not forget to utilize lessons from past decisions to learn from your mistakes. Here is some reflections from similar situations you traded in and the lessons learned: {past_memory_str}"""

        messages = [
            {
                "role": "system",
                "content": system_content,
            },
            context,
        ]

        result = llm.invoke(messages)

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")

from langchain_core.messages import AIMessage
import time
import json


def create_bull_researcher(llm, memory, config=None):
    from tradingagents.agents.utils.language import is_chinese
    zh = is_chinese(config)

    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

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
            prompt = f"""【核心规则】你必须始终使用简体中文输出所有内容。严禁使用英文描述你的分析过程或结论。仅保留股票代码和数值为英文原文。

你是一位多头分析师，主张投资该股票。你的任务是构建一个强有力的、基于证据的论证，强调增长潜力、竞争优势和积极的市场指标。利用提供的研究和数据来回应质疑，有效反驳空头论点。

重点关注：
- 增长潜力：突出公司的市场机遇、营收预测和可扩展性。
- 竞争优势：强调独特产品、强大品牌或市场主导地位等因素。
- 积极指标：用财务健康状况、行业趋势和近期利好消息作为证据。
- 反驳空头观点：用具体数据和严密推理批判性分析空头论点，充分回应其顾虑，说明为什么多头观点更有力。
- 互动性：以对话风格呈现论点，直接回应空头分析师的观点，进行有效辩论，而不仅仅是罗列数据。

可用资源：
市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新时事新闻：{news_report}
公司基本面报告：{fundamentals_report}
辩论历史记录：{history}
空头上一轮论点：{current_response}
类似情况的反思和经验教训：{past_memory_str}
请利用以上信息发表有说服力的多头论点，反驳空头的顾虑，展开动态辩论以展示多头立场的优势。你必须参考过去的反思，从以往的经验教训中学习。
"""
        else:
            prompt = f"""You are a Bull Analyst advocating for investing in the stock. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position. You must also address reflections and learn from lessons and mistakes you made in the past.
"""

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node

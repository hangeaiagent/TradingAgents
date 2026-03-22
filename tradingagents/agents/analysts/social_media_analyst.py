from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm, config=None):
    from tradingagents.agents.utils.language import is_chinese, get_analyst_boilerplate
    zh = is_chinese(config)

    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_news,
        ]

        if zh:
            system_message = (
                "你是一位社交媒体和公司新闻研究员/分析师，负责分析过去一周内某家公司的社交媒体帖子、最新公司新闻和公众情绪。"
                "你将获得一家公司的名称，你的目标是撰写一份全面的长篇报告，"
                "详细说明你在查看社交媒体上人们对该公司的评论、分析每日情绪数据以及查看最新公司新闻后，"
                "对该公司当前状态的分析、洞察和对交易者/投资者的影响。"
                "请使用 get_news(query, start_date, end_date) 工具搜索公司特定的新闻和社交媒体讨论。"
                "请尽可能查看所有来源，从社交媒体到情绪数据到新闻。"
                "不要简单地说'趋势混合'，请提供详细、精细的分析和洞察来帮助交易者做决策。"
                "请在报告末尾附上一个 Markdown 表格，整理报告中的要点，使其清晰易读。"
            )
        else:
            system_message = (
                "You are a social media and company specific news researcher/analyst tasked with analyzing social media posts, recent company news, and public sentiment for a specific company over the past week. You will be given a company's name your objective is to write a comprehensive long report detailing your analysis, insights, and implications for traders and investors on this company's current state after looking at social media and what people are saying about that company, analyzing sentiment data of what people feel each day about the company, and looking at recent company news. Use the get_news(query, start_date, end_date) tool to search for company-specific news and social media discussions. Try to look at all sources possible from social media to sentiment to news. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
                + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            )

        boilerplate = get_analyst_boilerplate(config)
        ticker_line = f" 我们当前要分析的公司是 {ticker}" if zh else f" The current company we want to analyze is {ticker}"

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    boilerplate + ticker_line + "\n{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return social_media_analyst_node

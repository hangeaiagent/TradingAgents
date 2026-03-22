from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news, get_global_news
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm, config=None):
    from tradingagents.agents.utils.language import is_chinese, get_analyst_boilerplate
    zh = is_chinese(config)

    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [
            get_news,
            get_global_news,
        ]

        if zh:
            system_message = (
                "你是一位新闻研究员，负责分析过去一周的最新新闻和趋势。"
                "请撰写一份全面的报告，涵盖与交易和宏观经济相关的全球动态。"
                "请使用以下工具：get_news(query, start_date, end_date) 搜索公司特定或定向新闻，"
                "get_global_news(curr_date, look_back_days, limit) 获取更广泛的宏观经济新闻。"
                "不要简单地说'趋势混合'，请提供详细、精细的分析和洞察来帮助交易者做决策。"
                "请在报告末尾附上一个 Markdown 表格，整理报告中的要点，使其清晰易读。"
            )
        else:
            system_message = (
                "You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for company-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
                + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            )

        boilerplate = get_analyst_boilerplate(config)
        ticker_line = f" 我们正在分析的公司是 {ticker}" if zh else f" We are looking at the company {ticker}"

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
            "news_report": report,
        }

    return news_analyst_node

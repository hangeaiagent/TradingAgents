from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement, get_insider_transactions
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm, config=None):
    from tradingagents.agents.utils.language import is_chinese, get_analyst_boilerplate
    zh = is_chinese(config)

    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        if zh:
            system_message = (
                "你是一位研究员，负责分析公司过去一周的基本面信息。"
                "请撰写一份全面的公司基本面报告，包括财务文件、公司概况、基本财务数据和财务历史，"
                "以便全面了解公司的基本面信息，为交易者提供参考。"
                "请尽可能包含详细内容。不要简单地说'趋势混合'，"
                "请提供详细、精细的分析和洞察来帮助交易者做决策。"
                "请在报告末尾附上一个 Markdown 表格，整理报告中的要点，使其清晰易读。"
                "请使用以下工具：`get_fundamentals` 进行全面的公司分析，"
                "`get_balance_sheet`、`get_cashflow` 和 `get_income_statement` 获取具体的财务报表。"
            )
        else:
            system_message = (
                "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
                + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
                + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
            )

        boilerplate = get_analyst_boilerplate(config)
        ticker_line = f" 我们要分析的公司是 {ticker}" if zh else f" The company we want to look at is {ticker}"

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
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node

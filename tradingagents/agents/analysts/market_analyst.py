from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_stock_data, get_indicators
from tradingagents.dataflows.config import get_config


def create_market_analyst(llm, config=None):
    from tradingagents.agents.utils.language import is_chinese, get_analyst_boilerplate
    zh = is_chinese(config)

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_stock_data,
            get_indicators,
        ]

        if zh:
            system_message = (
                "你是一位交易助理，负责分析金融市场。你的任务是根据当前市场状况或交易策略，从以下列表中选择最多 **8 个最相关的技术指标**，"
                "这些指标应提供互补的信息，避免冗余。各类别及其指标如下：\n\n"
                "**均线类：**\n"
                "- close_50_sma：50 日简单移动平均线，中期趋势指标。用于识别趋势方向和动态支撑/阻力位。\n"
                "- close_200_sma：200 日简单移动平均线，长期趋势基准。用于确认整体趋势、识别金叉/死叉形态。\n"
                "- close_10_ema：10 日指数移动平均线，灵敏的短期均线。用于捕捉动量的快速变化。\n\n"
                "**MACD 类：**\n"
                "- macd：MACD 线，通过 EMA 差值计算动量。用于观察交叉和背离信号。\n"
                "- macds：MACD 信号线，MACD 线的 EMA 平滑。用于与 MACD 线的交叉触发交易。\n"
                "- macdh：MACD 柱状图，显示 MACD 线与信号线之间的差距。用于可视化动量强度。\n\n"
                "**动量指标：**\n"
                "- rsi：相对强弱指数（RSI），衡量超买/超卖状态。使用 70/30 阈值，关注背离信号。\n\n"
                "**波动率指标：**\n"
                "- boll：布林带中轨（20 日 SMA），价格运动的动态基准。\n"
                "- boll_ub：布林带上轨，中轨上方 2 个标准差，信号潜在超买和突破区域。\n"
                "- boll_lb：布林带下轨，中轨下方 2 个标准差，指示潜在超卖状态。\n"
                "- atr：平均真实波幅（ATR），衡量波动率，用于设定止损和调整仓位。\n\n"
                "**成交量指标：**\n"
                "- vwma：成交量加权移动平均线，结合价格与成交量确认趋势。\n\n"
                "请选择互补且多样的指标，避免冗余（例如不要同时选 rsi 和 stochrsi）。"
                "请简要说明为什么这些指标适合当前市场。"
                "调用工具时请使用上述指标的精确英文名称，否则调用会失败。"
                "请务必先调用 get_stock_data 获取 CSV 数据，然后再用 get_indicators 获取具体指标。"
                "请撰写一份非常详细、细致入微的趋势分析报告。不要简单地说'趋势混合'，"
                "请提供详细、精细的分析和洞察来帮助交易者做决策。"
                "请在报告末尾附上一个 Markdown 表格，整理报告中的要点，使其清晰易读。"
            )
        else:
            system_message = (
                """You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy. Categories and each category's indicators are:

Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.
- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.

MACD Related:
- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.
- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.
- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.

Momentum Indicators:
- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.

Volatility Indicators:
- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.
- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.
- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.
- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.

Volume-Based Indicators:
- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.

- Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names. Write a very detailed and nuanced report of the trends you observe. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."""
                + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
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
            "market_report": report,
        }

    return market_analyst_node

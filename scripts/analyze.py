#!/usr/bin/env python3
"""TradingAgents headless CLI for OpenClaw skill invocation."""

import argparse
import os
import sys
from datetime import date


def parse_args():
    parser = argparse.ArgumentParser(description="TradingAgents Stock Analysis")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", type=str, help="Single stock ticker (e.g. NVDA)")
    group.add_argument("--tickers", type=str, help='Comma-separated tickers (e.g. "NVDA,AAPL,TSLA")')
    parser.add_argument("--date", type=str, default=date.today().strftime("%Y-%m-%d"),
                        help="Analysis date in YYYY-MM-DD format (default: today)")
    parser.add_argument("--depth", choices=["full", "quick"], default="full",
                        help="full = all analysts, quick = news + sentiment only")
    parser.add_argument("--llm", type=str, default="openai",
                        help="LLM provider: openai, anthropic, google, xai, openrouter, ollama")
    parser.add_argument("--model", type=str, default=None,
                        help="Override both deep_think and quick_think model names")
    parser.add_argument("--base-url", type=str, default=None,
                        help="Custom API base URL (OpenAI-compatible endpoint)")
    return parser.parse_args()


def build_config(args):
    from tradingagents.default_config import DEFAULT_CONFIG
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = args.llm

    if args.model:
        config["deep_think_llm"] = args.model
        config["quick_think_llm"] = args.model
    elif os.environ.get("ONE_API_GEMINI_MODEL"):
        config["deep_think_llm"] = os.environ["ONE_API_GEMINI_MODEL"]
        config["quick_think_llm"] = os.environ["ONE_API_GEMINI_MODEL"]

    if args.base_url:
        config["backend_url"] = args.base_url
    elif os.environ.get("ONE_API_BASE_URL"):
        config["backend_url"] = os.environ["ONE_API_BASE_URL"]

    return config


def get_selected_analysts(depth):
    if depth == "quick":
        return ["news", "social"]
    return ["market", "social", "news", "fundamentals"]


def format_report(final_state, decision, ticker, trade_date, depth):
    lines = []
    lines.append(f"# Trading Analysis: {ticker} ({trade_date})")
    lines.append(f"\n## Decision: {decision}\n")

    # I. Analyst Reports
    analyst_sections = []
    if final_state.get("market_report"):
        analyst_sections.append(f"### Market Analyst\n{final_state['market_report']}")
    if final_state.get("sentiment_report"):
        analyst_sections.append(f"### Social Analyst\n{final_state['sentiment_report']}")
    if final_state.get("news_report"):
        analyst_sections.append(f"### News Analyst\n{final_state['news_report']}")
    if final_state.get("fundamentals_report"):
        analyst_sections.append(f"### Fundamentals Analyst\n{final_state['fundamentals_report']}")
    if analyst_sections:
        lines.append("## I. Analyst Reports\n")
        lines.append("\n\n".join(analyst_sections))

    # II. Research Team
    debate = final_state.get("investment_debate_state", {})
    research_parts = []
    if debate.get("bull_history"):
        research_parts.append(f"### Bull Researcher\n{debate['bull_history']}")
    if debate.get("bear_history"):
        research_parts.append(f"### Bear Researcher\n{debate['bear_history']}")
    if debate.get("judge_decision"):
        research_parts.append(f"### Research Manager Decision\n{debate['judge_decision']}")
    if research_parts:
        lines.append("\n## II. Research Team\n")
        lines.append("\n\n".join(research_parts))

    # III. Trading Plan
    if final_state.get("trader_investment_plan"):
        lines.append(f"\n## III. Trading Plan\n\n{final_state['trader_investment_plan']}")

    # IV. Risk Assessment
    risk = final_state.get("risk_debate_state", {})
    risk_parts = []
    if risk.get("aggressive_history"):
        risk_parts.append(f"### Aggressive View\n{risk['aggressive_history']}")
    if risk.get("conservative_history"):
        risk_parts.append(f"### Conservative View\n{risk['conservative_history']}")
    if risk.get("neutral_history"):
        risk_parts.append(f"### Neutral View\n{risk['neutral_history']}")
    if risk_parts:
        lines.append("\n## IV. Risk Assessment\n")
        lines.append("\n\n".join(risk_parts))

    # V. Final Trade Decision
    if final_state.get("final_trade_decision"):
        lines.append(f"\n## V. Final Trade Decision\n\n{final_state['final_trade_decision']}")

    return "\n".join(lines)


def analyze_ticker(ticker, trade_date, depth, config):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    analysts = get_selected_analysts(depth)
    ta = TradingAgentsGraph(selected_analysts=analysts, debug=False, config=config)
    final_state, decision = ta.propagate(ticker, trade_date)
    return final_state, decision


def main():
    args = parse_args()

    # Determine ticker list
    if args.ticker:
        tickers = [args.ticker.strip()]
    else:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    if not tickers:
        print("Error: no tickers provided", file=sys.stderr)
        sys.exit(1)

    # Immediate output for OpenClaw timeout (must print within 5 seconds)
    print(f"Analyzing {', '.join(tickers)} ({args.depth} mode, {args.llm})...\n", flush=True)

    # Load environment
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv optional if env vars are set directly

    # Support ONE_API_KEY as OPENAI_API_KEY fallback
    if os.environ.get("ONE_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["ONE_API_KEY"]

    # Validate API key
    key_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "xai": "XAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    required_key = key_map.get(args.llm)
    if required_key and not os.environ.get(required_key):
        print(f"Error: {required_key} not set. Add it to .env or export it.", file=sys.stderr)
        sys.exit(1)

    config = build_config(args)

    for i, ticker in enumerate(tickers):
        if i > 0:
            print("\n" + "=" * 80 + "\n", flush=True)

        try:
            print(f"Starting analysis for {ticker}...", flush=True)
            final_state, decision = analyze_ticker(ticker, args.date, args.depth, config)
            report = format_report(final_state, decision, ticker, args.date, args.depth)
            print(report, flush=True)
        except Exception as e:
            print(f"Error analyzing {ticker}: {e}", file=sys.stderr)
            if len(tickers) == 1:
                sys.exit(2)


if __name__ == "__main__":
    main()

"""Language suffix helper for multi-language agent output."""

LANG_SUFFIX = {
    "zh": (
        "\n\n---\n"
        "## OUTPUT LANGUAGE REQUIREMENT\n"
        "你是一位中文金融分析师。你的全部输出——包括分析报告正文、表格、结论和建议——都必须使用简体中文撰写。"
        "仅保留以下内容为英文原文：股票代码（如 AAPL）、技术指标名称（如 RSI、MACD）和数值。"
        "\nIMPORTANT: Write your ENTIRE response in Simplified Chinese. This is mandatory.\n"
    ),
}


def get_language_suffix(config: dict) -> str:
    lang = config.get("output_language")
    if not lang:
        return ""
    return LANG_SUFFIX.get(lang, "")

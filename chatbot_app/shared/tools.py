"""Tavily tools and runtime context shared by the independent modes."""

import os
from datetime import datetime, timedelta, timezone

from langchain_tavily import TavilySearch

from .configuration import load_environment

load_environment()


def create_tools():
    """Each graph gets its own list; future date/weather tools can be added here."""
    if not os.getenv("TAVILY_API_KEY", "").strip():
        return []
    return [TavilySearch(
        max_results=3,
        topic="general",
        search_depth="basic",
        include_raw_content=False,
        description=(
            "检索网页以核实事实、查找来源和获取最新信息。"
            "用户要求联网，或询问近期新闻、科研进展、当前信息时使用。"
            "输入具体的搜索问题，必要时包含领域和时间范围。"
        ),
    )]


def runtime_prompt(tools):
    now = datetime.now(timezone(timedelta(hours=8)))
    available = "、".join(tool.name for tool in tools) or "无"
    return (
        f"\n\n当前北京时间：{now:%Y-%m-%d %H:%M}。"
        f"当前可用工具：{available}。"
        "只有实际取得工具结果才能声称已经查证；没有可用工具时如实说明。"
    )

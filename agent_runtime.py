"""Shared model configuration; each mode owns its own graph and tool registry."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from langchain_core.messages import AnyMessage
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

load_dotenv(Path(__file__).with_name(".env"), override=False)


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


api_key = os.getenv("QWEN_API_KEY", "").strip()
if not api_key:
    raise ValueError("QWEN_API_KEY is missing. Add it to .env or your environment.")

llm = ChatOpenAI(
    model=os.getenv("QWEN_MODEL", "").strip() or "qwen3.7-flash",
    api_key=api_key,
    base_url=os.getenv("QWEN_BASE_URL", "").strip()
    or "https://maas.qianwenaiapi.com/compatible-mode/v1",
    use_responses_api=False,
    extra_body={"enable_thinking": False},
    streaming=True,
)


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


def model_with_tools(tools):
    return llm.bind_tools(tools) if tools else llm


def runtime_prompt(tools):
    now = datetime.now(timezone(timedelta(hours=8)))
    available = "、".join(tool.name for tool in tools) or "无"
    return (
        f"\n\n当前北京时间：{now:%Y-%m-%d %H:%M}。"
        f"当前可用工具：{available}。"
        "只有实际取得工具结果才能声称已经查证；没有可用工具时如实说明。"
    )

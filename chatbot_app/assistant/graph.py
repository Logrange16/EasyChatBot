"""Autonomous research, evidence synthesis, reflection and public chat output."""

import json
import re

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Overwrite

from chatbot_app.assistant.prompts import (
    RESEARCH_SYSTEM_PROMPT,
    SUMMARIZER_SYSTEM_PROMPT,
    REFLECTION_SYSTEM_PROMPT,
    TOOL_SYSTEM_PROMPT,
)
from chatbot_app.assistant.state import State
from chatbot_app.shared import model as agent_model
from chatbot_app.shared.state import ChatState
from chatbot_app.shared.tools import create_tools, runtime_prompt

tools = create_tools()


def text_content(content) -> str:
    if isinstance(content, str):
        return content.strip()
    return "".join(
        block if isinstance(block, str) else block.get("text", "")
        for block in content
        if isinstance(block, (str, dict))
    ).strip()


def prepare_topic(state: State):
    """Start a fresh research task, retaining public conversation context."""
    latest_user_message = next(
        (message for message in reversed(state["messages"]) if message.type == "human"),
        None,
    )
    if latest_user_message is None:
        raise ValueError("Research topic not found.")
    # Studio Chat sends text content blocks; the standalone web sends strings.
    topic = text_content(latest_user_message.content)
    if not topic:
        raise ValueError("Research topic must be non-empty text.")
    return {
        "research_topic": topic,
        "research_messages": Overwrite(list(state["messages"])),
        "research_notes": "",
        "draft_summary": "",
        "running_summary": "",
        "reflection_count": 0,
    }


def model_messages(state: State, prompt: str):
    source_urls = []
    for message in state["research_messages"]:
        if message.type != "tool":
            continue
        content = text_content(message.content)
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            urls = [item.get("url") for item in payload["results"] if isinstance(item, dict)]
        else:
            urls = re.findall(r"https?://[^\s<>\"']+", content)
        source_urls.extend(url for url in urls if isinstance(url, str) and url not in source_urls)
    evidence_note = (
        "\n\n实际工具结果中的来源 URL（引用时使用这些原始链接，不得补造 DOI 或论文地址）：\n"
        + "\n".join(source_urls)
    ) if source_urls else "\n\n本次内部记录中尚无可引用的工具来源；不得声称已经联网核实。"
    return [
        SystemMessage(content=(
            prompt + runtime_prompt(tools)
            + "\n\n本次用户输入：\n" + state["research_topic"] + evidence_note
        )),
        *state["research_messages"],
    ]


def research_update(response):
    update = {"research_messages": [response]}
    if not response.tool_calls:
        notes = text_content(response.content)
        if not notes:
            raise ValueError("Research model returned neither notes nor tool calls.")
        update["research_notes"] = notes
    return update


def research(state: State, config: RunnableConfig):
    """Analyze the topic; the model generates search queries through tool calls."""
    response = agent_model.model_with_tools(tools).bind(temperature=0).invoke(
        model_messages(state, RESEARCH_SYSTEM_PROMPT), config=config,
    )
    return research_update(response)


async def async_research(state: State, config: RunnableConfig):
    response = await agent_model.model_with_tools(tools).bind(temperature=0).ainvoke(
        model_messages(state, RESEARCH_SYSTEM_PROMPT), config=config,
    )
    return research_update(response)


def summary_update(response):
    summary = text_content(response.content)
    if response.tool_calls or not summary:
        raise ValueError("Summarizer must return a non-empty draft.")
    return {"research_messages": [response], "draft_summary": summary}


def summarize_sources(state: State, config: RunnableConfig):
    """Synthesize the evidence and research notes into a complete draft."""
    response = agent_model.llm.bind(temperature=0).invoke(
        model_messages(state, SUMMARIZER_SYSTEM_PROMPT), config=config,
    )
    return summary_update(response)


async def async_summarize_sources(state: State, config: RunnableConfig):
    response = await agent_model.llm.bind(temperature=0).ainvoke(
        model_messages(state, SUMMARIZER_SYSTEM_PROMPT), config=config,
    )
    return summary_update(response)


def reflection_messages(state: State):
    return model_messages(
        state,
        REFLECTION_SYSTEM_PROMPT + "\n\n待复核草稿：\n" + state["draft_summary"],
    )


def reflection_update(state: State, response):
    update = {
        "research_messages": [response],
        "reflection_count": state.get("reflection_count", 0) + 1,
    }
    if not response.tool_calls:
        summary = text_content(response.content)
        if not summary:
            raise ValueError("Reflection must return a summary or request a tool.")
        update["running_summary"] = summary
    return update


def reflect_on_summary(state: State, config: RunnableConfig):
    """The reviewer either searches for missing evidence or approves a revised summary."""
    response = agent_model.model_with_tools(tools).bind(temperature=0).invoke(
        reflection_messages(state), config=config,
    )
    return reflection_update(state, response)


async def async_reflect_on_summary(state: State, config: RunnableConfig):
    response = await agent_model.model_with_tools(tools).bind(temperature=0).ainvoke(
        reflection_messages(state), config=config,
    )
    return reflection_update(state, response)


def route_tools(state: State):
    """Read the model's decision from the internal message channel."""
    return tools_condition(state, messages_key="research_messages")


def finalize_summary(state: State):
    """Publish only the reviewed answer to the existing public messages channel."""
    summary = state["running_summary"]
    if not summary:
        raise ValueError("Cannot publish an empty summary.")
    return {"messages": [AIMessage(content=summary)]}


def build_graph(*, async_model: bool = False):
    builder = StateGraph(State, input_schema=ChatState)
    builder.add_node("prepare_topic", prepare_topic)
    builder.add_node("research", async_research if async_model else research)
    builder.add_node("tools", ToolNode(
        tools,
        messages_key="research_messages",
        handle_tool_errors="检索工具执行失败。请勿声称检索成功；可调整查询重试，或如实说明资料不足。",
    ))
    builder.add_node("summarize_sources", async_summarize_sources if async_model else summarize_sources)
    builder.add_node("reflect_on_summary", async_reflect_on_summary if async_model else reflect_on_summary)
    builder.add_node("finalize_summary", finalize_summary)

    builder.add_edge(START, "prepare_topic")
    builder.add_edge("prepare_topic", "research")
    builder.add_conditional_edges("research", route_tools, {"tools": "tools", END: "summarize_sources"})
    builder.add_edge("tools", "research")
    builder.add_edge("summarize_sources", "reflect_on_summary")
    builder.add_conditional_edges("reflect_on_summary", route_tools, {"tools": "tools", END: "finalize_summary"})
    builder.add_edge("finalize_summary", END)
    return builder


# This is an execution safety limit, not a condition for declaring research complete.
graph = build_graph().compile().with_config({"recursion_limit": 80})

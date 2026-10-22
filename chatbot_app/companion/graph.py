"""Companion mode: its own graph, persona and extensible tool registry."""

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from chatbot_app.shared.model import model_with_tools
from chatbot_app.shared.tools import create_tools, runtime_prompt
from chatbot_app.companion.state import State
from chatbot_app.companion.prompts import DEFAULT_SYSTEM_PROMPT, get_companion_prompt

tools = create_tools()


def model_messages(state: State, config: RunnableConfig):
    configurable = config.get("configurable", {})
    prompt = get_companion_prompt(configurable.get("companion_prompt", ""))
    nickname = configurable.get("companion_name")
    if nickname and nickname != "你的聊天伙伴":
        prompt += (
            f"\n\n本应用中，你当前的角色昵称是「{nickname}」。"
            "日常交流和自我介绍时使用这个昵称，并沿用上述人设的性格和交流方式。"
            "用户明确询问底层模型来源时，请如实回答。"
        )
    return [SystemMessage(content=prompt + runtime_prompt(tools)), *state["messages"]]


def chatbot(state: State, config: RunnableConfig):
    response = model_with_tools(tools).invoke(model_messages(state, config), config=config)
    return {"messages": [response]}


async def async_chatbot(state: State, config: RunnableConfig):
    response = await model_with_tools(tools).ainvoke(model_messages(state, config), config=config)
    return {"messages": [response]}


def build_graph(*, async_model: bool = False):
    builder = StateGraph(State)
    builder.add_node("chatbot", async_chatbot if async_model else chatbot)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "chatbot")
    builder.add_conditional_edges("chatbot", tools_condition, {"tools": "tools", END: END})
    builder.add_edge("tools", "chatbot")
    return builder


graph_builder = build_graph()
# Agent Server supplies checkpointing and manages conversation threads.
graph = graph_builder.compile()

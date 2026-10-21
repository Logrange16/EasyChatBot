"""Research assistant mode: a separate graph with a concise tool-first prompt."""

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from agent_runtime import State, create_tools, model_with_tools, runtime_prompt
from prompts import TOOL_SYSTEM_PROMPT

tools = create_tools()


def model_messages(state: State):
    return [
        SystemMessage(content=TOOL_SYSTEM_PROMPT + runtime_prompt(tools)),
        *state["messages"],
    ]


def chatbot(state: State, config: RunnableConfig):
    response = model_with_tools(tools).invoke(model_messages(state), config=config)
    return {"messages": [response]}


async def async_chatbot(state: State, config: RunnableConfig):
    response = await model_with_tools(tools).ainvoke(model_messages(state), config=config)
    return {"messages": [response]}


def build_graph(*, async_model: bool = False):
    builder = StateGraph(State)
    builder.add_node("chatbot", async_chatbot if async_model else chatbot)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "chatbot")
    builder.add_conditional_edges("chatbot", tools_condition, {"tools": "tools", END: END})
    builder.add_edge("tools", "chatbot")
    return builder


graph = build_graph().compile()

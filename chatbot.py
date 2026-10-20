import os
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from langchain_core.messages import AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from prompts import DEFAULT_SYSTEM_PROMPT


load_dotenv(Path(__file__).with_name(".env"), override=False)


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


api_key = os.getenv("QWEN_API_KEY", "").strip()
if not api_key:
    raise ValueError(
        "QWEN_API_KEY is missing. Copy .env.example to .env and add your API key, "
        "or set QWEN_API_KEY in your environment."
    )

model_name = os.getenv("QWEN_MODEL", "").strip() or "qwen3.7-flash"
base_url = (
    os.getenv("QWEN_BASE_URL", "").strip()
    or "https://maas.qianwenaiapi.com/compatible-mode/v1"
)

llm = ChatOpenAI(
    model=model_name,
    api_key=api_key,
    base_url=base_url,
    use_responses_api=False,
    extra_body={"enable_thinking": False},
    streaming=True,
)


def chatbot(state: State):
    model_messages = [
        SystemMessage(content=DEFAULT_SYSTEM_PROMPT),
        *state["messages"],
    ]
    response = llm.invoke(model_messages)
    return {"messages": [response]}


async def async_chatbot(state: State, config: RunnableConfig):
    prompt = DEFAULT_SYSTEM_PROMPT
    nickname = config.get("configurable", {}).get("companion_name")
    if nickname and nickname != "你的聊天伙伴":
        prompt += (
            f"\n\n本应用中，你当前的角色昵称是「{nickname}」。"
            "日常交流和自我介绍时使用这个昵称，并沿用上述人设的性格和交流方式。"
            "用户明确询问底层模型来源时，请如实回答。"
        )
    model_messages = [
        SystemMessage(content=prompt),
        *state["messages"],
    ]
    response = await llm.ainvoke(model_messages)
    return {"messages": [response]}


def build_graph(*, async_model: bool = False):
    builder = StateGraph(State)
    builder.add_node("chatbot", async_chatbot if async_model else chatbot)
    builder.add_edge(START, "chatbot")
    builder.add_edge("chatbot", END)
    return builder


graph_builder = build_graph()

# Agent Server supplies checkpointing and manages conversation threads.
graph = graph_builder.compile()

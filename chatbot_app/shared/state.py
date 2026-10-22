"""Message fields shared by chat modes; research fields belong to assistant."""

from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

"""TypedDict state: public chat history and a separate internal research transcript."""

from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from chatbot_app.shared.state import ChatState


class State(ChatState, total=False):
    research_topic: str
    research_messages: Annotated[list[AnyMessage], add_messages]
    research_notes: str
    draft_summary: str
    running_summary: str
    reflection_count: int

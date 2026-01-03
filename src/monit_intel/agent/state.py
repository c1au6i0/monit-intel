from typing import Annotated, TypedDict, List
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # This keeps track of the conversation
    messages: Annotated[list, add_messages]
    # This stores the data pulled from SQLite
    context_data: str
    # A flag to tell the agent if it needs to alert you
    is_critical: bool

import sqlite3
import json
from langchain_ollama import ChatOllama
from .state import AgentState
from ..tools.log_reader import LogReader

# Initialize our model (on GPU 1)
model = ChatOllama(model="llama3.1:8b", temperature=0.2)

def fetch_db_node(state: AgentState):
    """
    Node: Queries SQLite for the most recent status of all services.
    """
    conn = sqlite3.connect("monit_history.db")
    cursor = conn.cursor()
    
    # Get the latest snapshot for every service
    cursor.execute("""
        SELECT service_name, status, raw_json 
        FROM snapshots 
        WHERE timestamp = (SELECT MAX(timestamp) FROM snapshots)
    """)
    rows = cursor.fetchall()
    conn.close()

    # Format the data into a readable block for the LLM
    reports = []
    for row in rows:
        reports.append(f"Service: {row[0]} | Status: {row[1]} | Data: {row[2]}")
    
    return {"current_monit_data": "\n".join(reports)}

def fetch_logs_node(state: AgentState):
    """
    Node: Fetch relevant logs for failed services based on the log registry.
    """
    context = state.get("context_data", "")
    if not context:
        return {"context_data": ""}
    
    # Extract service names from context
    lines = context.split("\n")
    services = []
    for line in lines:
        if "Service:" in line:
            parts = line.split("|")
            if parts:
                service_name = parts[0].replace("Service:", "").strip()
                services.append(service_name)
    
    # Fetch logs for each failed service
    logs_output = []
    for service in services:
        log_content = get_service_logs(service)
        logs_output.append(log_content)
    
    enhanced_context = context + "\n\n" + "\n\n".join(logs_output)
    return {"context_data": enhanced_context}

def call_model_node(state: AgentState):
    """
    Node: Takes the DB data and fetched logs, and asks the LLM for analysis.
    """
    system_prompt = """You are an expert Linux System Administrator analyzing server failures from Monit.

Your job is to:
1. Identify which services have failed
2. Analyze the provided logs to find root causes
3. Suggest remediation steps

Be concise and actionable. Focus on the "Why" not just the "What"."""
    
    messages = [("system", system_prompt)] + state["messages"]
    response = model.invoke(messages)
    
    return {"messages": [response]}

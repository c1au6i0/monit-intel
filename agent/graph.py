"""
LangGraph workflow definition for Monit-Intel Agent.
Builds the DAG for the ReAct loop.
"""

import sqlite3
from typing import Any
from langgraph.graph import StateGraph, START, END
from langchain_ollama import ChatOllama
from agent.state import AgentState
from tools import get_service_logs

# Initialize Llama 3.1 model
model = ChatOllama(model="llama3.1:8b", temperature=0.2)


def detect_failures(state: AgentState) -> dict[str, Any]:
    """
    Node: Check SQLite for recent service failures (status != 0).
    Only returns services that are in the log registry AND have changed status.
    Tracks state to avoid re-analyzing unchanged failures.
    """
    # Services we have log sources for
    log_registry_services = {
        "system_backup",
        "nordvpn_reconnect", 
        "nordvpn_status",
        "gamma_conn",
        "network_resurrect",
        "zfs_sanoid"
    }
    
    conn = sqlite3.connect("monit_history.db")
    cursor = conn.cursor()
    
    # Get the most recent snapshot for each service
    cursor.execute("""
        SELECT service_name, status, raw_json 
        FROM snapshots 
        WHERE (service_name, timestamp) IN (
            SELECT service_name, MAX(timestamp) 
            FROM snapshots 
            GROUP BY service_name
        )
        AND status != 0
    """)
    
    all_failures = cursor.fetchall()
    
    # Check which failures are NEW or CHANGED
    changed_failures = []
    for service_name, status, raw_json in all_failures:
        if service_name not in log_registry_services:
            continue
        
        # Check if this is a new failure or status changed
        cursor.execute(
            "SELECT last_status FROM failure_history WHERE service_name = ?",
            (service_name,)
        )
        history = cursor.fetchone()
        
        if not history or history[0] == 0:
            # New failure (was healthy before)
            changed_failures.append((service_name, status, raw_json, True))
        elif history[0] != status:
            # Status changed (different error code)
            changed_failures.append((service_name, status, raw_json, True))
        else:
            # Same status as last check - still failing but no change
            changed_failures.append((service_name, status, raw_json, False))
    
    conn.close()
    
    if changed_failures:
        new_failures = [f for f in changed_failures if f[3]]
        ongoing_failures = [f for f in changed_failures if not f[3]]
        
        report = []
        if new_failures:
            report.append("NEW FAILURES:")
            report.extend([f"  [NEW] {f[0]}: Status {f[1]}" for f in new_failures])
        if ongoing_failures:
            report.append("ONGOING:")
            report.extend([f"  [ONGOING] {f[0]}: Status {f[1]}" for f in ongoing_failures])
        
        print("\nFailure Status:")
        print("\n".join(report))
    else:
        print("All monitored services healthy")
    
    return {
        "context_data": "\n".join([
            f"Service: {f[0]} | Status: {f[1]} | Changed: {f[3]}" for f in changed_failures
        ]),
        "is_critical": len([f for f in changed_failures if f[3]]) > 0  # Only critical if NEW/CHANGED
    }


def analyze_with_llm(state: AgentState) -> dict[str, Any]:
    """
    Node: Send context to Llama 3.1 for root-cause analysis.
    Only analyzes NEW or CHANGED failures, skips unchanged ones.
    """
    if not state.get("is_critical"):
        return {"messages": []}
    
    # Extract only CHANGED failures for analysis
    context = state.get("context_data", "")
    changed_failures = [
        line for line in context.split("\n")
        if "Changed: True" in line
    ]
    
    if not changed_failures:
        print("\n[Analysis] Skipped - all failures are ongoing, no changes detected")
        return {"messages": []}
    
    analysis_context = "\n".join(changed_failures)
    
    system_prompt = """You are an expert Linux system administrator analyzing NEW server failures from Monit.

Log Registry (where to look for each service):
- system_backup: /data/tank/backups/sys_restore/backup_log_*.log (latest file)
- nordvpn_reconnect: /var/log/nordvpn-reconnect.log (append)
- nordvpn_status: journalctl -u nordvpnd.service
- gamma_conn: tailscale ping + journalctl -u tailscaled
- network_resurrect: /var/log/monit-network-restart.log (append)
- ZFS/Sanoid: journalctl -u sanoid

Your task:
1. Identify which services have NEWLY failed
2. Analyze provided logs to find root causes
3. Suggest remediation steps

Be concise and actionable. Focus on the "Why" not just the "What"."""

    user_message = f"""NEW failures detected:
{analysis_context}

Which services need investigation and where should we look first?"""

    response = model.invoke([
        ("system", system_prompt),
        ("user", user_message)
    ])
    
    print(f"\n[LLM Analysis]:\n{response.content}")
    
    return {"messages": [("assistant", response.content)]}


def fetch_logs_and_context(state: AgentState) -> dict[str, Any]:
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


def build_graph():
    """
    Construct the LangGraph workflow DAG.
    
    Flow:
    START → detect_failures → fetch_logs → analyze_llm → END
    """
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("detect_failures", detect_failures)
    graph.add_node("fetch_logs", fetch_logs_and_context)
    graph.add_node("analyze_llm", analyze_with_llm)
    
    # Define edges
    graph.add_edge(START, "detect_failures")
    graph.add_edge("detect_failures", "fetch_logs")
    graph.add_edge("fetch_logs", "analyze_llm")
    graph.add_edge("analyze_llm", END)
    
    return graph.compile()

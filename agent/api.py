"""
FastAPI REST server for Monit-Intel Agent.
Provides interactive interface to query and analyze service failures.
"""

import sqlite3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta
from agent.graph import build_graph
from agent.mother import Mother
from agent.actions import ActionExecutor, ActionType
from tools import get_service_logs

app = FastAPI(
    title="Monit-Intel Agent API",
    description="Query and analyze server health via REST API",
    version="1.0.0"
)

# Initialize Mother and ActionExecutor
mother = Mother()
action_executor = ActionExecutor()


class AnalysisRequest(BaseModel):
    service: str = None
    question: str = None


class ServiceStatus(BaseModel):
    name: str
    status: int
    last_checked: str


class AnalysisResponse(BaseModel):
    service: str
    analysis: str
    timestamp: str


class MotherChatRequest(BaseModel):
    query: str


class ActionRequest(BaseModel):
    action: str
    service: str
    approve: bool = False


@app.get("/")
def root():
    """Health check endpoint."""
    return {
        "name": "Monit-Intel Agent API",
        "status": "running",
        "endpoints": [
            "/status - Get current service status",
            "/analyze - Analyze a specific service or all failures",
            "/history - Get failure history for a service",
            "/health - Health check"
        ]
    }


@app.get("/health")
def health():
    """Health check."""
    try:
        conn = sqlite3.connect("monit_history.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM snapshots")
        count = cursor.fetchone()[0]
        conn.close()
        
        return {
            "status": "healthy",
            "database": "connected",
            "snapshots": count
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


@app.get("/status", response_model=list[ServiceStatus])
def get_status():
    """Get current status of all monitored services."""
    try:
        conn = sqlite3.connect("monit_history.db")
        cursor = conn.cursor()
        
        # Get latest status for each service
        cursor.execute("""
            SELECT service_name, status, MAX(timestamp)
            FROM snapshots
            GROUP BY service_name
            ORDER BY service_name
        """)
        
        services = []
        for name, status, timestamp in cursor.fetchall():
            services.append(ServiceStatus(
                name=name,
                status=status,
                last_checked=timestamp
            ))
        
        conn.close()
        return services
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query error: {str(e)}")


@app.post("/analyze", response_model=AnalysisResponse)
def analyze(request: AnalysisRequest):
    """
    Trigger analysis of a service or all current failures.
    If service is None, analyzes all current failures.
    """
    try:
        # Build and run the workflow
        workflow = build_graph()
        
        result = workflow.invoke({
            "messages": [],
            "context_data": "",
            "is_critical": False
        })
        
        # Extract analysis from messages
        analysis_text = ""
        if result.get("messages"):
            for msg in result["messages"]:
                if isinstance(msg, tuple) and len(msg) > 1:
                    analysis_text += msg[1] + "\n"
                elif hasattr(msg, "content"):
                    analysis_text += msg.content + "\n"
        
        return AnalysisResponse(
            service=request.service or "all",
            analysis=analysis_text.strip() or "No failures detected or analysis skipped",
            timestamp=datetime.now().isoformat()
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@app.get("/history")
def get_history(service: str, days: int = 7):
    """
    Get failure history for a service over the last N days.
    """
    try:
        conn = sqlite3.connect("monit_history.db")
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute("""
            SELECT timestamp, status
            FROM snapshots
            WHERE service_name = ? AND timestamp > ?
            ORDER BY timestamp DESC
        """, (service, cutoff_date))
        
        history = []
        for timestamp, status in cursor.fetchall():
            history.append({
                "timestamp": timestamp,
                "status": status,
                "healthy": status == 0
            })
        
        conn.close()
        
        if not history:
            raise HTTPException(
                status_code=404,
                detail=f"No history found for service '{service}' in last {days} days"
            )
        
        return {
            "service": service,
            "days": days,
            "total_checks": len(history),
            "failures": sum(1 for h in history if h["status"] != 0),
            "history": history
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query error: {str(e)}")


@app.get("/logs/{service}")
def get_logs(service: str):
    """Get latest logs for a specific service."""
    try:
        result = get_service_logs(service)
        
        if "Error:" in result:
            raise HTTPException(status_code=404, detail=result)
        
        return {
            "service": service,
            "logs": result,
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ============================================================================
# MOTHER: Interactive Chat Interface (Phase 6)
# ============================================================================

@app.post("/mother/chat")
def mother_chat(request: MotherChatRequest):
    """
    Query the agent using natural language via Mother chat interface.
    Automatically injects service context and failure history.
    """
    try:
        response = mother.query_agent(request.query)
        
        return {
            "query": request.query,
            "response": response,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@app.get("/mother/history")
def mother_history(limit: int = 10):
    """Get conversation history from Mother."""
    try:
        history = mother.get_history(limit=limit)
        
        return {
            "count": len(history),
            "conversations": history
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.delete("/mother/clear")
def mother_clear():
    """Clear all conversation history."""
    try:
        mother.clear_history()
        
        return {
            "status": "cleared",
            "message": "All conversation history has been deleted"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ============================================================================
# ACTIONS: Safe Command Execution (Phase 7)
# ============================================================================

@app.post("/mother/actions/suggest")
def suggest_action(request: ActionRequest):
    """
    Suggest an action without executing it.
    User can review and approve before execution.
    """
    try:
        action_type = ActionType[request.action.upper()]
        suggestion = action_executor.suggest_action(action_type, request.service)
        
        return suggestion
    
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown action: {request.action}. Valid actions: {[a.name for a in ActionType]}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/mother/actions/execute")
def execute_action(request: ActionRequest):
    """
    Execute a safe action with user approval.
    Returns execution result and logs to audit trail.
    """
    try:
        action_type = ActionType[request.action.upper()]
        result = action_executor.execute_action(
            action_type,
            request.service,
            user_approved=request.approve
        )
        
        return result
    
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown action: {request.action}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/mother/actions/audit")
def get_audit_log(limit: int = 50):
    """Get action audit log (all executed commands)."""
    try:
        logs = action_executor.get_audit_log(limit=limit)
        
        return {
            "count": len(logs),
            "audit_log": logs
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

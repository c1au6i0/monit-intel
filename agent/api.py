"""
FastAPI REST server for Monit-Intel Agent.
Provides interactive interface to query and analyze service failures.
"""

import sqlite3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta
from agent.graph import build_graph
from tools import get_service_logs

app = FastAPI(
    title="Monit-Intel Agent API",
    description="Query and analyze server health via REST API",
    version="1.0.0"
)


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

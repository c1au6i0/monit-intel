"""
FastAPI REST server for Monit-Intel Agent.
Provides interactive interface to query and analyze service failures.
"""

import sqlite3
import json
import asyncio
import os
import base64
import urllib.parse
from typing import Optional, Dict
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Header, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from .graph import build_graph
from .mother import Mother
from .actions import ActionExecutor, ActionType
from ..tools.log_reader import LogReader
from ..chat_auth import verify_chat_credentials

# Load Monit API credentials from environment
MONIT_USER = os.getenv("MONIT_USER")
MONIT_PASS = os.getenv("MONIT_PASS")

# If Monit credentials not set in environment, raise error
if not MONIT_USER or not MONIT_PASS:
    raise RuntimeError(
        "MONIT_USER and MONIT_PASS environment variables must be set. "
        "See systemd env.conf or .env file."
    )


def verify_auth(authorization: str = Header(None)) -> str:
    """Verify HTTP Basic Authentication against chat credentials in database."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    try:
        scheme, credentials = authorization.split(" ")
        if scheme.lower() != "basic":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
        
        decoded = base64.b64decode(credentials).decode("utf-8")
        username, password = decoded.split(":", 1)
        
        # Verify against chat credentials in database
        if not verify_chat_credentials(username, password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        return username
    
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=401, detail="Invalid credentials format")


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


def _to_local(ts: Optional[str]) -> str:
    """Convert naive UTC timestamp strings from SQLite to local time with TZ."""
    if not ts:
        return "N/A"
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z%z")
    except Exception:
        return ts


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
def health(_: str = Depends(verify_auth)):
    """Health check. Requires authentication."""
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
def get_status(_: str = Depends(verify_auth)):
    """Get current status of all monitored services. Requires authentication."""
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
                last_checked=_to_local(timestamp)
            ))
        
        conn.close()
        return services
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query error: {str(e)}")


@app.post("/analyze", response_model=AnalysisResponse)
def analyze(request: AnalysisRequest, _: str = Depends(verify_auth)):
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
            timestamp=datetime.now().astimezone().isoformat()
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@app.get("/history")
def get_history(service: str, days: int = 7, _: str = Depends(verify_auth)):
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
                "timestamp": _to_local(timestamp),
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
def get_logs(service: str, _: str = Depends(verify_auth)):
    """Get latest logs for a specific service. Requires authentication."""
    try:
        result = get_service_logs(service)
        
        if "Error:" in result:
            raise HTTPException(status_code=404, detail=result)
        
        return {
            "service": service,
            "logs": result,
            "timestamp": datetime.now().astimezone().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ============================================================================
# MOTHER: Interactive Chat Interface (Phase 6)
# ============================================================================

@app.post("/mother/chat")
def mother_chat(request: MotherChatRequest, _: str = Depends(verify_auth)):
    """
    Query the agent using natural language via Mother chat interface.
    Automatically injects service context and failure history.
    Requires HTTP Basic Authentication (chat credentials).
    """
    try:
        response = mother.query_agent(request.query)
        
        return {
            "query": request.query,
            "response": response,
            "timestamp": datetime.now().astimezone().isoformat()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@app.get("/mother/history")
def mother_history(limit: int = 10, _: str = Depends(verify_auth)):
    """Get conversation history from Mother. Requires authentication."""
    try:
        history = mother.get_history(limit=limit)
        
        return {
            "count": len(history),
            "conversations": [
                {**h, "timestamp": _to_local(h.get("timestamp"))} for h in history
            ]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.delete("/mother/clear")
def mother_clear(_: str = Depends(verify_auth)):
    """Clear all conversation history. Requires authentication."""
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
def suggest_action(request: ActionRequest, _: str = Depends(verify_auth)):
    """
    Suggest an action without executing it.
    User can review and approve before execution.
    Requires authentication.
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
def execute_action(request: ActionRequest, _: str = Depends(verify_auth)):
    """
    Execute a safe action with user approval.
    Returns execution result and logs to audit trail.
    Requires authentication.
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
def get_audit_log(limit: int = 50, _: str = Depends(verify_auth)):
    """Get action audit log (all executed commands). Requires authentication."""
    try:
        logs = action_executor.get_audit_log(limit=limit)
        
        return {
            "count": len(logs),
            "audit_log": logs
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ============================================================================
# Helper: Detect action suggestions in Mother's responses
# ============================================================================

def detect_action_suggestion(response: str) -> Optional[Dict]:
    """
    Detect if Mother is suggesting a system command action.
    Parses response for patterns like "systemctl restart {service}".
    Handles commands in backticks and code blocks.
    
    Returns:
        Dict with action type and service name, or None if no action detected
    """
    import re
    
    response_lower = response.lower()
    
    # Patterns to detect actions (with optional sudo prefix and backticks)
    patterns = [
        (r"(?:`{1,3}\s*)?(?:sudo\s+)?systemctl\s+restart\s+(\w+)", "systemctl_restart"),
        (r"(?:`{1,3}\s*)?(?:sudo\s+)?systemctl\s+stop\s+(\w+)", "systemctl_stop"),
        (r"(?:`{1,3}\s*)?(?:sudo\s+)?systemctl\s+start\s+(\w+)", "systemctl_start"),
        (r"(?:`{1,3}\s*)?(?:sudo\s+)?systemctl\s+status\s+(\w+)", "systemctl_status"),
        (r"(?:`{1,3}\s*)?sudo\s+monit\s+monitor\s+(\w+)", "monit_monitor"),
        (r"(?:`{1,3}\s*)?sudo\s+monit\s+start\s+(\w+)", "monit_start"),
        (r"(?:`{1,3}\s*)?sudo\s+monit\s+stop\s+(\w+)", "monit_stop"),
        (r"(?:`{1,3}\s*)?(?:sudo\s+)?journalctl\s+-u\s+(\w+)", "journalctl_view"),
    ]
    
    for pattern, action_type in patterns:
        match = re.search(pattern, response_lower)
        if match:
            service_name = match.group(1)
            return {
                "action": action_type,
                "service": service_name,
                "command": match.group(0).strip("`").strip()
            }
    
    return None


# ============================================================================
# WEBSOCKET: Bidirectional Chat
# ============================================================================

class ConnectionManager:
    """Manages WebSocket connections."""
    
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    async def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for bidirectional chat with Mother.
    First message must be authentication: {"type": "auth", "credentials": "base64_encoded_user:pass"}
    
    After auth, send messages:
    {
        "type": "message",
        "content": "user query",
        "action": "execute_command" (optional)
    }
    """
    await manager.connect(websocket)
    authenticated = False
    
    try:
        while True:
            # Receive first message - should be auth
            data = await websocket.receive_json()
            
            # Check for auth message
            if data.get("type") == "auth":
                credentials_b64 = data.get("credentials", "")
                
                try:
                    # URL-decode if needed
                    decoded_credentials = urllib.parse.unquote(credentials_b64)
                    # Base64 decode
                    credentials = base64.b64decode(decoded_credentials).decode("utf-8")
                    username, password = credentials.split(":", 1)
                    
                    # Verify against chat credentials in database
                    if verify_chat_credentials(username, password):
                        authenticated = True
                        await websocket.send_json({
                            "type": "system",
                            "message": "Authentication successful"
                        })
                        continue
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Invalid credentials"
                        })
                        await websocket.close(code=4001, reason="Invalid credentials")
                        return
                
                except (ValueError, UnicodeDecodeError):
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid credentials format"
                    })
                    await websocket.close(code=4001, reason="Invalid credentials format")
                    return
            
            # Only process other messages after authentication
            if not authenticated:
                await websocket.send_json({
                    "type": "error",
                    "message": "Not authenticated. Send auth message first."
                })
                continue
            
            msg_type = data.get("type", "message")
            
            print(f"DEBUG: Received message type: {msg_type}, data: {data}", flush=True)
            
            # Only check for content on message type
            if msg_type == "message":
                content = data.get("content", "").strip()
                if not content:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Empty message"
                    })
                    continue
            else:
                content = data.get("content", "")
            
            try:
                if msg_type == "message":
                    # Send acknowledgment for message type
                    await websocket.send_json({
                        "type": "thinking",
                        "message": "Processing your query..."
                    })
                    
                    # Chat with Mother
                    response = mother.query_agent(content)
                    
                    # Check if Mother's response contains an action suggestion
                    action_suggestion = detect_action_suggestion(response)
                    
                    print(f"DEBUG: Response: {response[:200]}")  # Debug: print first 200 chars
                    print(f"DEBUG: Action suggestion detected: {action_suggestion}")  # Debug: print detected action
                    
                    if action_suggestion:
                        # Send the response first
                        await websocket.send_json({
                            "type": "response",
                            "content": response,
                            "timestamp": datetime.now().astimezone().isoformat()
                        })
                        
                        # Then send action suggestion for approval
                        try:
                            action_type = ActionType[action_suggestion["action"].upper()]
                            suggestion = action_executor.suggest_action(action_type, action_suggestion["service"])
                            
                            print(f"DEBUG: Sending action suggestion - action: {action_suggestion['action']}, service: {action_suggestion['service']}")
                            
                            await websocket.send_json({
                                "type": "action_suggestion",
                                "action": action_suggestion["action"],
                                "service": action_suggestion["service"],
                                "command": suggestion.get("command"),
                                "description": suggestion.get("description"),
                                "timestamp": datetime.now().astimezone().isoformat()
                            })
                        except (KeyError, ValueError) as e:
                            print(f"DEBUG: Error converting action type: {e}")
                            # If action type is invalid, just send response
                            pass
                    else:
                        # No action detected, just send response
                        await websocket.send_json({
                            "type": "response",
                            "content": response,
                            "timestamp": datetime.now().astimezone().isoformat()
                        })
                
                elif msg_type == "action":
                    # Execute action
                    action = data.get("action", "").lower()
                    service = data.get("service", "").lower()
                    
                    if not action or not service:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Action and service required"
                        })
                        continue
                    
                    # Suggest action first
                    suggestion = action_executor.suggest_action(action, service)
                    
                    if not suggestion.get("allowed"):
                        await websocket.send_json({
                            "type": "error",
                            "message": suggestion.get("reason", "Action not allowed")
                        })
                        continue
                    
                    # Ask for approval
                    await websocket.send_json({
                        "type": "action_suggestion",
                        "action": suggestion.get("action_type"),
                        "service": suggestion.get("service"),
                        "command": suggestion.get("command"),
                        "description": suggestion.get("description")
                    })
                
                elif msg_type == "action_confirm":
                    # Confirm and execute action
                    action_str = data.get("action", "").lower()
                    service = data.get("service", "").lower()
                    
                    print(f"DEBUG action_confirm: action_str={action_str}, service={service}", flush=True)
                    
                    try:
                        # Convert string to ActionType enum
                        print(f"DEBUG: About to convert action_str.upper()={action_str.upper()}", flush=True)
                        action_type = ActionType[action_str.upper()]
                        print(f"DEBUG: Converted to ActionType: {action_type}", flush=True)
                        print(f"DEBUG: About to execute action", flush=True)
                        result = action_executor.execute_action(action_type, service, user_approved=True)
                        print(f"DEBUG: Execute result: {result}", flush=True)
                    except (KeyError, ValueError) as e:
                        print(f"DEBUG: Conversion/Execution error: {e}", flush=True)
                        import traceback
                        traceback.print_exc()
                        result = {
                            "success": False,
                            "reason": f"Unknown action type: {action_str}. Supported: systemctl_restart, systemctl_stop, systemctl_start, systemctl_status, monit_monitor, monit_start, monit_stop, journalctl_view"
                        }
                    except Exception as e:
                        print(f"DEBUG: UNEXPECTED error in action_confirm: {e}", flush=True)
                        import traceback
                        traceback.print_exc()
                        result = {
                            "success": False,
                            "reason": str(e)
                        }
                    
                    print(f"DEBUG: About to send response", flush=True)
                    if result.get("success"):
                        await websocket.send_json({
                            "type": "action_result",
                            "success": True,
                            "exit_code": result.get("exit_code"),
                            "output": result.get("output"),
                            "timestamp": datetime.now().astimezone().isoformat()
                        })
                    else:
                        await websocket.send_json({
                            "type": "action_result",
                            "success": False,
                            "error": result.get("reason"),
                            "timestamp": datetime.now().astimezone().isoformat()
                        })
                    print(f"DEBUG: Response sent", flush=True)
                
                elif msg_type == "history":
                    # Get conversation history
                    history = mother.get_history(limit=10)
                    await websocket.send_json({
                        "type": "history",
                        "conversations": history
                    })
                
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}"
                    })
            
            except Exception as e:
                import traceback
                print(f"ERROR: {str(e)}", flush=True)
                print(f"TRACEBACK: {traceback.format_exc()}", flush=True)
                await websocket.send_json({
                    "type": "error",
                    "message": f"Error processing request: {str(e)}"
                })
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)
        print(f"WebSocket error: {e}")


# ============================================================================
# STATIC FILES: Serve Web UI
# ============================================================================

@app.get("/chat")
def chat_ui():
    """Serve the chat UI."""
    import os
    # Get the directory of this file and construct path to static/chat.html
    current_dir = os.path.dirname(os.path.abspath(__file__))
    chat_file = os.path.join(current_dir, "static", "chat.html")
    
    if not os.path.exists(chat_file):
        raise HTTPException(
            status_code=404, 
            detail=f"Chat UI not found at {chat_file}"
        )
    
    return FileResponse(chat_file, media_type="text/html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

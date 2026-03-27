"""
Ghost AI System — FastAPI REST Server
Exposes Ghost AI agent capabilities as a REST API for the dashboard frontend.

Start with:  uvicorn ghost_api:app --reload --port 8000
"""
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from ghost_agent import AgentTask, GhostAgent

app = FastAPI(
    title="Ghost AI System",
    description="Autonomous security orchestration platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singleton agents keyed by model name
_agents: dict[str, GhostAgent] = {}

AVAILABLE_TOOLS = [
    {
        "id": "gitleaks",
        "name": "Gitleaks",
        "category": "Secret Scanning",
        "description": "Detect hardcoded secrets and credentials in codebases",
        "status": "online",
    },
    {
        "id": "trufflehog",
        "name": "TruffleHog",
        "category": "Secret Scanning",
        "description": "Find leaked credentials using entropy and pattern detection",
        "status": "online",
    },
    {
        "id": "commix",
        "name": "Commix",
        "category": "Injection Testing",
        "description": "Automated command injection vulnerability exploitation",
        "status": "online",
    },
    {
        "id": "w3af",
        "name": "w3af",
        "category": "Web App Scanning",
        "description": "Web application attack and audit framework",
        "status": "standby",
    },
    {
        "id": "aircrack",
        "name": "Aircrack-ng",
        "category": "Wireless Security",
        "description": "IEEE 802.11 WEP/WPA/WPA2 security assessment suite",
        "status": "standby",
    },
    {
        "id": "beef",
        "name": "BeEF",
        "category": "Browser Exploitation",
        "description": "Browser exploitation framework for client-side security testing",
        "status": "standby",
    },
    {
        "id": "threat_intel",
        "name": "Threat Intel",
        "category": "OSINT",
        "description": "Dark web threat intelligence gathering and analysis",
        "status": "online",
    },
]


def _get_agent(model: str = "claude-opus-4-6") -> GhostAgent:
    if model not in _agents:
        _agents[model] = GhostAgent(model_choice=model)
    return _agents[model]


# ── Request / response models ─────────────────────────────────────────────────

class GoalRequest(BaseModel):
    goal: str
    model: Optional[str] = "claude-opus-4-6"


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    model: Optional[str] = "claude-opus-4-6"


class ScanRequest(BaseModel):
    tool: str
    params: dict
    model: Optional[str] = "claude-opus-4-6"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Health check."""
    return {"status": "online", "system": "Ghost AI", "version": "1.0.0"}


@app.get("/tools")
def list_tools():
    """List all available security tools and their status."""
    return {"tools": AVAILABLE_TOOLS}


@app.post("/agent/run")
async def run_goal(req: GoalRequest):
    """Autonomously plan and execute tasks for a security goal."""
    agent = _get_agent(req.model)
    return await agent.run_goal(req.goal)


@app.post("/agent/chat")
async def chat(req: ChatRequest):
    """Interactive chat with Ghost AI."""
    agent = _get_agent(req.model)
    response, session_id = await agent.chat(req.message, req.session_id)
    return {"session_id": session_id, "response": response}


@app.post("/scan")
async def run_scan(req: ScanRequest):
    """Run a specific security tool scan directly."""
    agent = _get_agent(req.model)
    task = AgentTask(
        id=str(uuid.uuid4()),
        name=f"{req.tool} scan",
        tool=req.tool,
        params=req.params,
    )
    completed = await agent.execute_task(task)
    return agent._serialize_task(completed)


@app.get("/session/{session_id}")
def get_session(session_id: str):
    """Get metadata for an active session."""
    agent = next(iter(_agents.values()), None)
    if not agent:
        raise HTTPException(status_code=404, detail="No active agents")
    session = agent.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session.session_id,
        "goal": session.goal,
        "history_length": len(session.history),
        "task_count": len(session.tasks),
    }

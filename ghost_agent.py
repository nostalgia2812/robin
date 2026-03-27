"""
Ghost AI System - Autonomous Security Orchestration Agent
Coordinates secret scanning, vulnerability assessment, and threat intelligence
for authorized security operations.
"""
import asyncio
import json
import shutil
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from llm import get_llm, generate_summary


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class AgentTask:
    id: str
    name: str
    tool: str
    params: dict
    status: AgentStatus = AgentStatus.IDLE
    result: Optional[dict] = None
    error: Optional[str] = None


@dataclass
class GhostSession:
    session_id: str
    goal: str = ""
    tasks: list = field(default_factory=list)
    history: list = field(default_factory=list)
    intel_context: dict = field(default_factory=dict)


class GhostAgent:
    """
    Ghost AI — Autonomous security orchestration agent.
    Coordinates secret scanning, vulnerability assessment, and cyber threat
    intelligence gathering for authorized security operations.
    """

    SYSTEM_PROMPT = """You are Ghost, an autonomous AI security operations agent.
You coordinate security tools for authorized red team operations, secret scanning,
and cyber threat intelligence gathering.

Your capabilities:
- Secret & credential detection (gitleaks, trufflehog)
- Web application vulnerability scanning (w3af, commix)
- Wireless security assessment (aircrack-ng)
- Browser security testing (BeEF)
- Dark web threat intelligence (OSINT)
- Security posture analysis and reporting

Always operate within authorized scope. Be precise, technical, and actionable.
Provide structured, intelligence-grade assessments.
"""

    PLANNER_PROMPT = """You are Ghost AI planner. Given a security goal, decompose it into discrete tasks.

Return ONLY a valid JSON array. Each task object must have:
- "id": unique string like "t1", "t2"
- "name": short task description
- "tool": one of [gitleaks, trufflehog, commix, w3af, threat_intel]
- "params": object with tool-specific parameters

Tool params:
- gitleaks: {"path": "/path/to/repo"}
- trufflehog: {"target": "/path/or/git/url"}
- commix: {"url": "http://target/page?param=val"}
- w3af: {"url": "http://target"}
- threat_intel: {"query": "search terms"}

Return only the JSON array, no markdown, no explanation.
"""

    def __init__(self, model_choice: str = "claude-sonnet-4-6"):
        self.llm = get_llm(model_choice)
        self.sessions: dict[str, GhostSession] = {}
        self._tool_registry = {
            "gitleaks": self._run_gitleaks,
            "trufflehog": self._run_trufflehog,
            "commix": self._run_commix,
            "w3af": self._run_w3af,
            "threat_intel": self._run_threat_intel,
        }

    # ── Session management ────────────────────────────────────────

    def new_session(self, goal: str = "") -> GhostSession:
        sid = str(uuid.uuid4())
        session = GhostSession(session_id=sid, goal=goal)
        self.sessions[sid] = session
        return session

    def get_session(self, session_id: str) -> Optional[GhostSession]:
        return self.sessions.get(session_id)

    # ── Planning ──────────────────────────────────────────────────

    async def plan(self, goal: str) -> list:
        """Use LLM to decompose a security goal into executable tasks."""
        messages = [
            SystemMessage(content=self.PLANNER_PROMPT),
            HumanMessage(content=f"Security goal: {goal}"),
        ]
        response = self.llm.invoke(messages)
        raw = response.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            tasks_data = json.loads(raw.strip())
        except json.JSONDecodeError:
            tasks_data = [{"id": "t1", "name": "Threat intel",
                           "tool": "threat_intel", "params": {"query": goal}}]
        return [
            AgentTask(
                id=t.get("id", str(uuid.uuid4())),
                name=t.get("name", "unnamed"),
                tool=t.get("tool", "threat_intel"),
                params=t.get("params", {}),
            )
            for t in tasks_data
        ]

    # ── Execution ─────────────────────────────────────────────────

    async def execute_task(self, task: AgentTask) -> AgentTask:
        """Execute a single agent task."""
        task.status = AgentStatus.RUNNING
        runner = self._tool_registry.get(task.tool)
        if not runner:
            task.status = AgentStatus.ERROR
            task.error = f"Unknown tool: {task.tool}"
            return task
        try:
            task.result = await runner(task.params)
            task.status = AgentStatus.COMPLETE
        except Exception as exc:
            task.status = AgentStatus.ERROR
            task.error = str(exc)
        return task

    async def run_goal(self, goal: str) -> dict:
        """Plan and execute all tasks for a security goal."""
        session = self.new_session(goal)
        tasks = await self.plan(goal)
        session.tasks = tasks

        completed = []
        for task in tasks:
            result = await self.execute_task(task)
            completed.append(result)

        summary = await self._summarize(goal, completed)
        return {
            "session_id": session.session_id,
            "goal": goal,
            "tasks": [self._serialize_task(t) for t in completed],
            "summary": summary,
        }

    # ── Chat ──────────────────────────────────────────────────────

    async def chat(self, message: str, session_id: Optional[str] = None) -> tuple:
        """Interactive chat. Returns (response, session_id)."""
        if session_id and session_id in self.sessions:
            session = self.sessions[session_id]
        else:
            session = self.new_session()
            session_id = session.session_id

        msgs = [SystemMessage(content=self.SYSTEM_PROMPT)]
        for h in session.history:
            if h["role"] == "user":
                msgs.append(HumanMessage(content=h["content"]))
            else:
                msgs.append(AIMessage(content=h["content"]))
        msgs.append(HumanMessage(content=message))

        response = self.llm.invoke(msgs)
        reply = response.content
        session.history.append({"role": "user", "content": message})
        session.history.append({"role": "assistant", "content": reply})
        return reply, session_id

    # ── Summarization ─────────────────────────────────────────────

    async def _summarize(self, goal: str, tasks: list) -> str:
        task_lines = []
        for t in tasks:
            line = f"- [{t.tool}] {t.name}: {t.status.value}"
            if t.result:
                count = t.result.get("count", "")
                if count:
                    line += f" ({count} findings)"
            if t.error:
                line += f" ERROR: {t.error}"
            task_lines.append(line)

        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Security goal: {goal}\n\nTask results:\n"
                    + "\n".join(task_lines)
                    + "\n\nProvide a concise, structured security assessment "
                    "with key findings and recommendations."
                )
            ),
        ]
        response = self.llm.invoke(messages)
        return response.content

    # ── Tool runners ──────────────────────────────────────────────

    async def _run_gitleaks(self, params: dict) -> dict:
        path = params.get("path", ".")
        if not shutil.which("gitleaks"):
            return {
                "status": "unavailable",
                "message": "gitleaks not installed — see github.com/gitleaks/gitleaks",
                "findings": [],
                "count": 0,
            }
        proc = await asyncio.create_subprocess_exec(
            "gitleaks", "detect",
            "--source", path,
            "--report-format", "json",
            "--report-path", "/tmp/gitleaks_ghost.json",
            "--no-git",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        try:
            with open("/tmp/gitleaks_ghost.json") as f:
                findings = json.load(f)
        except Exception:
            findings = []
        return {
            "status": "complete",
            "tool": "gitleaks",
            "path": path,
            "findings": findings[:10],
            "count": len(findings),
        }

    async def _run_trufflehog(self, params: dict) -> dict:
        target = params.get("target", ".")
        if not shutil.which("trufflehog"):
            return {
                "status": "unavailable",
                "message": "trufflehog not installed — see github.com/trufflesecurity/trufflehog",
                "findings": [],
                "count": 0,
            }
        proc = await asyncio.create_subprocess_exec(
            "trufflehog", "filesystem", target, "--json", "--no-update",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        findings = []
        for line in stdout.decode().splitlines():
            try:
                findings.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return {
            "status": "complete",
            "tool": "trufflehog",
            "target": target,
            "findings": findings[:10],
            "count": len(findings),
        }

    async def _run_commix(self, params: dict) -> dict:
        url = params.get("url")
        if not url:
            return {"status": "error", "message": "url parameter required"}
        if not shutil.which("commix"):
            return {
                "status": "unavailable",
                "message": "commix not installed — see github.com/commixproject/commix",
            }
        proc = await asyncio.create_subprocess_exec(
            "commix", "--url", url, "--batch",
            "--output-dir", "/tmp/commix_ghost",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = stdout.decode()[:3000]
        except asyncio.TimeoutError:
            proc.kill()
            output = "Scan timed out after 120s"
        return {"status": "complete", "tool": "commix", "url": url, "output": output}

    async def _run_w3af(self, params: dict) -> dict:
        url = params.get("url")
        if not url:
            return {"status": "error", "message": "url parameter required"}
        profile = (
            f"plugins\n"
            f"use discovery web_spider\n"
            f"use audit xss sqli csrf os_commanding\n"
            f"use output console\n"
            f"use output xml_file\n"
            f"output config xml_file\n"
            f"set output_file /tmp/ghost_w3af_results.xml\n"
            f"back\n"
            f"target\n"
            f"set target {url}\n"
            f"back\n"
            f"start\n"
        )
        return {
            "status": "queued",
            "tool": "w3af",
            "url": url,
            "message": "Run: w3af_console -s /tmp/ghost_w3af.w3af",
            "profile": profile,
        }

    async def _run_threat_intel(self, params: dict) -> dict:
        query = params.get("query", "")
        if not query:
            return {"status": "error", "message": "query parameter required"}
        try:
            from search import search_dark_web
            results = search_dark_web(query)
            summary = generate_summary(self.llm, query, str(results[:5]))
            return {
                "status": "complete",
                "tool": "threat_intel",
                "query": query,
                "result_count": len(results),
                "summary": summary,
            }
        except ImportError:
            return {"status": "error", "message": "search module unavailable"}

    @staticmethod
    def _serialize_task(task: AgentTask) -> dict:
        return {
            "id": task.id,
            "name": task.name,
            "tool": task.tool,
            "params": task.params,
            "status": task.status.value,
            "result": task.result,
            "error": task.error,
        }

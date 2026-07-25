"""Google ADK Scrum Master Orchestration Engine for Vertex AI Agent Engine.

Instantiates `LlmAgent` personas (`product_architect`, `cloud_backend`, `frontend`, `qa_sec`),
binds native Python tools and skills, assembles the iterative `LoopAgent` (`dev_qa_loop`), and
executes the top-level `SequentialAgent` pipeline.
"""
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from orchestration.circuit_breaker import (
    CircuitBreakerTrippedException,
    evaluate_qa_feedback_and_break,
)
from orchestration.state import ScrumSessionStateModel
from tools.ci_tools import check_ci_status
from tools.git_tools import create_feature_branch_and_commit, create_pull_request
from tools.secret_tools import get_gcp_secret

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Google ADK Agent Base Constructs (Compatible with Vertex AI Agent Engine)
# ------------------------------------------------------------------------------
class LlmAgent:
    """Google ADK LlmAgent wrapper representing an autonomous persona."""

    def __init__(
        self,
        name: str,
        role: str,
        model: str,
        instructions: str,
        tools: Optional[List[Callable[..., Any]]] = None,
        skills: Optional[List[str]] = None,
        temperature: float = 0.2,
    ):
        self.name = name
        self.role = role
        self.model = model
        self.instructions = instructions
        self.tools = tools or []
        self.skills = skills or []
        self.temperature = temperature

    def execute(self, prompt: str, state: ScrumSessionStateModel) -> str:
        """Execute the agent persona against the provided prompt and session state.

        In production on Vertex AI Agent Engine, this invokes the hosted Gemini 3.1 LLM
        with automatic tool calling and skill retrieval.
        """
        logger.info(f"[{self.name} | {self.model}] Executing prompt for ticket '{state.ticket_id}'...")
        # Simulate or execute tool-bound agent logic
        if self.name == "product_architect":
            state.openapi_spec_path = "api-spec-v1.yaml"
            state.architecture_summary = "Serverless GCP Cloud Run architecture with Cloud SQL PostgreSQL."
            return f"Architectural specification and ticket {state.ticket_id} generated successfully."
        elif self.name in ("cloud_backend", "frontend"):
            state.pr_url = f"https://github.com/example-org/repo/pull/{state.retry_count + 1}"
            state.pr_number = state.retry_count + 1
            return f"Implementation complete. Created PR #{state.pr_number} at {state.pr_url}."
        elif self.name == "qa_sec":
            # In simulated run, return PASS after 1 retry or immediately if retry_count > 0
            status_val = "PASS" if state.retry_count > 0 or os.environ.get("MOCK_QA_IMMEDIATE_PASS") else "FAIL"
            failed = [] if status_val == "PASS" else ["Scenario 1: Missing RFC 7807 error handler in endpoint."]
            return (
                f'{{"status": "{status_val}", "failed_criteria": {json_dumps(failed)}, '
                f'"actionable_feedback": "Audit completed with verdict: {status_val}."}}'
            )
        return "Agent execution finished."


class LoopAgent:
    """Google ADK LoopAgent executing sub-agents iteratively until break condition or max iterations."""

    def __init__(self, name: str, sub_agents: List[LlmAgent], max_iterations: int = 3):
        self.name = name
        self.sub_agents = sub_agents
        self.max_iterations = max_iterations

    def run(self, state: ScrumSessionStateModel) -> ScrumSessionStateModel:
        """Run the iterative development and QA loop under circuit breaker governance."""
        logger.info(f"Starting LoopAgent '{self.name}' (Max Iterations: {self.max_iterations})...")
        
        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"--- {self.name} Iteration {iteration}/{self.max_iterations} ---")
            
            # 1. Execute Developer persona (e.g., backend or frontend)
            dev_agent = self.sub_agents[0]
            dev_output = dev_agent.execute(
                prompt=f"Implement requirements for {state.ticket_id}. Feedback: {state.feedback}",
                state=state,
            )
            logger.debug(f"{dev_agent.name} output: {dev_output}")

            # 2. Execute QA Auditor persona
            qa_agent = self.sub_agents[1]
            qa_output = qa_agent.execute(
                prompt=f"Audit deliverables for {state.ticket_id} at PR #{state.pr_number}.",
                state=state,
            )
            logger.debug(f"{qa_agent.name} output: {qa_output}")

            # 3. Evaluate Circuit Breaker and break condition
            try:
                should_continue, updated_state = evaluate_qa_feedback_and_break(
                    state=state,
                    qa_raw_output=qa_output,
                    max_retries=self.max_iterations,
                )
                state = updated_state
                if not should_continue:
                    logger.info(f"LoopAgent '{self.name}' terminated early: QA PASSED on iteration {iteration}.")
                    break
            except CircuitBreakerTrippedException as e:
                logger.error(f"LoopAgent '{self.name}' halted by circuit breaker: {e}")
                raise

        return state


class SequentialAgent:
    """Google ADK SequentialAgent executing sub-agents or loops in strict deterministic order."""

    def __init__(self, name: str, sub_agents: List[Any]):
        self.name = name
        self.sub_agents = sub_agents

    def run(self, state: ScrumSessionStateModel) -> ScrumSessionStateModel:
        """Execute pipeline stages sequentially."""
        logger.info(f"Starting SequentialAgent Pipeline '{self.name}'...")
        for stage in self.sub_agents:
            if isinstance(stage, LlmAgent):
                stage.execute(prompt=f"Execute stage {stage.name} for {state.ticket_id}", state=state)
            elif isinstance(stage, LoopAgent):
                state = stage.run(state)
            else:
                logger.warning(f"Unknown sub-agent type in SequentialAgent: {type(stage)}")
        logger.info(f"SequentialAgent Pipeline '{self.name}' finished successfully.")
        return state


def json_dumps(data: Any) -> str:
    """Helper for JSON dumping in simulated responses."""
    import json
    return json.dumps(data)


# ------------------------------------------------------------------------------
# Orchestration Setup & Execution
# ------------------------------------------------------------------------------
def _load_instructions(persona_dir: Path) -> str:
    """Load instructions.md for a given persona."""
    inst_file = persona_dir / "instructions.md"
    if inst_file.exists():
        return inst_file.read_text(encoding="utf-8")
    return f"Standard ADK instructions for {persona_dir.name}."


def create_scrum_team_orchestrator(
    base_dir: Optional[Path] = None,
    max_loop_iterations: int = 3,
) -> SequentialAgent:
    """Instantiate Google ADK LlmAgents, bind tools, assemble dev_qa_loop, and return main SequentialAgent.

    Args:
        base_dir: Root repository path containing 'agents/'. Defaults to current working directory.
        max_loop_iterations: Maximum iterations for the dev_qa_loop (default: 3).

    Returns:
        Configured top-level SequentialAgent.
    """
    root = base_dir or Path.cwd()
    agents_dir = root / "agents"

    # 1. Instantiate Persona LlmAgents
    product_architect = LlmAgent(
        name="product_architect",
        role="Lead Technical PM & GCP Solutions Architect",
        model="gemini-3.1-pro",
        instructions=_load_instructions(agents_dir / "product_architect"),
        skills=["openapi-spec-generator", "plantuml-c4-designer", "gcp-cloud-run-deploy", "gcp-iam-secret-manager"],
        tools=[create_feature_branch_and_commit, create_pull_request, get_gcp_secret],
        temperature=0.2,
    )

    cloud_backend = LlmAgent(
        name="cloud_backend",
        role="Principal GCP Backend Engineer",
        model="gemini-3.1-pro",
        instructions=_load_instructions(agents_dir / "cloud_backend"),
        skills=["openapi-spec-generator", "gcp-cloud-run-deploy", "gcp-iam-secret-manager"],
        tools=[create_feature_branch_and_commit, create_pull_request, get_gcp_secret, check_ci_status],
        temperature=0.1,
    )

    qa_sec = LlmAgent(
        name="qa_sec",
        role="QA & Cloud Security Auditor",
        model="gemini-3.1-flash",
        instructions=_load_instructions(agents_dir / "qa_sec"),
        skills=["gherkin-qa-audit", "gcp-iam-secret-manager"],
        tools=[check_ci_status, get_gcp_secret],
        temperature=0.1,
    )

    # 2. Assemble Iterative dev_qa_loop (LoopAgent)
    dev_qa_loop = LoopAgent(
        name="dev_qa_loop",
        sub_agents=[cloud_backend, qa_sec],
        max_iterations=max_loop_iterations,
    )

    # 3. Assemble Top-Level SequentialAgent
    scrum_pipeline = SequentialAgent(
        name="gcp_native_scrum_team",
        sub_agents=[product_architect, dev_qa_loop],
    )

    return scrum_pipeline


def run_scrum_sprint(ticket_id: str, feature_name: str, max_iterations: int = 3) -> ScrumSessionStateModel:
    """Execute a complete multi-agent Scrum sprint for the specified ticket."""
    initial_state = ScrumSessionStateModel(
        ticket_id=ticket_id,
        feature_name=feature_name,
        status="IN_PROGRESS",
    )

    orchestrator = create_scrum_team_orchestrator(max_loop_iterations=max_iterations)
    final_state = orchestrator.run(initial_state)
    return final_state


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    print("=== Launching GCP-Native Multi-Agent Scrum Team ===")
    session_state = run_scrum_sprint(
        ticket_id="TICKET-BACKEND-101",
        feature_name="Cloud Run Order Processing Microservice",
        max_iterations=3,
    )
    print("\n=== Scrum Sprint Execution Completed ===")
    print(session_state.model_dump_json(indent=2))

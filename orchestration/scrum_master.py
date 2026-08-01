"""Google ADK Scrum Master Orchestration Engine for Vertex AI Agent Engine.

Instantiates `LlmAgent` personas (`product_architect`, `cloud_backend`, `frontend`, `qa_sec`),
dynamically loads configs from `config.yaml` and `instructions.md`, binds native Python tools,
assembles the iterative `LoopAgent`, and executes the main `SequentialAgent` pipeline.
"""

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from google import genai
from google.genai import types
from ruamel.yaml import YAML

from orchestration.circuit_breaker import (
    CircuitBreakerTrippedError,
    evaluate_qa_feedback_and_break,
)
from orchestration.state import ScrumSessionStateModel
from tools.ci_tools import check_ci_status
from tools.git_tools import create_feature_branch_and_commit, create_pull_request
from tools.secret_tools import get_gcp_secret

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Configuration & Instructions Loader
# ------------------------------------------------------------------------------
def load_persona_config(persona_dir: Path) -> dict[str, Any]:
    """Load configuration from config.yaml and instructions from instructions.md."""
    config_file = persona_dir / "config.yaml"
    inst_file = persona_dir / "instructions.md"

    config_data: dict[str, Any] = {}
    if config_file.exists():
        yaml = YAML(typ="safe")
        with config_file.open("r", encoding="utf-8") as f:
            config_data = yaml.load(f) or {}

    instructions = ""
    if inst_file.exists():
        instructions = inst_file.read_text(encoding="utf-8")

    agent_meta = config_data.get("agent", {})
    model_meta = agent_meta.get("model", {})

    return {
        "name": agent_meta.get("name", persona_dir.name),
        "role": agent_meta.get("role", f"Scrum Persona {persona_dir.name}"),
        "model": model_meta.get("engine", "gemini-3.1-pro"),
        "temperature": model_meta.get("temperature", 0.2),
        "top_p": model_meta.get("top_p", 0.95),
        "max_output_tokens": model_meta.get("max_output_tokens", 8192),
        "safety_settings": model_meta.get("safety_settings", {}),
        "skills": agent_meta.get("skills", []),
        "tool_names": agent_meta.get("tools", []),
        "instructions": instructions,
    }


TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "git_tools.create_feature_branch_and_commit": create_feature_branch_and_commit,
    "git_tools.create_pull_request": create_pull_request,
    "secret_tools.get_gcp_secret": get_gcp_secret,
    "ci_tools.check_ci_status": check_ci_status,
}


def bind_tools_from_names(
    tool_names: list[str], default_tools: list[Callable[..., Any]] | None = None
) -> list[Callable[..., Any]]:
    """Map tool name strings from config.yaml to Python callable functions."""
    if not tool_names and default_tools:
        return default_tools
    bound = []
    for name in tool_names:
        if name in TOOL_REGISTRY:
            bound.append(TOOL_REGISTRY[name])
        else:
            logger.warning(f"Tool '{name}' requested in config.yaml not found in TOOL_REGISTRY.")
    return bound or (default_tools or [])


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
        tools: list[Callable[..., Any]] | None = None,
        skills: list[str] | None = None,
        temperature: float = 0.2,
        top_p: float = 0.95,
        max_output_tokens: int = 8192,
        safety_settings: dict[str, Any] | None = None,
    ):
        self.name = name
        self.role = role
        self.model = model
        self.instructions = instructions
        self.tools = tools or []
        self.skills = skills or []
        self.temperature = temperature
        self.top_p = top_p
        self.max_output_tokens = max_output_tokens
        self.safety_settings = safety_settings or {}

    def execute(self, prompt: str, state: ScrumSessionStateModel) -> str:
        """Execute the agent persona against the provided prompt and session state.

        In production on Vertex AI Agent Engine, this invokes the hosted Gemini 3.1 LLM
        with automatic tool calling and skill retrieval.
        """
        logger.info(
            f"[{self.name} | {self.model}] Executing prompt for ticket '{state.ticket_id}'..."
        )

        try:
            # We use Vertex AI credentials if available, otherwise fallback
            loc = os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west2")
            client = genai.Client(vertexai=True, location=loc)
        except Exception:
            client = genai.Client()

        # Dynamic tool for state mutation
        def update_session_state(
            pr_url: str = "",
            pr_number: int = 0,
            architecture_summary: str = "",
            openapi_spec_path: str = "",
            prd_content: str = "",
            arch_spec_content: str = "",
        ) -> str:
            """Updates the central Scrum session state.

            Args:
                pr_url: The URL of the raised pull request.
                pr_number: The integer PR number.
                architecture_summary: High level summary of architecture.
                openapi_spec_path: Path to openapi spec.
                prd_content: Product requirement document text.
                arch_spec_content: Architecture spec text.
            """
            if pr_url:
                state.pr_url = pr_url
            if pr_number:
                state.pr_number = pr_number
            if architecture_summary:
                state.architecture_summary = architecture_summary
            if openapi_spec_path:
                state.openapi_spec_path = openapi_spec_path
            if prd_content:
                state.prd_content = prd_content
            if arch_spec_content:
                state.arch_spec_content = arch_spec_content
            return "Session state updated successfully."

        # Bind tools
        active_tools = list(self.tools) if self.tools else []
        if self.name != "qa_sec":
            active_tools.append(update_session_state)

        config = types.GenerateContentConfig(
            system_instruction=self.instructions,
            temperature=self.temperature,
            top_p=self.top_p,
            max_output_tokens=self.max_output_tokens,
            tools=active_tools if active_tools else None,
        )

        if self.name == "qa_sec":
            config.response_mime_type = "application/json"

        # Append state to the prompt
        full_prompt = f"{prompt}\n\nCurrent Session State:\n{state.model_dump_json(indent=2)}"

        try:
            chat = client.chats.create(model=self.model, config=config)
            response = chat.send_message(full_prompt)
            # Log state changes
            if self.name != "qa_sec":
                state.record_iteration(
                    self.name, "llm_execution", "SUCCESS", "LLM completed execution and tool calls."
                )
            return response.text or ""
        except Exception as e:
            logger.error(f"Error calling LLM for {self.name}: {e}")
            if self.name == "qa_sec":
                import json
                return json.dumps({
                    "status": "FAIL",
                    "failed_criteria": [f"Critical API Failure: {e}"],
                    "actionable_feedback": (
                        "The LLM API call failed. Verify Vertex AI model "
                        "availability, regions, and permissions."
                    )
                })
            return f"Error executing agent {self.name}: {e}"


class LoopAgent:
    """Google ADK LoopAgent executing sub-agents iteratively until break condition or max limit."""

    def __init__(self, name: str, sub_agents: list[LlmAgent], max_iterations: int = 3):
        self.name = name
        self.sub_agents = sub_agents
        self.max_iterations = max_iterations

    def run(self, state: ScrumSessionStateModel) -> ScrumSessionStateModel:
        """Run the iterative development and QA loop under circuit breaker governance."""
        logger.info(f"Starting LoopAgent '{self.name}' (Max Iterations: {self.max_iterations})...")

        # Separate developer personas from auditor personas dynamically without hardcoded indices
        developers = [
            agent
            for agent in self.sub_agents
            if agent.name != "qa_sec" and not agent.name.startswith("qa")
        ]
        auditors = [
            agent
            for agent in self.sub_agents
            if agent.name == "qa_sec" or agent.name.startswith("qa")
        ]

        if not developers and self.sub_agents:
            developers = [self.sub_agents[0]]
        if not auditors and len(self.sub_agents) > 1:
            auditors = [self.sub_agents[-1]]

        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"--- {self.name} Iteration {iteration}/{self.max_iterations} ---")

            # 1. Execute Developer persona matching ticket category dynamically
            active_devs = []
            if state.ticket_type == "FRONTEND":
                active_devs = [
                    d for d in developers if "frontend" in d.name.lower() or "ui" in d.name.lower()
                ]
            elif state.ticket_type == "BACKEND":
                active_devs = [
                    d
                    for d in developers
                    if "backend" in d.name.lower() or "cloud" in d.name.lower()
                ]
            elif state.ticket_type == "FULLSTACK":
                active_devs = developers

            if not active_devs:
                active_devs = [developers[0]] if developers else []

            for target_dev in active_devs:
                dev_prompt = (
                    f"Implement requirements for {state.ticket_id} ({state.ticket_type}). "
                    f"Feedback: {state.feedback}"
                )
                dev_output = target_dev.execute(
                    prompt=dev_prompt,
                    state=state,
                )
                logger.debug(f"{target_dev.name} output: {dev_output}")

            # 2. Execute QA Auditor persona
            qa_agent = auditors[0] if auditors else self.sub_agents[-1]
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
                    verify_ci_func=check_ci_status,
                )
                state = updated_state
                if not should_continue:
                    logger.info(
                        f"LoopAgent '{self.name}' terminated early: "
                        f"QA PASSED on iteration {iteration}."
                    )
                    break
            except CircuitBreakerTrippedError as e:
                logger.error(f"LoopAgent '{self.name}' halted by circuit breaker: {e}")
                raise

        return state


class SequentialAgent:
    """Google ADK SequentialAgent executing sub-agents or loops in strict deterministic order."""

    def __init__(self, name: str, sub_agents: list[Any]):
        self.name = name
        self.sub_agents = sub_agents

    def run(self, state: ScrumSessionStateModel) -> ScrumSessionStateModel:
        """Execute pipeline stages sequentially."""
        logger.info(f"Starting SequentialAgent Pipeline '{self.name}'...")
        for stage in self.sub_agents:
            if isinstance(stage, LlmAgent):
                stage.execute(
                    prompt=f"Execute stage {stage.name} for {state.ticket_id}", state=state
                )
            elif isinstance(stage, LoopAgent):
                state = stage.run(state)
            else:
                logger.warning(f"Unknown sub-agent type in SequentialAgent: {type(stage)}")
        logger.info(f"SequentialAgent Pipeline '{self.name}' finished successfully.")
        return state

    def query(
        self,
        ticket_id: str = "TICKET-001",
        ticket_type: str = "BACKEND",
        description: str = "Execute Scrum workflow",
        repo_name: str = "owner/repo",
        branch_name: str = "main",
        state_dict: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Vertex AI Reasoning Engine API entrypoint."""
        if state_dict:
            state = ScrumSessionStateModel.from_typed_dict(state_dict)
        else:
            state = ScrumSessionStateModel(
                ticket_id=ticket_id,
                feature_name=description,
                ticket_type=ticket_type,
                repo_name=repo_name,
                branch_name=branch_name,
            )
        result_state = self.run(state)
        return cast(dict[str, Any], result_state.to_typed_dict())


# ------------------------------------------------------------------------------
# Orchestration Setup & Execution
# ------------------------------------------------------------------------------
def create_scrum_team_orchestrator(
    base_dir: Path | None = None,
    max_loop_iterations: int = 3,
) -> SequentialAgent:
    """Instantiate ADK LlmAgents from config.yaml, bind tools, and return main SequentialAgent.

    Args:
        base_dir: Root repository path containing 'agents/'. Defaults to current working directory.
        max_loop_iterations: Maximum iterations for the dev_qa_loop (default: 3).

    Returns:
        Configured top-level SequentialAgent.
    """
    root = base_dir or Path.cwd()
    agents_dir = root / "agents"

    # Load persona configurations dynamically from config.yaml and instructions.md
    pa_cfg = load_persona_config(agents_dir / "product_architect")
    cb_cfg = load_persona_config(agents_dir / "cloud_backend")
    fe_cfg = load_persona_config(agents_dir / "frontend")
    qa_cfg = load_persona_config(agents_dir / "qa_sec")

    # 1. Instantiate Persona LlmAgents with dynamic config loading (tools & safety settings)
    product_architect = LlmAgent(
        name=pa_cfg["name"],
        role=pa_cfg["role"],
        model=pa_cfg["model"],
        instructions=pa_cfg["instructions"],
        skills=pa_cfg["skills"],
        tools=bind_tools_from_names(
            pa_cfg.get("tool_names", []),
            [create_feature_branch_and_commit, create_pull_request, get_gcp_secret],
        ),
        temperature=pa_cfg["temperature"],
        top_p=pa_cfg["top_p"],
        max_output_tokens=pa_cfg["max_output_tokens"],
        safety_settings=pa_cfg.get("safety_settings"),
    )

    cloud_backend = LlmAgent(
        name=cb_cfg["name"],
        role=cb_cfg["role"],
        model=cb_cfg["model"],
        instructions=cb_cfg["instructions"],
        skills=cb_cfg["skills"],
        tools=bind_tools_from_names(
            cb_cfg.get("tool_names", []),
            [
                create_feature_branch_and_commit,
                create_pull_request,
                get_gcp_secret,
                check_ci_status,
            ],
        ),
        temperature=cb_cfg["temperature"],
        top_p=cb_cfg["top_p"],
        max_output_tokens=cb_cfg["max_output_tokens"],
        safety_settings=cb_cfg.get("safety_settings"),
    )

    frontend = LlmAgent(
        name=fe_cfg["name"],
        role=fe_cfg["role"],
        model=fe_cfg["model"],
        instructions=fe_cfg["instructions"],
        skills=fe_cfg["skills"],
        tools=bind_tools_from_names(
            fe_cfg.get("tool_names", []),
            [
                create_feature_branch_and_commit,
                create_pull_request,
                get_gcp_secret,
                check_ci_status,
            ],
        ),
        temperature=fe_cfg["temperature"],
        top_p=fe_cfg["top_p"],
        max_output_tokens=fe_cfg["max_output_tokens"],
        safety_settings=fe_cfg.get("safety_settings"),
    )

    qa_sec = LlmAgent(
        name=qa_cfg["name"],
        role=qa_cfg["role"],
        model=qa_cfg["model"],
        instructions=qa_cfg["instructions"],
        skills=qa_cfg["skills"],
        tools=bind_tools_from_names(
            qa_cfg.get("tool_names", []), [check_ci_status, get_gcp_secret]
        ),
        temperature=qa_cfg["temperature"],
        top_p=qa_cfg["top_p"],
        max_output_tokens=qa_cfg["max_output_tokens"],
        safety_settings=qa_cfg.get("safety_settings"),
    )

    # 2. Assemble specialized parallel/dual-track dev-QA loops
    backend_qa_loop = LoopAgent(
        name="backend_qa_loop",
        sub_agents=[cloud_backend, qa_sec],
        max_iterations=max_loop_iterations,
    )

    frontend_qa_loop = LoopAgent(
        name="frontend_qa_loop",
        sub_agents=[frontend, qa_sec],
        max_iterations=max_loop_iterations,
    )

    # Combined dual-track dev_qa_loop supporting FULLSTACK, BACKEND, and FRONTEND execution
    dev_qa_loop = LoopAgent(
        name="dev_qa_loop",
        sub_agents=[cloud_backend, frontend, qa_sec],
        max_iterations=max_loop_iterations,
    )

    # 3. Assemble Top-Level SequentialAgent
    scrum_pipeline = SequentialAgent(
        name="gcp_native_scrum_team",
        sub_agents=[product_architect, dev_qa_loop],
    )
    # Expose specialized loops as attributes on the pipeline for direct access
    scrum_pipeline.backend_qa_loop = backend_qa_loop  # type: ignore
    scrum_pipeline.frontend_qa_loop = frontend_qa_loop  # type: ignore
    scrum_pipeline.dev_qa_loop = dev_qa_loop  # type: ignore

    return scrum_pipeline


def run_scrum_sprint(
    ticket_id: str,
    feature_name: str,
    ticket_type: str = "BACKEND",
    max_iterations: int = 3,
) -> ScrumSessionStateModel:
    """Execute a complete multi-agent Scrum sprint for the specified ticket."""
    initial_state = ScrumSessionStateModel(
        ticket_id=ticket_id,
        feature_name=feature_name,
        ticket_type=ticket_type,
        status="IN_PROGRESS",
    )

    orchestrator = create_scrum_team_orchestrator(max_loop_iterations=max_iterations)
    final_state = orchestrator.run(initial_state)
    return final_state


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    print("=== Launching GCP-Native Multi-Agent Scrum Team ===")
    session_state = run_scrum_sprint(
        ticket_id="TICKET-BACKEND-101",
        feature_name="Cloud Run Order Processing Microservice",
        ticket_type="BACKEND",
        max_iterations=3,
    )
    print("\n=== Scrum Sprint Execution Completed ===")
    print(session_state.model_dump_json(indent=2))

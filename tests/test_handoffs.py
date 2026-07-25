"""Unit and integration tests for Google ADK Agent Orchestration and Circuit Breaker handoffs.

Verifies state serialization, QA JSON evaluation, retry counter incrementation, circuit breaker
tripping, iteration recording, dynamic config loading, and full sequential/loop agent pipeline execution.
"""
import pytest
from orchestration.circuit_breaker import (
    CircuitBreakerTrippedException,
    evaluate_qa_feedback_and_break,
)
from orchestration.scrum_master import (
    LlmAgent,
    LoopAgent,
    SequentialAgent,
    create_scrum_team_orchestrator,
)
from orchestration.state import ScrumSessionStateModel


@pytest.mark.unit
def test_scrum_session_state_model_serialization() -> None:
    """Test Pydantic model serialization and TypedDict conversion with expanded fields."""
    state = ScrumSessionStateModel(
        ticket_id="TICKET-BACKEND-001",
        feature_name="Order Processing API",
        ticket_type="BACKEND",
        repo_name="owner/repo",
        branch_name="feature/orders",
        status="IN_PROGRESS",
    )
    assert state.retry_count == 0
    assert state.ci_passed is False
    assert state.ticket_type == "BACKEND"

    state.record_iteration("cloud_backend", "commit", "SUCCESS", "Pushed commit")
    assert len(state.iteration_history) == 1
    assert state.iteration_history[0]["persona"] == "cloud_backend"

    typed_dict = state.to_typed_dict()
    assert typed_dict["ticket_id"] == "TICKET-BACKEND-001"
    assert typed_dict["repo_name"] == "owner/repo"

    restored = ScrumSessionStateModel.from_typed_dict(typed_dict)
    assert restored.ticket_id == state.ticket_id
    assert restored.branch_name == "feature/orders"


@pytest.mark.unit
def test_evaluate_qa_feedback_pass() -> None:
    """Test that a QA PASS verdict immediately terminates the sprint loop."""
    state = ScrumSessionStateModel(ticket_id="TEST-001", feature_name="Test Feature")
    qa_output = '```json\n{\n  "status": "PASS",\n  "failed_criteria": [],\n  "actionable_feedback": "Looks great."\n}\n```'

    should_continue, updated = evaluate_qa_feedback_and_break(state, qa_output, max_retries=3)
    assert should_continue is False
    assert updated.status == "PASS"
    assert updated.ci_passed is True
    assert updated.retry_count == 0
    assert len(updated.iteration_history) == 1


@pytest.mark.unit
def test_evaluate_qa_feedback_nested_json_parsing() -> None:
    """Test that QA output containing nested JSON structures parses correctly without regex truncation."""
    state = ScrumSessionStateModel(ticket_id="TEST-002", feature_name="Nested JSON Test")
    qa_output = """
    ```json
    {
      "status": "FAIL",
      "failed_criteria": [
        "Scenario 1: Endpoint returned 500 error",
        "Security: Raw SQL string interpolation found"
      ],
      "details": {
        "error_code": "ERR_500",
        "nested_info": {
          "field": "user_id"
        }
      },
      "actionable_feedback": "Fix parameterized queries and catch auth error."
    }
    ```
    """
    should_continue, updated = evaluate_qa_feedback_and_break(state, qa_output, max_retries=3)
    assert should_continue is True
    assert updated.status == "FAIL"
    assert updated.retry_count == 1
    assert len(updated.failed_criteria) == 2


@pytest.mark.unit
def test_evaluate_qa_feedback_circuit_breaker_tripped() -> None:
    """Test that exceeding max_retries trips the circuit breaker exception."""
    state = ScrumSessionStateModel(ticket_id="TEST-001", feature_name="Test Feature", retry_count=2)
    qa_output = '{"status": "FAIL", "failed_criteria": ["Still failing."], "actionable_feedback": "Try again."}'

    with pytest.raises(CircuitBreakerTrippedException) as exc_info:
        evaluate_qa_feedback_and_break(state, qa_output, max_retries=3)

    assert exc_info.value.state.status == "CIRCUIT_BROKEN"
    assert exc_info.value.state.retry_count == 3


@pytest.mark.unit
def test_loop_agent_frontend_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that LoopAgent correctly executes frontend persona when ticket_type is FRONTEND."""
    monkeypatch.setenv("MOCK_QA_IMMEDIATE_PASS", "true")

    backend_agent = LlmAgent(name="cloud_backend", role="Backend Dev", model="gemini-3.1-pro", instructions="Dev")
    frontend_agent = LlmAgent(name="frontend", role="Frontend Dev", model="gemini-3.1-flash", instructions="Frontend")
    qa_agent = LlmAgent(name="qa_sec", role="QA Auditor", model="gemini-3.1-flash", instructions="QA")

    loop = LoopAgent(name="test_loop", sub_agents=[backend_agent, frontend_agent, qa_agent], max_iterations=3)

    state = ScrumSessionStateModel(ticket_id="TICKET-FRONTEND-001", feature_name="React Dashboard UI", ticket_type="FRONTEND")
    final_state = loop.run(state)

    assert final_state.status == "PASS"
    assert final_state.ci_passed is True


@pytest.mark.unit
def test_full_sequential_orchestration_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test full sequential pipeline (product_architect -> dev_qa_loop with dynamic configs)."""
    monkeypatch.setenv("MOCK_QA_IMMEDIATE_PASS", "true")

    orchestrator = create_scrum_team_orchestrator(max_loop_iterations=3)
    state = ScrumSessionStateModel(ticket_id="TEST-SEQ-1", feature_name="Sequential Test", ticket_type="BACKEND")

    final_state = orchestrator.run(state)

    assert final_state.openapi_spec_path == "api-spec-v1.yaml"
    assert final_state.pr_url is not None
    assert final_state.status == "PASS"
    assert final_state.ci_passed is True

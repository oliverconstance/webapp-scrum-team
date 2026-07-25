"""Unit and integration tests for Google ADK Agent Orchestration and Circuit Breaker handoffs.

Verifies state serialization, QA JSON evaluation, retry counter incrementation, circuit breaker
tripping, and full sequential/loop agent pipeline execution.
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
    """Test Pydantic model serialization and TypedDict conversion."""
    state = ScrumSessionStateModel(
        ticket_id="TICKET-BACKEND-001",
        feature_name="Order Processing API",
        status="IN_PROGRESS",
    )
    assert state.retry_count == 0
    assert state.ci_passed is False

    typed_dict = state.to_typed_dict()
    assert typed_dict["ticket_id"] == "TICKET-BACKEND-001"
    assert typed_dict["status"] == "IN_PROGRESS"

    restored = ScrumSessionStateModel.from_typed_dict(typed_dict)
    assert restored.ticket_id == state.ticket_id


@pytest.mark.unit
def test_evaluate_qa_feedback_pass() -> None:
    """Test that a QA PASS verdict immediately terminates the sprint loop."""
    state = ScrumSessionStateModel(ticket_id="TEST-001", feature_name="Test Feature")
    qa_output = '{"status": "PASS", "failed_criteria": [], "actionable_feedback": "Looks great."}'

    should_continue, updated = evaluate_qa_feedback_and_break(state, qa_output, max_retries=3)
    assert should_continue is False
    assert updated.status == "PASS"
    assert updated.ci_passed is True
    assert updated.retry_count == 0


@pytest.mark.unit
def test_evaluate_qa_feedback_fail_and_retry() -> None:
    """Test that a QA FAIL verdict increments retry count and continues the loop."""
    state = ScrumSessionStateModel(ticket_id="TEST-001", feature_name="Test Feature", retry_count=1)
    qa_output = '{"status": "FAIL", "failed_criteria": ["Scenario 2 failed."], "actionable_feedback": "Fix 500 error."}'

    should_continue, updated = evaluate_qa_feedback_and_break(state, qa_output, max_retries=3)
    assert should_continue is True
    assert updated.status == "FAIL"
    assert updated.retry_count == 2
    assert "Scenario 2 failed." in updated.failed_criteria


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
def test_loop_agent_early_termination(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that LoopAgent terminates early when QA passes on iteration 1."""
    monkeypatch.setenv("MOCK_QA_IMMEDIATE_PASS", "true")

    dev_agent = LlmAgent(name="cloud_backend", role="Backend Dev", model="gemini-3.1-pro", instructions="Dev")
    qa_agent = LlmAgent(name="qa_sec", role="QA Auditor", model="gemini-3.1-flash", instructions="QA")
    loop = LoopAgent(name="test_loop", sub_agents=[dev_agent, qa_agent], max_iterations=3)

    state = ScrumSessionStateModel(ticket_id="TEST-LOOP-1", feature_name="Loop Test")
    final_state = loop.run(state)

    assert final_state.status == "PASS"
    assert final_state.retry_count == 0
    assert final_state.ci_passed is True


@pytest.mark.unit
def test_full_sequential_orchestration_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test full sequential pipeline (product_architect -> dev_qa_loop)."""
    monkeypatch.setenv("MOCK_QA_IMMEDIATE_PASS", "true")

    orchestrator = create_scrum_team_orchestrator(max_loop_iterations=3)
    state = ScrumSessionStateModel(ticket_id="TEST-SEQ-1", feature_name="Sequential Test")

    final_state = orchestrator.run(state)

    assert final_state.openapi_spec_path == "api-spec-v1.yaml"
    assert final_state.pr_url is not None
    assert final_state.status == "PASS"
    assert final_state.ci_passed is True

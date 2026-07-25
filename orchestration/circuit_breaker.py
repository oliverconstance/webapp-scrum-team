"""Circuit Breaker logic for Google ADK Multi-Agent Scrum Workflows.

Evaluates QA JSON audit responses (`{"status": "PASS"|"FAIL", ...}`), updates session state,
increments retry counters, and trips the circuit breaker if retry thresholds (`retry_count >= 3`)
are exceeded to prevent infinite LLM execution loops and budget exhaustion.
"""
import json
import logging
import re
from typing import Any, Dict, Tuple

from orchestration.state import ScrumSessionStateModel

logger = logging.getLogger(__name__)

DEFAULT_CIRCUIT_BREAKER_THRESHOLD = 3


class CircuitBreakerTrippedException(Exception):
    """Exception raised when the maximum sprint retry threshold is reached."""

    def __init__(self, message: str, state: ScrumSessionStateModel):
        super().__init__(message)
        self.state = state


def _extract_json_from_llm_output(raw_output: str) -> Dict[str, Any]:
    """Extract and parse a JSON object from raw LLM output strings.

    Handles standard JSON strings as well as markdown-formatted JSON code blocks.

    Args:
        raw_output: Raw text output from the qa_sec agent.

    Returns:
        Parsed dictionary.

    Raises:
        ValueError: If no valid JSON object can be extracted or parsed.
    """
    cleaned = raw_output.strip()

    # Attempt to extract from markdown fenced code block
    json_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if json_block_match:
        cleaned = json_block_match.group(1).strip()
    elif not (cleaned.startswith("{") and cleaned.endswith("}")):
        # Attempt to find first '{' and last '}'
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
            cleaned = cleaned[start_idx : end_idx + 1]

    try:
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError("Extracted JSON is not an object/mapping.")
        return data
    except Exception as e:
        logger.error(f"Failed to parse QA JSON response:\n{raw_output}\nError: {e}")
        raise ValueError(f"Circuit breaker failed to parse QA JSON response: {e}") from e


def evaluate_qa_feedback_and_break(
    state: ScrumSessionStateModel,
    qa_raw_output: str,
    max_retries: int = DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
) -> Tuple[bool, ScrumSessionStateModel]:
    """Evaluate qa_sec audit response, update state, and check circuit breaker threshold.

    Args:
        state: Current ScrumSessionStateModel instance.
        qa_raw_output: Raw JSON string emitted by the qa_sec agent.
        max_retries: Maximum permitted retries before tripping circuit breaker (default: 3).

    Returns:
        Tuple of (should_continue_loop: bool, updated_state: ScrumSessionStateModel).

    Raises:
        CircuitBreakerTrippedException: If retry_count >= max_retries after a FAIL verdict.
    """
    logger.info(f"Evaluating QA feedback for ticket '{state.ticket_id}' (Current retry count: {state.retry_count}).")

    try:
        qa_data = _extract_json_from_llm_output(qa_raw_output)
    except ValueError as e:
        # If QA fails to emit valid JSON, treat as an audit failure and increment retry
        logger.warning(f"Invalid QA output format. Incrementing retry count. Details: {e}")
        state.retry_count += 1
        state.feedback = f"QA Agent emitted invalid JSON format: {e}. Please adhere strictly to JSON schema."
        state.status = "FAIL"
        if state.retry_count >= max_retries:
            state.status = "CIRCUIT_BROKEN"
            raise CircuitBreakerTrippedException(
                f"Circuit breaker tripped for '{state.ticket_id}': Exceeded {max_retries} retries due to invalid QA output format.",
                state=state,
            ) from e
        return True, state

    status = str(qa_data.get("status", "")).upper()
    failed_criteria = qa_data.get("failed_criteria", [])
    feedback = str(qa_data.get("actionable_feedback", "No feedback provided."))

    if not isinstance(failed_criteria, list):
        failed_criteria = [str(failed_criteria)]

    state.feedback = feedback
    state.failed_criteria = [str(c) for c in failed_criteria]

    if status == "PASS":
        logger.info(f"QA Audit PASSED for ticket '{state.ticket_id}'. Terminating sprint loop successfully.")
        state.status = "PASS"
        state.ci_passed = True
        return False, state  # Do not continue loop; sprint complete

    if status == "FAIL":
        state.retry_count += 1
        state.status = "FAIL"
        state.ci_passed = False
        logger.warning(
            f"QA Audit FAILED for ticket '{state.ticket_id}'. Incremented retry count to {state.retry_count}/{max_retries}.\n"
            f"Failed criteria: {state.failed_criteria}\nFeedback: {state.feedback}"
        )

        if state.retry_count >= max_retries:
            state.status = "CIRCUIT_BROKEN"
            logger.error(f"CIRCUIT BREAKER TRIPPED for ticket '{state.ticket_id}'. Halting execution.")
            raise CircuitBreakerTrippedException(
                f"Circuit breaker tripped for '{state.ticket_id}': Exceeded {max_retries} retries without QA PASS verdict.",
                state=state,
            )

        return True, state  # Continue loop for next developer sprint remediation

    # Handle unexpected status strings
    logger.error(f"Unknown QA status string '{status}'. Treating as FAIL.")
    state.retry_count += 1
    state.status = "FAIL"
    state.feedback = f"QA returned unrecognized status '{status}'. Expected 'PASS' or 'FAIL'. {feedback}"
    if state.retry_count >= max_retries:
        state.status = "CIRCUIT_BROKEN"
        raise CircuitBreakerTrippedException(
            f"Circuit breaker tripped for '{state.ticket_id}': Exceeded {max_retries} retries.",
            state=state,
        )
    return True, state

"""Circuit Breaker logic for Google ADK Multi-Agent Scrum Workflows.

Evaluates QA JSON audit responses (`{"status": "PASS"|"FAIL", ...}`), updates session state,
records iteration history, increments retry counters, and trips the circuit breaker if retry thresholds
(`retry_count >= 3`) are exceeded to prevent infinite LLM execution loops and budget exhaustion.
"""
import json
import logging
from typing import Any, Dict, Optional, Tuple

from orchestration.state import ScrumSessionStateModel

logger = logging.getLogger(__name__)

DEFAULT_CIRCUIT_BREAKER_THRESHOLD = 3


class CircuitBreakerTrippedException(Exception):
    """Exception raised when the maximum sprint retry threshold is reached."""

    def __init__(self, message: str, state: ScrumSessionStateModel):
        super().__init__(message)
        self.state = state


def _extract_json_from_llm_output(raw_output: str) -> Dict[str, Any]:
    """Extract and parse a JSON object from raw LLM output strings using brace tracking.

    Handles standard JSON strings as well as markdown-formatted JSON code blocks containing
    nested JSON objects or arrays without truncation bugs.

    Args:
        raw_output: Raw text output from the qa_sec agent.

    Returns:
        Parsed dictionary.

    Raises:
        ValueError: If no valid JSON object can be extracted or parsed.
    """
    cleaned = raw_output.strip()

    # Step 1: Strip outer markdown fenced code block delimiters if present
    if "```" in cleaned:
        lines = cleaned.splitlines()
        code_lines = []
        inside_block = False
        for line in lines:
            if line.strip().startswith("```"):
                if inside_block:
                    break  # End of fenced block
                inside_block = True
                continue
            if inside_block:
                code_lines.append(line)
        if code_lines:
            cleaned = "\n".join(code_lines).strip()

    # Step 2: Use brace balancing to find the outermost '{' and '}'
    start_idx = cleaned.find("{")
    if start_idx == -1:
        raise ValueError("No open brace '{' found in raw output string.")

    depth = 0
    end_idx = -1
    in_string = False
    escape = False

    for i in range(start_idx, len(cleaned)):
        char = cleaned[i]

        if escape:
            escape = False
            continue

        if char == "\\" and in_string:
            escape = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if not in_string:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break

    if end_idx == -1:
        # Fallback to last index of '}'
        end_idx = cleaned.rfind("}")
        if end_idx == -1 or end_idx <= start_idx:
            raise ValueError("No matching closing brace '}' found in raw output string.")

    json_str = cleaned[start_idx : end_idx + 1]

    try:
        data = json.loads(json_str)
        if not isinstance(data, dict):
            raise ValueError("Extracted JSON payload is not a mapping object.")
        return data
    except Exception as e:
        logger.error(f"Failed to parse QA JSON payload:\n{json_str}\nError: {e}")
        raise ValueError(f"Circuit breaker failed to parse QA JSON response: {e}") from e


def evaluate_qa_feedback_and_break(
    state: ScrumSessionStateModel,
    qa_raw_output: str,
    max_retries: int = DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
    verify_ci_func: Optional[Any] = None,
) -> Tuple[bool, ScrumSessionStateModel]:
    """Evaluate qa_sec audit response, update state, record history, and check circuit breaker threshold.

    Args:
        state: Current ScrumSessionStateModel instance.
        qa_raw_output: Raw JSON string emitted by the qa_sec agent.
        max_retries: Maximum permitted retries before tripping circuit breaker (default: 3).
        verify_ci_func: Optional check_ci_status callable to verify real CI build state on PASS.

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
        state.record_iteration("qa_sec", "audit", "INVALID_FORMAT", state.feedback)

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
        # Optionally double-verify real CI status if function and PR info provided
        if verify_ci_func and state.repo_name and state.pr_number:
            try:
                ci_res = verify_ci_func(state.repo_name, state.pr_number)
                if not ci_res.get("ci_passed", False):
                    logger.warning(f"QA output PASS, but GitHub CI checks failed for PR #{state.pr_number}.")
                    state.retry_count += 1
                    state.status = "FAIL"
                    state.ci_passed = False
                    state.feedback = f"QA auditor approved PR, but automated GitHub CI checks failed: {ci_res.get('state_summary')}."
                    state.record_iteration("circuit_breaker", "ci_check", "FAIL", state.feedback)
                    if state.retry_count >= max_retries:
                        state.status = "CIRCUIT_BROKEN"
                        raise CircuitBreakerTrippedException(
                            f"Circuit breaker tripped for '{state.ticket_id}': Exceeded retries due to failing CI checks.",
                            state=state,
                        )
                    return True, state
            except Exception as e:
                logger.error(f"Error executing verify_ci_func: {e}")

        logger.info(f"QA Audit PASSED for ticket '{state.ticket_id}'. Terminating sprint loop successfully.")
        state.status = "PASS"
        state.ci_passed = True
        state.record_iteration("qa_sec", "audit", "PASS", feedback)
        return False, state  # Do not continue loop; sprint complete

    if status == "FAIL":
        state.retry_count += 1
        state.status = "FAIL"
        state.ci_passed = False
        state.record_iteration("qa_sec", "audit", "FAIL", feedback)

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
    state.record_iteration("qa_sec", "audit", "UNKNOWN_STATUS", state.feedback)

    if state.retry_count >= max_retries:
        state.status = "CIRCUIT_BROKEN"
        raise CircuitBreakerTrippedException(
            f"Circuit breaker tripped for '{state.ticket_id}': Exceeded {max_retries} retries.",
            state=state,
        )
    return True, state

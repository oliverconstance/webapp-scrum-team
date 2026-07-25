---
name: gherkin-qa-audit
description: Standard operating procedure (SOP) for evaluating backend API and frontend UX deliverables against Gherkin BDD acceptance criteria, OWASP Top 10 security baselines, and GCP IAM least-privilege standards.
---

# Gherkin QA & Security Audit Skill

This skill defines the mandatory standard operating procedure (SOP) for conducting rigorous quality assurance and cloud security auditing on all software deliverables produced within the multi-agent Scrum team. Audits evaluate functional compliance against Gherkin BDD scenarios (`Feature`, `Scenario`, `Given`, `When`, `Then`), verify adherence to OWASP Top 10 security standards, and inspect GCP IAM and Secret Manager hygiene.

When executing this skill as the `qa_sec` agent, you MUST return your final audit verdict as a strict, syntactically valid JSON object. Do not include introductory markdown chatter outside the JSON code block if consumed programmatically by the circuit breaker.

## Prerequisites
- Access to the target execution ticket (`TICKET-BACKEND-*.md` or `TICKET-FRONTEND-*.md`) containing Gherkin acceptance criteria.
- Access to the generated pull request diffs, code artifacts, OpenAPI specifications, and Terraform/IAM definitions.
- Automated testing framework (pytest, cypress, playwright, or gherkin parser) available in CI/CD.

## Step-by-Step Procedure

### Step 1: Audit Functional Compliance (Gherkin Acceptance Criteria)
For each `Scenario` defined in the execution ticket:
1. Verify that code implements the exact precondition state specified in `Given`.
2. Trace the execution path triggered by the action in `When`.
3. Assert that the returned HTTP status codes, JSON payloads, or UX visual state transitions match `Then`.
4. If auditing frontend React/Next.js components, explicitly verify that all five core UX states are implemented and tested: **Ideal**, **Loading**, **Error**, **Empty**, and **Degraded**.

### Step 2: Audit Cloud Security & OWASP Top 10 Compliance
Inspect source code and configuration manifests against critical security vulnerabilities:
1. **Injection (SQL/NoSQL/Command)**: Ensure ORM parameterized queries or SQLAlchemy/SQLModel binding is used; reject raw string interpolation in database queries.
2. **Broken Authentication & Authorization**: Verify endpoints enforce valid JWT/OIDC bearer token verification or Knative IAM invoker authentication (`--no-allow-unauthenticated`).
3. **Sensitive Data Exposure**: Ensure no plaintext passwords, API keys, or private certificates are embedded in source code or Dockerfiles. Verify retrieval from GCP Secret Manager via `google-cloud-secretmanager`.
4. **IAM Over-Privileging**: Verify that GCP service accounts do not bind primitive `roles/owner` or `roles/editor`. Require granular resource-level bindings (e.g., `roles/secretmanager.secretAccessor`, `roles/run.invoker`).

### Step 3: Emit Strict JSON Feedback
After completing the audit, compile all findings into a strict JSON payload. The circuit breaker in `orchestration/circuit_breaker.py` consumes this payload to determine whether to transition to deployment or trigger a remediation sprint.

#### JSON Schema
```json
{
  "status": "PASS | FAIL",
  "failed_criteria": [
    "Scenario 2: User login fails with 500 instead of RFC 7807 401 Unauthorized",
    "Security: Hardcoded fallback API key found in src/config.py"
  ],
  "actionable_feedback": "Detailed instructions on what the backend or frontend engineer must fix to pass the audit."
}
```

## Verification & Troubleshooting

### Verification Command
To test JSON syntax and simulate QA validation against sample outputs:

```bash
# Validate that QA feedback output is valid JSON
python -c 'import json, sys; data=json.load(sys.stdin); assert data["status"] in ("PASS", "FAIL"); print("JSON schema valid.")' < qa_output.json
```

### Common Errors and Solutions
- **Error: `Circuit breaker failed to parse QA response: Expecting value: line 1 column 1 (char 0)`**
  - *Solution*: Ensure the LLM output contains only the JSON object without surrounding conversational filler (e.g., "Here is my audit report: ..."). Use markdown JSON code block formatting or raw JSON.
- **Error: `status is neither PASS nor FAIL`**
  - *Solution*: Ensure case sensitivity: use `"PASS"` or `"FAIL"`, never `"passed"`, `"success"`, or `"true"`.

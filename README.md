# GCP-Native Multi-Agent Scrum Team (Google ADK & Vertex AI Agent Engine)

An enterprise-grade, autonomous software development team powered by **Google Cloud Platform (GCP)**, **Google Agent Development Kit (ADK)**, and **Vertex AI Agent Engine**. This repository scaffolds a complete multi-agent workflow orchestration system designed to natively architect, implement, test, and deploy cloud-native software systems.

---

## 🏗️ System Architecture & Workflow Orchestration

The system orchestrates four specialized AI personas into an agile Scrum workflow using Google ADK's `SequentialAgent` and `LoopAgent` constructs:

```
+-----------------------------------------------------------------------------------+
|                                 SequentialAgent                                   |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |                             product_architect                               |  |
|  |  (Gemini 3.1 Pro) - Drafts PRDs, ADRs, C4 Models, OpenAPI Specs & Tickets   |  |
|  +-----------------------------------------------------------------------------+  |
|                                        |                                          |
|                                        v                                          |
|  +-----------------------------------------------------------------------------+  |
|  |                            dev_qa_loop (LoopAgent)                          |  |
|  |  Max Iterations: 3 | Controlled by Circuit Breaker                          |  |
|  |                                                                             |  |
|  |     +-------------------------+              +------------------------+     |  |
|  |     |      cloud_backend      | <----------> |        qa_sec          |     |  |
|  |     | (Gemini 3.1 Pro/Node/Py)|              |  (Gemini 3.1 Flash/QA) |     |  |
|  |     +-------------------------+              +------------------------+     |  |
|  |                  ^                                       ^                  |  |
|  |                  |                                       |                  |  |
|  |                  v                                       v                  |  |
|  |     +-------------------------+              +------------------------+     |  |
|  |     |        frontend         | <----------> |     Circuit Breaker    |     |  |
|  |     | (Gemini 3.1 Flash/React)|              |   (State & Retries)    |     |  |
|  |     +-------------------------+              +------------------------+     |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## 👥 Persona Definitions (`agents/`)

| Persona | Model | Role & Responsibilities | Bound Skills |
| :--- | :--- | :--- | :--- |
| **`product_architect`** | `gemini-3.1-pro` | Lead Technical PM & Solutions Architect. Generates PRDs, ADRs, 6-domain architecture specs, OpenAPI 3.1 contracts, PlantUML C4 diagrams, and discrete backend/frontend execution tickets. | `openapi-spec-generator`, `plantuml-c4-designer`, `gcp-cloud-run-deploy`, `gcp-iam-secret-manager` |
| **`cloud_backend`** | `gemini-3.1-pro` | Principal Backend Engineer. Implements Node.js/TypeScript or Python FastAPI services based on OpenAPI specs. Builds multi-stage Dockerfiles and Terraform/IaC modules for Cloud Run. | `openapi-spec-generator`, `gcp-cloud-run-deploy`, `gcp-iam-secret-manager` |
| **`frontend`** | `gemini-3.1-flash` | Senior Frontend Engineer. Develops responsive React/Next.js and Tailwind CSS applications wired to Cloud Run REST endpoints, handling 5 core UX states (Ideal, Loading, Error, Empty, Degraded). | `openapi-spec-generator` |
| **`qa_sec`** | `gemini-3.1-flash` | QA & Cloud Security Auditor. Evaluates Gherkin acceptance criteria, OWASP Top 10 compliance, IAM least privilege, and Secret Manager hygiene. Outputs strict JSON feedback. | `gherkin-qa-audit`, `gcp-iam-secret-manager` |

---

## 🧠 Agent Skills Matrix (`.agent/skills/`)

All skills adhere to the [agentskills.io](https://agentskills.io) specification and cross-reference Google's official cloud skills standards ([github.com/google/skills](https://github.com/google/skills/tree/main/skills/cloud)):

1. **`openapi-spec-generator`**: Standard operating procedure (SOP) for drafting OpenAPI 3.1 contracts, accompanied by Python validation scripts (`validate_yaml.py`) and standard RFC 7807 error schema templates.
2. **`plantuml-c4-designer`**: Procedural guide for authoring C4 Container and Sequence architectural diagrams.
3. **`gcp-cloud-run-deploy`**: Comprehensive SOP for containerizing microservices and deploying serverless applications to Google Cloud Run using `gcloud` CLI and Terraform.
4. **`gcp-iam-secret-manager`**: Guidelines for implementing least-privilege IAM service accounts and binding runtime secrets securely via Google Cloud Secret Manager.
5. **`gherkin-qa-audit`**: SOP for QA validation and security auditing against Gherkin behavior-driven development (BDD) suites and cloud security baselines.

---

## 🛠️ Executable Python Tools (`tools/`)

The team uses fully typed, production-ready Python tools integrated with GCP and GitHub APIs:
- `tools/git_tools.py`: Branch creation, commit authoring, and Pull Request generation via `PyGithub`.
- `tools/secret_tools.py`: Secure runtime secret retrieval from Google Cloud Secret Manager using least-privilege service accounts.
- `tools/ci_tools.py`: Real-time CI/CD workflow and Pull Request check status verification.

---

## 🔄 Orchestration & State Management (`orchestration/`)

- **`state.py`**: Defines `ScrumSessionState` using Pydantic and TypedDict for robust state sharing across agents (tracking ticket IDs, PR URLs, CI build status, retry counts, and QA feedback).
- **`circuit_breaker.py`**: Evaluates QA JSON outputs (`PASS`/`FAIL`), increments retry counters, and triggers execution pauses if `retry_count >= 3` to prevent infinite LLM loops and budget exhaustion.
- **`scrum_master.py`**: Instantiates Google ADK `LlmAgent` personas, binds native tools, constructs the iterative `LoopAgent` (`dev_qa_loop`), and executes the top-level `SequentialAgent`.

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.11+
- [Poetry](https://python-poetry.org/) or `uv`
- Google Cloud SDK (`gcloud`) authenticated to your GCP project
- GitHub Personal Access Token or GitHub App credentials

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/your-org/gcp-multiagent-scrum-team.git
cd gcp-multiagent-scrum-team

# Install dependencies
poetry install
```

### 3. Environment Configuration
Copy the sample environment file and populate your GCP and GitHub credentials:
```bash
cp .env.example .env
```

### 4. Running the Multi-Agent Team
```bash
# Execute the Scrum Master orchestration script
poetry run python -m orchestration.scrum_master
```

### 5. Running Tests & Validation
```bash
# Run all unit and integration tests
poetry run pytest

# Validate YAML frontmatter across all skills
poetry run python .agent/skills/openapi-spec-generator/scripts/validate_yaml.py
```

---

## 🤖 CI/CD & Deployment (`.github/workflows/`)

- **`agent-ci.yml`**: Automatically validates skill YAML frontmatter, executes pytest test suites, and enforces code linting on every Pull Request.
- **`deploy-agents.yml`**: Deploys the multi-agent system to GCP Vertex AI Agent Engine using secure Workload Identity Federation (WIF) upon merging to `main`.

---

## 📜 License
Apache License 2.0 - See LICENSE for details.

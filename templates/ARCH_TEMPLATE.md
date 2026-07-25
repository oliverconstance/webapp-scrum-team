# 6-Domain System Architecture Specification: [System Name]

**Document Control**
- **Lead Architect**: Principal GCP Solutions Architect (`product_architect`)
- **Version**: 1.0.0
- **Status**: Draft / Approved

---

## Domain 1: Frontend Architecture
- **Framework**: React 18+, Next.js 14+ (App Router).
- **Styling**: Tailwind CSS utility-first design system with responsive breakpoints and dark mode.
- **Hosting & CDN**: Deployed to Google Cloud Run (containerized Next.js server) or Firebase Hosting CDN for static assets.
- **State & Caching**: SWR / TanStack Query for client-side API caching and optimistic UI updates.
- **UX Reliability**: Mandatory implementation of all **5 core UX states**: Ideal, Loading (skeleton pulses), Error (RFC 7807 banners), Empty (friendly CTA), and Degraded (cached fallbacks).

---

## Domain 2: API Gateway & Ingress
- **Ingress Controller**: GCP Cloud Run serverless Knative ingress routing with regional HTTPS endpoints.
- **Contract Specification**: OpenAPI 3.1 YAML specification (`api-spec-*.yaml`) enforced at build and test time.
- **Error Standardization**: Strict adherence to RFC 7807 problem details (`type`, `title`, `status`, `detail`, `instance`).
- **CORS & Rate Limiting**: Explicit CORS origin whitelist; API rate limiting via Google Cloud Armor or Cloud API Gateway.

---

## Domain 3: Compute Layer (Serverless)
- **Primary Compute Platform**: Google Cloud Run (2nd Gen execution environment).
- **Container Sizing**: Default allocation: 1 vCPU, 1024MiB RAM per container instance.
- **Concurrency & Autoscaling**: 
  - `containerConcurrency: 80` requests per container.
  - Autoscaling bounds: `min-instances: 1` (to prevent cold start latency on critical paths), `max-instances: 10`.
- **Performance Optimizations**: Enabled Startup CPU Boost (`run.googleapis.com/startup-cpu-boost: "true"`) and disabled CPU throttling where background async workers require continuous CPU.

---

## Domain 4: Storage & Data Persistence Layer
- **Relational Database**: Google Cloud SQL for PostgreSQL 15+.
- **Connection Security**: Cloud SQL Auth Proxy sidecar or Private Service Connect (VPC Native) with IAM database authentication.
- **ORM & Migrations**: SQLAlchemy 2.0 / SQLModel (Python) or Prisma / Drizzle ORM (Node.js TypeScript). Automated schema migrations executed in CI/CD pipeline before traffic cutover.
- **NoSQL / Caching (Optional)**: Cloud Firestore (Native Mode) for real-time document sync and session state persistence.

---

## Domain 5: Event Bus & Asynchronous Workflows
- **Message Broker**: Google Cloud Pub/Sub for decoupled, event-driven publish/subscribe messaging between microservices.
- **Task Orchestration**: Google Cloud Tasks for structured, rate-controlled pull/push queues with exponential backoff retries.
- **Dead-Letter Queues (DLQ)**: All Pub/Sub subscriptions and Cloud Tasks must specify a DLQ target after 5 failed delivery attempts to prevent poison pill message loops.

---

## Domain 6: Security, IAM & Observability
- **Least-Privilege IAM**: Zero primitive roles (`roles/owner`, `roles/editor`). Dedicated runtime service accounts scoped strictly to required resources (`roles/run.invoker`, `roles/secretmanager.secretAccessor`, `roles/cloudtrace.agent`).
- **Runtime Secrets**: Zero plaintext environment variables. All secrets retrieved dynamically at runtime from Google Cloud Secret Manager using `secret_tools.py` via Workload Identity Federation.
- **Distributed Tracing & Logging**: Cloud Trace integration via OpenTelemetry; Google Cloud Logging structured JSON logs with trace ID correlation injected into every log entry.

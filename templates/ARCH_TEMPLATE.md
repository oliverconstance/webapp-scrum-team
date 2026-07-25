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

## Domain 2: API Gateway, Edge Ingress & WAF Security
- **Edge Load Balancing**: Global External Application Load Balancer (GCLB) with Serverless Network Endpoint Groups (NEGs) targeting Cloud Run services in `europe-west2` (London).
- **DNS & TLS**: Google Cloud DNS managed zones with Google-managed SSL/TLS certificates (`compute_managed_ssl_certificate`) terminating HTTPS at the edge.
- **WAF Security Policies**: Google Cloud Armor security policies (`google_compute_security_policy`) attached to the GCLB, enforcing OWASP Top 10 rules against SQL injection, XSS, rate limiting, and layer-7 DDoS mitigation.
- **Contract Specification**: OpenAPI 3.1 YAML specification (`api-spec-*.yaml`) enforced at build and test time, strictly adhering to RFC 7807 problem detail error responses.

---

## Domain 3: Compute Layer (Serverless)
- **Primary Compute Platform**: Google Cloud Run (2nd Gen execution environment, deployed in `europe-west2` / London).
- **Container Sizing**: Default allocation: 1 vCPU, 1024MiB RAM per container instance.
- **Concurrency & Autoscaling**: 
  - `containerConcurrency: 80` requests per container.
  - Autoscaling bounds: `min-instances: 1` (to prevent cold start latency on critical paths), `max-instances: 10`.
- **Performance Optimizations**: Enabled Startup CPU Boost (`run.googleapis.com/startup-cpu-boost: "true"`) and disabled CPU throttling where background async workers require continuous CPU.

---

## Domain 4: Storage & Data Persistence Layer
- **Relational Database**: Google Cloud SQL for PostgreSQL 15+ deployed in `europe-west2` (London).
- **Private VPC Networking**: Serverless VPC Access Connector or Direct VPC Egress so Cloud Run connects to Cloud SQL over RFC 1918 private internal IP addresses without public internet routing.
- **Connection Security**: Cloud SQL Auth Proxy sidecar or Private Service Connect with IAM database authentication.
- **ORM & Migrations**: SQLAlchemy 2.0 / SQLModel (Python) or Prisma / Drizzle ORM (Node.js TypeScript). Automated schema migrations executed in CI/CD pipeline before traffic cutover.
- **NoSQL / Caching (Optional)**: Cloud Firestore (Native Mode) or Memorystore for Redis for real-time document sync and session state caching.

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

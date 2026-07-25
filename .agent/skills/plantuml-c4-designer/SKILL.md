---
name: plantuml-c4-designer
description: Procedural guide and standard operating procedure (SOP) for drafting C4 Container and C4 Sequence architectural diagrams using PlantUML for GCP-native systems. Use this skill when creating architecture documentation, visual design specifications, or system boundary models.
---

# PlantUML C4 Designer Skill

This skill defines the mandatory standard operating procedure (SOP) for authoring C4 Container and C4 Sequence architectural diagrams using PlantUML (`.puml`) for software systems deployed on Google Cloud Platform (GCP). All diagrams must utilize C4-PlantUML standard macros, clearly define GCP service boundaries, and illustrate asynchronous and synchronous interactions between personas and cloud components.

## Prerequisites
- PlantUML rendering engine or IDE plugin (e.g., VS Code PlantUML extension) installed.
- Access to the official C4-PlantUML standard library macros (`C4_Container.puml` and `C4_Sequence.puml`).
- Comprehensive understanding of the system's 6-domain architecture specification (Frontend, API Gateway, Compute, Storage, Event Bus, Security/IAM).

## Step-by-Step Procedure

### Step 1: Draft C4 Container Diagrams
When documenting system components, create a C4 Container diagram illustrating how external actors and systems interact with internal GCP containers (Cloud Run, Cloud SQL, Firestore, Pub/Sub, Secret Manager).

1. Include the C4 standard header: `!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Container.puml`.
2. Declare external actors using `Person(alias, "Label", "Description")`.
3. Group GCP resources inside a boundary using `System_Boundary(alias, "GCP Project Boundary")`.
4. Declare compute services (e.g., Cloud Run) using `Container(alias, "Label", "Technology", "Description")`.
5. Declare data stores (e.g., Cloud SQL, Firestore) using `ContainerDb(alias, "Label", "Technology", "Description")`.
6. Define explicit relationships with directionality and protocols: `Rel(from, to, "Action", "Protocol/HTTPS/gRPC")`.

### Step 2: Draft C4 Sequence Diagrams
When detailing specific execution workflows (e.g., authentication, transaction processing, asynchronous event handling), create a C4 Sequence diagram.

1. Include the C4 sequence header: `!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Sequence.puml`.
2. Define participants representing actors, frontend clients, API endpoints, microservices, and databases.
3. Use synchronous arrow notation (`->`) for blocking REST/gRPC requests.
4. Use asynchronous arrow notation (`-->` or `-x`) for Pub/Sub event emissions and webhook callbacks.
5. Include activation blocks (`activate`/`deactivate`) and notes (`note right of`) to clarify state changes or error handling paths.

### Step 3: Validate and Format Diagram Code
1. Ensure all diagram files end with `.puml`.
2. Enforce standard formatting: `@startuml` on line 1, `@enduml` on the final line.
3. Remove unused definitions and ensure syntax compatibility with PlantUML 1.2023+.

## Verification & Troubleshooting

### Verification Command
To test syntax and generate PNG/SVG diagrams locally using PlantUML command line or Docker:

```bash
# Using local plantuml JAR or CLI
plantuml -tpng path/to/diagram.puml

# Or via Docker if local PlantUML is unavailable
docker run --rm -v $(pwd):/work ghcr.io/plantuml/plantuml -tpng /work/path/to/diagram.puml
```

### Common Errors and Solutions
- **Error: `Cannot include https://raw.githubusercontent.com/...`**
  - *Solution*: Ensure network connectivity or replace remote URLs with offline cached copies of `C4_Container.puml` in air-gapped CI/CD pipelines.
- **Error: `Syntax error: Unrecognized macro ContainerDb`**
  - *Solution*: Verify that `!include` points to `C4_Container.puml` (not `C4_Context.puml` or `C4_Component.puml`).

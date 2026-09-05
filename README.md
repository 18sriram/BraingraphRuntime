# BrainGraph Runtime

BrainGraph Runtime is a local AI orchestration runtime designed for autonomous coding workflows. The current implementation includes infrastructure bootstrapping, a graph-backed memory engine, and deterministic context retrieval without LLM calls.

## Project structure

- `backend/` – FastAPI service, config, database, graph, repository, and service layers
- `frontend/` – Next.js app and dashboard UI shell
- `shared/` – shared types and contracts for future cross-stack use
- `backend/app/memory/` – graph, artifact, episodic memory layers and context builder
- `backend/app/gateway/` – provider-independent model gateway and provider adapters
- `backend/app/safety/` – action parser, deterministic policy, risk classifier, approvals, sandbox, and audit logging
- `docker-compose.yml` – local infrastructure stack definition
- `.env.example` – environment variables for local development
- `Makefile` – convenience commands for bootstrapping and compose operations

## Quick start

1. Copy the environment file:
   `cp .env.example .env`
2. Launch the stack:
   `docker compose up --build`
3. Open the services:
   - Backend API: http://localhost:8000/docs
   - Frontend: http://localhost:3000
   - Neo4j browser: http://localhost:7474

## CLI

Install the CLI from the repository root with `pip install -e .`. Run `bg init` from any project directory to enter its name, choose from the available databases, register the workspace, and create `.braingraph/braingraph.json`, `.braingraph/state.json`, `.braingraph/logs/`, `.braingraph/artifacts/`, and `.braingraph/checkpoints/`. The CLI detects the current directory automatically.

Use `bg start`, `bg stop`, and `bg status` for local services. `bg start` opens the registered workspace, verifies Neo4j, initializes the Brain Graph, records runtime state, and opens the dashboard. Select a model provider with `bg start --provider openai`, `bg start --provider claude`, or `bg start --provider gemini`. Database and workspace operations are available through `bg db list`, `bg db add`, `bg db use`, `bg workspace list`, and `bg workspace open`. Use `bg graph export` and `bg graph import <file>` for graph backups.

`bg graph export` writes `braingraph_export.json` containing workspace metadata, Neo4j nodes, relationships, and artifact references. Import reconstructs the graph in the active workspace database using stable logical keys and Neo4j `MERGE`, so repeated imports do not duplicate graph entities.

   ### Multi-database workspaces

   The runtime can register multiple local Neo4j instances and switch the active workspace database. Passwords are encrypted with Fernet before they are stored in SQLite. Set `DATABASE_ENCRYPTION_KEY` to a generated Fernet key for a stable deployment key; when it is empty, the backend creates a local `.database.key` file.

   Database management endpoints:

   - `GET /api/databases` – list registered databases
   - `POST /api/databases` – register a database
   - `PUT /api/databases/{id}` – update database settings
   - `DELETE /api/databases/{id}` – remove a database
   - `POST /api/databases/{id}/activate` – select the active database
   - `GET /api/databases/active` – get the selected database

   Project workspaces can be registered against any configured database. Project paths are normalized and unique. Opening a workspace through `POST /api/workspaces/{id}/switch` verifies connectivity to its assigned Neo4j database before updating `last_opened`.

   Workspace endpoints:

   - `GET /api/workspaces` – list registered workspaces
   - `POST /api/workspaces` – register a project workspace
   - `GET /api/workspaces/{id}` – get workspace details
   - `POST /api/workspaces/{id}/switch` – open and switch to a workspace
   - `DELETE /api/workspaces/{id}` – remove a workspace registration

   `GET /api/workspaces/{id}/context` returns the structured default workspace context, including workspace metadata, Git state, relevant graph nodes, current task, and database ID. The agent loop includes this context in every planning request sent to the model when a workspace context builder is configured.

   The directory watcher mirrors supported file creation and modification events into `File` graph nodes with path, SHA-256 hash, language, modification time, and workspace ID properties. Deleted files remain in Brain Graph with `archived=true`; file changes are never sent to the LLM.

   AgentRuntime state is persisted in SQLite and accepts explicit events through `POST /api/agent-runtime/{task_id}/events`. Current state is available from `GET /api/agent-runtime/{task_id}` and the dashboard WebSocket at `/ws/dashboard?task_id={task_id}`. The state machine supports `OFF`, `READY`, `WAITING_FOR_QUOTA`, `SENDING_FIRST_PROMPT`, `PLANNING`, `EXECUTING`, `OBSERVING`, `DECISION`, `UPDATING_MEMORY`, `PAUSED`, `SUCCESS`, `FAILED`, and `ABORTED`.

## Included infrastructure

- FastAPI backend with a health route
- Next.js frontend shell
- Neo4j graph database container
- SQLite metadata foundation
- Docker Compose environment for local orchestration
- Three graph-backed memory layers: structured graph knowledge, artifact references, and agent episodes
- Two-hop `ContextBuilder` retrieval for task context, files, decisions, errors, experiments, constraints, and relationships
- Provider-independent model gateway for OpenAI, Anthropic, and Gemini
- Environment-controlled provider selection, request timeouts, and transient-failure retries
- Finite-state agent loop with planning, execution, observation, memory updates, pause, quota, and termination states
- Safety Engine with `SAFE`, `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL` risk levels
- Project-scoped filesystem access and Docker command execution with network disabled by default
- Configurable CPU, memory, timeout, and JSONL audit logging limits for sandbox execution
- Structured sandbox reports containing status, stdout, stderr, exit code, timeout, and duration
- Quota-aware scheduler with persisted pending work, configurable delayed checks, automatic resume, and REST status endpoints
- Git integration with automatic checkpoints, diff generation, rollback, and graph-stored commit metadata
- Watchdog directory watcher for Python, TypeScript, JSON, and Markdown file nodes
- Durable AgentRuntime finite-state workflow with persisted transitions and live state events

## Current status

Implemented and tested:

- Graph CRUD and deterministic two-hop memory retrieval
- Graph, artifact, and episodic memory layers
- Provider-independent OpenAI, Anthropic, and Gemini model gateway
- Strict JSON LLM protocol with validation and serialization
- Agent Loop finite-state workflow with persisted in-memory state
- Safety policy, risk classification, approvals, Docker sandbox, and audit logging

The current repository uses an in-memory graph implementation for local tests. Neo4j is defined in Docker Compose but the production Neo4j repository adapter and end-to-end container validation remain future integration work.

The Model Gateway is ready for later orchestration use. Configure `MODEL_PROVIDER` as `openai`, `anthropic`, or `gemini`, provide the matching API key, and adjust `MODEL_TIMEOUT_SECONDS` or `MODEL_MAX_RETRIES` as needed. Callers use the shared `ChatRequest` and `ChatResponse` contract and do not select provider-specific clients.

The Agent Loop Engine is available through `AgentLoopEngine.run(task_id, objective)`. Each iteration builds graph context, requests a structured JSON plan, checks actions with the Safety Engine, executes allowed actions, records observations as graph results, and persists state. It terminates on success, no progress, iteration limit, pause, user abort, quota exhaustion, or failure.

The Safety Engine is available through `SafetyEngine.assess(action)` and `SandboxExecutor.execute(action)`. Dangerous commands such as `rm -rf`, `shutdown`, `reboot`, `mkfs`, `dd if=`, and `drop database` are blocked deterministically. High-risk actions require an approval callback, all filesystem paths must remain inside `PROJECT_ROOT`, and every safety check and execution attempt is written to `SAFETY_AUDIT_LOG`.

Command actions run inside Docker with only the project directory mounted, `--privileged=false`, all Linux capabilities dropped, network disabled by default, and configured CPU, memory, and timeout limits. `run_tests` defaults to `pytest`; `run_command` can run Python, npm, or pip commands through its `command` parameter. Results are returned as structured reports with captured `stdout`, `stderr`, `exit_code`, timeout status, and execution metadata.

Scheduler status is available at `GET /scheduler` and `GET /scheduler/{task_id}`. Configure `SCHEDULER_POLL_INTERVAL_SECONDS` to control the delay between quota checks; the scheduler uses a daemon watcher and does not busy-poll.

Git checkpoints are available through `GitIntegration`. Set `GIT_AUTO_COMMIT=true` to create a commit after each completed Agent Loop iteration. Checkpoint metadata includes the commit hash, changed files, task ID, iteration, model used, message, and diff, and is stored in the Brain Graph as a `GitCommit` artifact. `GIT_COMMIT_MESSAGE` controls the generated commit message.

The remaining product-level decisions are the concrete action executors for each action type, persistent Agent Loop state storage, Neo4j persistence, and API authentication. No API key or provider call is required to run the test suite.

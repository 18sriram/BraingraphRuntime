# BrainGraph Runtime Architecture

## Overview

BrainGraph Runtime is a local orchestration platform for autonomous coding workflows. The runtime uses a graph-first memory model to store tasks, decisions, experiments, and artifacts independent of any LLM provider. It exposes a FastAPI backend, a Next.js dashboard, and a Dockerized execution environment.

## Core layers

- API: service endpoints for runtime health, tasks, and graph events
- Services: orchestration and domain logic with business rules kept out of routes
- Models: persistent database models for SQLite and graph entities
- Repositories: persistence access for runtime metadata and graph operations
- Executors: safe command execution in sandboxed containers
- Scheduler: asynchronous orchestration loop for tasks and retries
- Safety Engine: command validation, access checks, and quota handling

## Storage

- SQLite: runtime metadata, execution records, and local state
- Neo4j: graph memory for agents, tasks, dependencies, decisions, and artifacts

## Execution model

1. Create a task and persist its lifecycle in the graph.
2. Evaluate task constraints and safety policies.
3. Execute steps inside a Docker sandbox.
4. Record artifacts, metrics, and failures.
5. Update the graph and resume or escalate based on policy.

## Future roadmap

- LLM provider adapters for OpenAI, Anthropic, and Gemini
- Quota-aware scheduling and automatic pause/resume behavior
- Graph visualization using React Flow
- CI and deployment automation
- Security hardening for sandboxed execution

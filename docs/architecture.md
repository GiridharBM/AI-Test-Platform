# Architecture

Status legend:

- **Implemented** — exists in the codebase today
- **Planned** — designed for, scheduled in upcoming milestones
- **Future/Research** — under consideration, not designed yet

## Current Foundation (Implemented)

```
┌─────────────────────────────┐
│ frontend/                   │  Reserved for Next.js dashboard
│ (empty, not initialized)    │
└─────────────────────────────┘
            │ HTTP
┌─────────────────────────────┐
│ backend/                    │  FastAPI + Uvicorn
│  app/main.py   GET /health  │
│  app/api/      routers      │
│  app/services/ business     │
│  app/models/   schemas      │
│  app/agents/   future home  │
│    of autonomous agents     │
│  app/code_intelligence/     │
│  app/execution/             │
│  app/evaluation/            │
└─────────────────────────────┘
```

Implemented components:

- Minimal FastAPI application (`backend/app/main.py`) exposing `GET /health`
- Package layout for future subsystems (`api`, `agents`, `code_intelligence`, `execution`, `evaluation`, `models`, `services`)
- Pytest-based smoke test for the health endpoint

## Planned (Upcoming Milestones)

- **Project upload & profiling** — ingest local source files and complete project folders
- **Repository-level code understanding** — Tree-sitter based parsing, code-aware RAG
- **Vector storage** — Qdrant for embeddings
- **LLM inference** — open-source coding LLMs served locally (NVIDIA RTX 5060) with GPU acceleration via PyTorch / Hugging Face Transformers; private NVIDIA DGX B200 for larger experiments
- **Autonomous agents** — test planning, generation, failure analysis, regeneration
- **Sandboxed execution** — Docker-based isolated test running
- **Dashboard** — Next.js + React + TypeScript + Tailwind CSS frontend with live agent activity

## Future/Research

- Mutation testing strategies
- Sandboxed bug detection and automated code repair
- Human-in-the-loop approval workflow before modifying original projects
- Risk-based and requirements-based test planning heuristics
- CPU/GPU benchmarking suite
- GitHub repository integration
- Multi-language support beyond Python (Java, JavaScript/TypeScript)

## Non-Goals (Current Milestone)

No LLM integration, RAG, embeddings, vector database, agents, test generation, Docker execution, mutation testing, GPU inference, code repair, GitHub API integration, authentication, complex frontend UI, PostgreSQL, or Redis/Celery exist yet. These are introduced incrementally after each milestone is verified.

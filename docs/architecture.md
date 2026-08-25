# Architecture

Status legend:

- **Implemented** — exists in the codebase today
- **Planned** — designed for, scheduled in upcoming milestones
- **Future/Research** — under consideration, not designed yet

## Current Foundation (Implemented — Milestone 2)

```
┌─────────────────────────────────────────────┐
│ browser / curl                               │
│  POST /api/projects/upload  (folder upload)  │
│  POST /api/projects/from-path (local dir)    │
│  POST /api/projects/{id}/profile             │
│  GET  /api/projects/{id}                     │
└────────────────────┬────────────────────────┘
                     │ HTTP
┌────────────────────┴────────────────────────┐
│ backend/                                     │  FastAPI + Uvicorn
│  app/main.py        GET /health, static UI   │
│  app/api/projects.py  project endpoints      │
│  app/core/config.py   limits & thresholds    │
│  app/models/project.py  Pydantic schemas     │
│  app/services/                                │
│    project_ingestion.py  upload + path mgmt  │
│    project_profiler.py   deterministic scan  │
│  app/agents/       future home of agents     │
│  app/code_intelligence/  future              │
│  app/execution/     future (Docker sandbox)  │
│  app/evaluation/    future                   │
│  workspace/         ingested project copies  │
└─────────────────────────────────────────────┘
```

Implemented components (Milestone 2):

- **Project ingestion** — folder upload preserving relative structure; local filesystem path registration (READ-ONLY)
- **Path safety** — traversal prevention, protected-dir rejection, filesystem root blocking, workspace self-analysis guard
- **Resource limits** — configurable max files (20k), max file size (2 MiB), max total size (200 MiB), max depth (20), all in `core/config.py`
- **Language detection** — Python, Java, JavaScript, TypeScript by file extension
- **File metrics** — source/test/doc/config/other classification; line counts; binary exclusion
- **Python AST analysis** — functions, classes, methods via `ast` module
- **Test detection** — name patterns, directory conventions; framework detection (pytest, unittest, JUnit, TestNG, Jest, Vitest, Mocha) from manifest evidence
- **Documentation detection** — markdown, RST, README files
- **Dependency manifest detection** — requirements.txt, pyproject.toml, Pipfile, pom.xml, build.gradle, package.json with basic package counts
- **API route detection** — FastAPI/Flask decorators, Express-style declarations, Spring `@Mapping` annotations
- **Complexity classification** — Small / Medium / Large based on source file count and line count thresholds
- **Profile persistence** — filesystem-based JSON storage (no database)
- **Minimal frontend** — static HTML/JS ingestion UI served at `/`

### Milestone 1 (also implemented)

- Package layout for future subsystems (`agents`, `code_intelligence`, `execution`, `evaluation`)
- Pytest-based health endpoint test
- `.gitignore` for Python, Node.js, IDE, OS, models, workspace

## Planned (Upcoming Milestones)

- **Repository-level code understanding** — Tree-sitter based parsing, code-aware RAG
- **Vector storage** — Qdrant for embeddings
- **LLM inference** — open-source coding LLMs served locally (NVIDIA RTX 5060) with GPU acceleration via PyTorch / Hugging Face Transformers; private NVIDIA DGX B200 for larger experiments
- **Autonomous agents** — test planning, generation, failure analysis, regeneration
- **Sandboxed execution** — Docker-based isolated test running
- **Dashboard** — Next.js + React + TypeScript + Tailwind CSS frontend with live agent activity
- **Java/JS/TS syntax metrics** — Tree-sitter integration for functions/classes beyond Python

## Future/Research

- Mutation testing strategies
- Sandboxed bug detection and automated code repair
- Human-in-the-loop approval workflow before modifying original projects
- Risk-based and requirements-based test planning heuristics
- CPU/GPU benchmarking suite
- GitHub repository integration
- Multi-language support beyond Python (Java, JavaScript/TypeScript)

## Not Implemented

No LLM integration, RAG, embeddings, vector database, agents, test generation, Docker execution, mutation testing, GPU inference, code repair, GitHub API integration, authentication, complex frontend UI, PostgreSQL, or Redis/Celery. These are introduced incrementally after each milestone is verified.

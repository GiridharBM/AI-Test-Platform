# Architecture

Status legend:

- **Implemented** — exists in the codebase today
- **Planned** — designed for, scheduled in upcoming milestones
- **Future/Research** — under consideration, not designed yet

## Current Foundation (Implemented — Milestone 6)

```
┌──────────────────────────────────────────────┐
│ browser / curl                                │
│  POST /api/projects/upload   (folder upload)  │
│  POST /api/projects/from-path  (local dir)    │
│  POST /api/projects/{id}/profile              │
│  POST /api/projects/{id}/discover             │
│  POST /api/projects/{id}/plan                 │
│  POST /api/projects/{id}/generate             │
│  POST /api/projects/{id}/execute              │
│  GET  /api/projects/{id}                      │
└─────────────────────┬────────────────────────┘
                      │ HTTP
┌─────────────────────┴────────────────────────┐
│ backend/                                      │  FastAPI + Uvicorn
│  app/main.py          GET /health, static UI  │
│  app/api/projects.py   project endpoints      │
│  app/core/config.py    limits & thresholds    │
│  app/models/                                    │
│    project.py          Pydantic schemas (M2)  │
│    codemap.py          Code map schemas (M3)  │
│    test_plan.py        Test plan schemas (M4) │
│    test_generation.py  Generated test schemas  │
│    execution.py        Execution result schemas│
│  app/services/                                 │
│    project_ingestion.py  upload + path mgmt   │
│    project_profiler.py   deterministic scan   │
│    code_analyzer.py      Python ast analysis  │
│    test_discovery.py     test func extraction │
│    project_discovery.py  discovery orchestrator│
│    call_graph.py        function-level calls   │
│    risk_scorer.py       target risk scoring   │
│    test_planner.py      plan generation       │
│    test_generator.py    scaffold generation   │
│  app/execution/                                 │
│    runner.py            Docker sandbox runner  │
│  app/agents/        future home of agents     │
│  app/code_intelligence/  future               │
│  app/evaluation/     future                   │
│  workspace/          ingested project copies  │
│ docker/                                        │
│    Dockerfile.testrunner  test runner image    │
└───────────────────────────────────────────────┘
```

Implemented components (Milestone 6):

- **Sandboxed test execution** — Docker-based isolated pytest execution with no network access
- **Resource limits** — configurable timeout, memory, CPU, and output size
- **Structured results** — per-file pass/fail/error status, stdout/stderr, duration, exit code
- **Automatic cleanup** — temp directories and Docker containers removed after execution
- **Docker-unavailable handling** — graceful degradation when Docker is not running
- **Execution persistence** — results stored under .meta/execution.json

- **Deterministic test scaffold generation** — template-based production of syntactically valid Python test files from the test plan
- **Framework-aware output** — generates pytest-style or unittest-style scaffolds based on detected framework
- **Edge-case test functions** — each TestSpec edge case becomes an individual test function
- **Async target scaffolding** — pytest.mark.asyncio markers for async targets
- **Class-based method scaffolds** — proper setUp and instantiation patterns for method targets
- **Safe placeholders** — NotImplementedError bodies ensure tests fail safely without executing untrusted code
- **Generated test persistence** — files written to workspace, metadata under .meta/test_generation.json

### Milestone 4 (also implemented)

- **Test plan generation** — deterministic, prioritised test specifications derived from code map and profile
- **Risk scoring** — configurable weighted scoring using test coverage, argument count, async, docstrings, public method, project complexity, mapping confidence, and fan-in
- **Function-level call graph** — lightweight AST-based caller/callee analysis for fan-in risk signals
- **Edge-case inference** — parameter-name heuristics suggesting specific edge cases per function argument
- **Test specification assembly** — priority, test type, suggested name, preconditions, related tested targets
- **Test plan persistence** — filesystem-based JSON storage under `.meta/test_plan.json`

### Milestone 3 (also implemented)

- **Code map generation** — deterministic per-file Python ast analysis producing structured source/test metadata
- **Source module analysis** — functions, classes, methods with signatures, decorators, docstrings, line ranges, imports
- **Test function discovery** — test_*/_test extraction with decorators, assertion counts, line ranges
- **Test-to-source mapping** — heuristic name similarity and import analysis with confidence scores
- **Testable target registry** — functions, methods, classes annotated with test coverage info
- **Coverage summary** — aggregate statistics: tested/untested targets, coverage percentage
- **Code map persistence** — filesystem-based JSON storage under `.meta/codemap.json`

### Milestone 2 (also implemented)

- **Project ingestion** — folder upload preserving relative structure; local filesystem path registration (READ-ONLY)
- **Path safety** — traversal prevention, protected-dir rejection, filesystem root blocking, workspace self-analysis guard
- **Resource limits** — configurable max files (20k), max file size (2 MiB), max total size (200 MiB), max depth (20), all in `core/config.py`
- **Language detection** — Python, Java, JavaScript, TypeScript by file extension
- **File metrics** — source/test/doc/config/other classification; line counts; binary exclusion
- **Python AST analysis (aggregate)** — functions, classes, methods via `ast` module
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

- **Test generation** — LLM-powered unit, integration, API, edge-case, security-oriented test creation
- **Test execution** — sandboxed test runs in Docker containers
- **Failure diagnosis** — AI-driven analysis of test failures and potential bug detection
- **Repository-level code understanding** — Tree-sitter based parsing, code-aware RAG
- **Vector storage** — Qdrant for embeddings
- **LLM inference** — open-source coding LLMs served locally (NVIDIA RTX 5060) with GPU acceleration via PyTorch / Hugging Face Transformers; private NVIDIA DGX B200 for larger experiments
- **Autonomous agents** — test generation, failure analysis, regeneration
- **Sandboxed execution** — Docker-based isolated test running
- **Dashboard** — Next.js + React + TypeScript + Tailwind CSS frontend with live agent activity
- **Java/JS/TS syntax metrics** — Tree-sitter integration for functions/classes beyond Python

## Future/Research

- Mutation testing strategies
- Sandboxed bug detection and automated code repair
- Human-in-the-loop approval workflow before modifying original projects
- CPU/GPU benchmarking suite
- GitHub repository integration
- Multi-language support beyond Python (Java, JavaScript/TypeScript)

## Not Implemented

No LLM integration, RAG, embeddings, vector database, agents, AI-powered test generation, mutation testing, GPU inference, code repair, GitHub API integration, authentication, complex frontend UI, PostgreSQL, or Redis/Celery. Test scaffolding generation is deterministic and template-based; LLM-powered test body generation is not yet introduced. Test execution is Docker-based sandboxed; native Python execution without Docker is not supported. These are introduced incrementally after each milestone is verified.

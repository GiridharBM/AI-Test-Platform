# AI Test Platform

A privacy-preserving, GPU-accelerated autonomous GenAI platform for automated software testing.

## Current Status

> **Milestone 10 — Evaluate**

The platform can ingest and profile projects, produce a structured code map, generate prioritised test plans, produce deterministic test scaffolds, and execute them in an isolated Docker sandbox. It diagnoses test failures deterministically, improves generated tests deterministically, and **verifies M8 improvements** via deterministic re-testing. It now also **evaluates the testing pipeline**: dynamic Python execution coverage, bounded mutation testing, and bounded CPU/GPU benchmarking, all run inside the M6 Docker sandbox. All stages are deterministic and private. No source code is modified. No AI inference is required. No M8/M9 loop, no source repair, no RAG, no autonomous agents.

## Long-Term Vision

The platform will autonomously test software projects through a continuous loop:

```
Analyze → Plan → Generate → Execute → Diagnose → Improve → Re-test → Evaluate
```

1. **Analyze** — repository-level code understanding via code-aware RAG
2. **Plan** — risk-based and requirements-based test planning
3. **Generate** — autonomous generation of unit, integration, API, edge-case, security-oriented, and regression tests
4. **Execute** — sandboxed test runs in Docker containers
5. **Diagnose** — AI-driven failure analysis and potential bug detection
6. **Improve** — test regeneration and sandboxed code repair (human approval required before modifying the original project)
7. **Re-test** — verify M8 improvements fixed diagnosed failures (implemented)
8. **Evaluate** — coverage analysis, mutation testing, and CPU/GPU benchmarking (implemented)

## Planned Technology Areas

These are planned, not yet implemented:

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS
- **Backend:** FastAPI, Python
- **AI/ML:** PyTorch, Hugging Face Transformers, open-source coding LLMs
- **Code intelligence:** Tree-sitter, code-aware RAG
- **Vector store:** Qdrant
- **Execution:** Docker sandboxed test execution
- **Acceleration:** NVIDIA GPU inference (local RTX 5060; NVIDIA DGX B200 for larger experiments)
- **Language coverage:** Python, Java, JavaScript/TypeScript testing

## Development Principle

This project is implemented incrementally. Each milestone is verified before the next one begins. See [docs/architecture.md](docs/architecture.md) for the current architecture state.

## Repository Layout

```
frontend/    Future Next.js dashboard (not yet initialized)
backend/     FastAPI application
docker/      Sandbox execution configs (future)
benchmarks/  CPU/GPU benchmarking (future)
experiments/ Research experiments (future)
docs/        Architecture and project documentation
```

## Backend Quick Start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000` for the project-ingestion UI, or use the API directly:

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Service health check |
| `/api/projects/upload` | POST | Upload a project folder (multipart) |
| `/api/projects/from-path` | POST | Register a local directory for profiling |
| `/api/projects/{id}/profile` | POST | Run deterministic profiling |
| `/api/projects/{id}/discover` | POST | Run test discovery and build code map |
| `/api/projects/{id}/plan` | POST | Generate prioritised test plan |
| `/api/projects/{id}/generate` | POST | Generate deterministic test scaffolds |
| `/api/projects/{id}/execute` | POST | Execute tests in Docker sandbox |
| `/api/projects/{id}/diagnose` | POST | Run deterministic failure diagnosis |
| `/api/projects/{id}/improve` | POST | Improve failing generated tests deterministically |
| `/api/projects/{id}/retest` | POST | Re-test M8 improvements and compare against baseline |
| `/api/projects/{id}/evaluate` | POST | Run coverage, mutation, and benchmark evaluation |
| `/api/projects/{id}` | GET | Retrieve metadata, profile, code map, test plan, generated tests, execution, diagnosis, improvement, retest, and evaluation results |

Run tests:

```bash
pytest          # 479 tests — ingestion, profiling, discovery, planning, generation, execution, diagnosis, improvement, retest, evaluation, API, security
```

## Milestone 7 — Hybrid Failure Diagnosis

- **Deterministic diagnosis core** — parses M6 execution output, classifies failures (assertion, exception, import_error, timeout, collection_error, syntax_error, unknown), produces a stable SHA-256 failure signature, links failures to source locations via the code map, and derives deterministic severity. Fully testable without any model.
- **Optional local/private AI boundary** — a thin `analyze(context) -> PotentialBug | None` interface under `backend/app/agents/llm.py`. **Off by default** (`DIAGNOSIS_AI_ENABLED=False`). No external/cloud calls, no API keys, no LLM/GPU/RAG infrastructure — the AI stage belongs to a future milestone.
- **Structured results** — `DiagnosisResult` (`backend/app/models/diagnosis.py`) persisted to `.meta/diagnosis.json`, with `overall_status` of `no_failures` / `failures_diagnosed` / `no_execution`.
- **Read-only & private** — diagnosis never executes or imports project code, never sends source/test/stdout/stderr/tracebacks externally, and validates untrusted traceback paths so they can never address host files.
- **No repair yet** — diagnosis only reports; automated repair/regeneration belongs to the future Improve milestone.

## Milestone 8 — Deterministic Test Improvement

- **Improve endpoint & core** — `POST /api/projects/{id}/improve` (and `backend/app/services/improvement.py`). Consumes the M7 `DiagnosisResult` plus the project's CodeMap and the M4 TestPlan.
- **Placeholder detection & regeneration** — finds `raise NotImplementedError("Scaffold generated by AI Test Platform")` scaffold bodies in generated tests and replaces them (in the matching generated-test function) with a deterministic import-and-invoke body whose argument literals come **only** from the TestPlan's explicit edge-case evidence. Sibling edge-case helpers are left untouched.
- **No fabricated behavior** — the improver never invents an input (no `add(0, 0)` from parameter names alone), never invents a behavioral assertion (`assert result == <value>`), never suppresses failures (`@skip`, `assert True`, catch-all `except`, empty bodies, deleting/weakening tests). When evidence is insufficient (no plan-pinned input, unresolvable target, class/method targets needing instantiation, non-`NotImplementedError` categories), the finding is reported `blocked`/`no_change` with an explicit reason.
- **Deterministic & private** — stable finding/file/function ordering, no randomness, no external calls, no code execution, no import of user modules, no LLM/GPU/RAG infrastructure. A local/private AI flag (`IMPROVE_AI_ENABLED=False`) is declared but the deterministic core is fully self-contained and off by default.
- **Sandboxed writes** — writes only under `workspace/{project_id}/generated_tests/` and only `*.py`, with traversal/absolute/drive/component guards. `source/`, `.meta/`, and original files are never written; writes are size-limited and atomic.
- **Structured results** — `ImprovementResult` (`backend/app/models/improvement.py`) with per-finding `ImprovementChange` (status `improved`/`blocked`/`no_change`, reason, and file before/after), persisted to `.meta/improvement.json`. Overall status is `improved`/`partial`/`blocked`/`no_change`. Improvement does **not** trigger a re-test loop (Re-test is implemented as M9; original-source code repair remains human-gated and out of scope).

## Milestone 9 — Re-test Verification

- **Retest endpoint & core** — `POST /api/projects/{id}/retest` (and `backend/app/services/retest.py`). Consumes the M8 `ImprovementResult`, M7 `DiagnosisResult`, and previous M6 `TestExecutionResult`.
- **Improved-test selection** — re-tests only tests where M8 produced `status == "improved"` changes; `no_change`/`blocked` M8 outcomes return a deterministic `no_op`.
- **M6 Docker sandbox reuse** — executes the full `generated_tests/` directory via the existing `execute_tests` runner. No second execution mechanism. M6 sandbox security model intact.
- **Baseline comparison** — correlates re-test file statuses against M6 baseline (prior execution) and M7 baseline (diagnosed function failures) to derive per-test verdicts: `fixed`, `still_failing`, `regression`, `passed`, `blocked`, `unavailable`.
- **No source repair** — never modifies original source code. Writes only `.meta/retest.json`. No improvement loop, no autonomous repair, no AI inference.
- **Deterministic & idempotent** — stable verdict ordering, no randomness, no external calls. Running twice against the same state yields identical logical results.
- **Structured results** — `ReTestResult` (`backend/app/models/retest.py`) with per-test `ReTestComparison` (baseline_status, retest_status, verdict, reason), persisted to `.meta/retest.json`. Overall status: `fixed`/`still_failing`/`regression`/`passed`/`blocked`/`unavailable`/`no_op`.

## Milestone 10 — Evaluate

- **Evaluate endpoint & orchestrator** — `POST /api/projects/{id}/evaluate` (and `backend/app/evaluation/orchestrator.py`). Runs three independent evaluation components and packs them into a single `EvaluationResult`, persisted to `.meta/evaluation.json`.
- **Coverage — dynamic Python execution coverage** — measures which source lines/branches are actually exercised by the generated tests inside the M6 Docker sandbox using the `coverage` package (installed in the sandbox image, not imported by the backend). This is a *runtime* measurement, entirely separate from the M3 static `CoverageSummary`. Reports per-file executable/covered lines, missing lines, line and branch percentages. Branch data is reported only when the tool produces it — never fabricated.
- **Mutation — bounded Python mutation testing** — generates controlled AST-based source mutations (operator, comparison, boolean-literal, augmented-assign) on isolated temporary copies and runs the tests against each mutant in the sandbox. Classifies each mutant `killed`/`survived`/`timeout`/`error`. Mutation score = killed / (killed + survived), with the denominator documented. Strictly bounded by `EVALUATION_MAX_MUTANTS`, a per-mutant timeout, and an overall wall-clock budget. No mutated source is ever left behind and the original source tree is never modified.
- **Benchmark — bounded CPU/GPU benchmarking** — measures the established current-platform workload (sandboxed test execution) over bounded warm-up + measured runs, reporting min/mean/median latency. GPU availability is probed honestly; when no GPU environment exists the GPU component is `unavailable` and no GPU numbers are fabricated. Benchmark values are inherently variable measurements, never used as logical IDs.
- **M9 → M10 behavior** — evaluation proceeds normally whether M9 is `fixed`, `still_failing`, `regression`, or `passed`; `no_op`/`blocked` add explicit warnings; `unavailable` preserves unavailable execution-dependent components. A missing optional component never silently becomes success.
- **Security & boundaries** — all executable project/test code runs in the M6 Docker sandbox (`--network none`, `--read-only`, tmpfs, memory/CPU limits, timeout, output cap, `--rm`, cleanup). No host execution, no source modification, no M8/M9 trigger, no mutation artifacts left behind. No LLM/RAG/vector/agent dependencies; no GPU model-inference libraries.
- **Deterministic & idempotent** — static metrics (coverage calculations, mutation classification/score, result ordering) are deterministic. Reevaluating does not modify source, tests, or .meta beyond `.meta/evaluation.json`, and does not trigger M8/M9. Only inherently variable benchmark measurements may differ between runs.
- **Structured results** — `EvaluationResult` (`backend/app/models/evaluation.py`) with component results (`CoverageResult`, `MutationResult`, `BenchmarkResult`), each with its own status (`completed`/`unavailable`/`blocked`/`error`/`not_run`), summary, warnings, and reasons.

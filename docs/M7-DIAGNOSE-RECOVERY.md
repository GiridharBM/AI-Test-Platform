# Milestone 7 (Diagnose) — Recovery Report

Status: **Recovery evidence only. No implementation performed. No files under `backend/` modified. Nothing committed or pushed.**

## 1. Intent recovered from repository evidence

Milestone 7 targets the sixth stage of the platform pipeline:

> Analyze → Plan → Generate → Execute → **Diagnose** → Improve → Re-test → Evaluate

README.md:16

The single authoritative one-line definition in the repo:

> **Diagnose** — AI-driven failure analysis and potential bug detection

README.md:23

Corroborated by architecture.md:118:

> **Failure diagnosis** — AI-driven analysis of test failures and potential bug detection

## 2. Evidence sources (ranked by trust)

| # | Source | What it confirms |
|---|--------|------------------|
| 1 | `README.md:16,23-25` | Pipeline position (after Execute, before Improve/Re-test); "AI-driven failure analysis and potential bug detection" |
| 2 | `docs/architecture.md:118` | "Failure diagnosis" planned capability |
| 3 | `docs/architecture.md:46-48,110` | `app/agents/` = "future home of agents" — the package reserved for this milestone |
| 4 | `docs/architecture.md:121-122,130` | LLM inference + autonomous agents + "sandboxed bug detection and automated code repair" (later-stage capabilities) |
| 5 | `docs/architecture.md:138` | **Not Implemented**: "…agents, AI-powered test generation, mutation testing, GPU inference, code repair…" — confirms M7 not yet built |
| 6 | M1–M6 commits (`a49db45`…`30511f9`) | Deterministic-first pattern; each milestone is deterministic with no LLM/AI |
| 7 | Empty placeholders `agents/`, `evaluation/`, `code_intelligence/` | Reserved package shells, no code |

## 3. What M7 is (confirmed)

M7 = **Diagnose**: consume a completed `TestExecutionResult` (M6) and produce a structured **failure diagnosis / potential bug report** — the first milestone that intentionally introduces AI/LLM-driven analysis. It is the bridge between the deterministic Execute stage and the AI/agent Improve stage.

## 4. What exists today that M7 must consume (the M6 → M7 data contract)

M6 produces `TestExecutionResult` (`backend/app/models/execution.py:41-53`):

- `schema_version: int = 1`
- `project_id: str`
- `overall_status: str` — `passed | failed | error | timeout | unavailable`
- `exit_code: int`
- `stdout` / `stderr` — raw pytest `-v` output (captured, capped at `EXECUTION_MAX_OUTPUT_BYTES`)
- `duration_seconds: float`
- `summary: ExecutionSummary` — `{total_files, total_test_functions, passed, failed, errors, skipped}`
- `file_results: list[TestFileResult]` — `{file_path, status, stdout, stderr, duration_seconds}`
- `warnings: list[str]`

Per-file result contract: `TestFileResult` (`execution.py:20-28`) with worst-status-per-file rollup.

Runner behavior M7 must rely on: `_parse_pytest_output` / `_parse_file_results` (`runner.py:71-116`) classify lines ending ` PASSED | FAILED | ERROR | SKIPPED`; `--tb=short` is used (`runner.py:192`), so tracebacks are present in `stderr`/`stdout` for diagnosis.

## 5. What M7 can correlate against (existing context)

Beyond the execution result, M7 has full project context persisted under `.meta/`:

- `profile.json` → `ProjectProfile` (`project.py:88`)
- `codemap.json` → `CodeMap` (`codemap.py:99`) — source modules, functions, classes with `file_path` + `line_start`/`line_end`, imports
- `test_plan.json` → `TestPlan` (`test_plan.py:48`) — specs, priorities, risk scores
- `test_generation.json` → `TestGenerationResult` — generated file content/metadata
- `execution.json` → `TestExecutionResult`
- On-disk source: `workspace/{project_id}/source/` and generated tests: `workspace/{project_id}/generated_tests/`

This is sufficient for failure-fragment → source-location linking (line numbers, function names, file paths).

## 6. Existing transport/persistence patterns M7 must mirror

- Persistence helpers in `backend/app/services/project_ingestion.py:170-183` (`save_execution`/`read_execution` under `.meta/execution.json`). M7 would add `save_diagnosis`/`read_diagnosis` under `.meta/diagnosis.json`.
- API endpoint wiring in `backend/app/api/projects.py:133-151` (`POST /{project_id}/execute`) and `GET /{project_id}` (`projects.py:176-206`), which returns `ProjectDetails` (`project.py:120-127`) with the per-stage optional field: `profile`, `codemap`, `test_plan`, `test_generation`, `execution`. M7 adds `diagnosis`.
- Config constants in `backend/app/core/config.py`.
- Pydantic models with `schema_version: int = 1` everywhere.

## 7. Intended shape of the M7 subsystem (inferred)

`backend/app/agents/` is the reserved home (`architecture.md:47`, `backend/README.md:32`). A natural fit:

- `backend/app/models/diagnosis.py` — `DiagnosisResult` (schema_version, project_id, created_at, per-failure findings, linked source locations, confidence, potential-bug flags, warnings)
- `backend/app/agents/diagnose.py` — orchestrator: reads execution + codemap + test files, produces diagnosis
- `backend/app/api/projects.py` — `POST /{project_id}/diagnose` + add `diagnosis` to `ProjectDetails`
- `backend/app/services/project_ingestion.py` — `save_diagnosis`/`read_diagnosis`
- Tests under `backend/tests/test_diagnosis*.py`

## 8. Key design tension / open decision

The pipeline is explicitly deterministic-first (M2–M6 all "no LLM, no AI"). README and architecture both label Diagnose as **AI-driven**. This is the first divergence point:

- **Option A (deterministic, consistent with M1–M6):** rule/heuristic failure analysis on the structured execution output + codemap line data (traceback → function → file matching), producing a deterministic diagnosis report. No LLM dependency — matches every prior milestone and the repo's clear deterministic-first principle.
- **Option B (AI/LLM, per README/architecture wording):** open-source coding LLM (PyTorch / HF Transformers, local GPU per architecture.md:121) analyzing stdout/stderr + source. Matches the literal "AI-driven" wording but breaks the deterministic pattern and introduces the first real AI infrastructure.

**Recommendation:** Implement **Option A first** (deterministic failure analysis and potential-bug detection) to preserve the platform's core invariant, with the diagnosis schema designed to carry AI-supplemented findings later. Respects "The shortest Lazy path that works" and keeps GPU/LLM work gated behind a later milestone. If the human author intended the literal AI-first Milestone 7, confirm before building — this is the single biggest ambiguity.

## 9. Security invariants M7 must preserve

- **Never execute uploaded project code on the host** — diagnosis is read-only analysis of persisted artifacts; no subprocess runs of user code.
- **Never import user modules** — all symbol resolution uses `codemap.json` (ast-based) data, not runtime import.
- **Prevent path traversal** — persisted `.meta/` JSON keys are project-internal; sanitize before any file reads.
- **Treat ingested projects as untrusted** — LLM prompts (if any) must not leak other projects; no secrets in diagnosis output.
- Generated/source content is already bounded by scan limits (`config.py`).

## 10. What to verify before implementation (acceptance anchors)

1. A stored `execution.json` with `overall_status == "failed"` yields at least one diagnosis finding.
2. A stored `execution.json` with `overall_status == "passed"` (or `timeout`/`unavailable`) yields expected no-failure / boundary handling.
3. Failure fragment (traceback function/file/line) maps to real `codemap` entries where confidence allows.
4. `GET /{project_id}` returns the new `diagnosis` field once `POST /{project_id}/diagnose` has run.
5. All M1–M6 existing tests remain green (221 as of M6).

## 11. Explicitly out of scope for M7 (per architecture.md:138)

RAG, embeddings, vector database, mutation testing, GPU inference, automated code repair (that's M8 "Improve"), GitHub API integration, auth, complex frontend, PostgreSQL/Redis/Celery. Automated code repair belongs to the **Improve** milestone.

## 12. Remaining gaps requiring human decision

1. **Deterministic (Option A) vs AI-LLM (Option B)** for the diagnosis engine — the single blocking decision.
2. Whether `diagnosis.json` may embed AI-supplemented fields in a future schema bump (`schema_version=2`) or should remain deterministic-only.
3. Whether a "potential bug detection" signal (different from "failure locus") is part of M7 scope now or deferred to Improve/M8.

## 13. Recommended immediate next step

Confirm Option A vs Option B (section 8). On confirmation, the lowest-risk path is:

1. Add `backend/app/models/diagnosis.py` + `save_diagnosis`/`read_diagnosis` in `project_ingestion.py`.
2. Add `POST /{project_id}/diagnose` and `diagnosis` on `ProjectDetails` + `GET`.
3. Implement deterministic analysis in `backend/app/agents/diagnose.py`.
4. Add `backend/tests/test_diagnosis*.py`; run full suite (221 + new).
5. Commit as M7 following the frozen milestone pattern.

## 14. Files touched by this recovery (none in backend)

- `docs/M7-DIAGNOSE-RECOVERY.md` (this report) — the only artifact created. Not committed, not pushed.

## 15. Frozen-milestone compliance

M1–M6 commits (`a49db45`, `faec19b`, `43956d0`, `77a756c`, `2f60697`, `30511f9`) remain untouched. Working tree, other than this new docs file, is clean.

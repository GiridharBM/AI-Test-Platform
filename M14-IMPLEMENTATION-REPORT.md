# M14 Implementation — Final Verification Report

Checkpoint: `21aa1354987f1c7e771ef588b0d448385a5b4ed0`
Scope: exactly three verified findings — F-GAP1 (MED), ACT-1 (MED), ACT-2 (LOW-MED).
Required: no commit/push, no scope expansion. Verified below. Repository tree is clean (`git status --short` lists only the 16 intended files; no stray artifacts; `dist/` is git-ignored).

## Implementation summary

- **F-GAP1** — added one canonical, origin-aware resolver `source_root(workspace, project_id)` in `backend/app/services/project_ingestion.py:122`. `pipeline._source_root` now delegates to it. Applied it at the three previously-broken call sites: `backend/app/services/retest.py:495`, `backend/app/evaluation/orchestrator.py:131`, and standalone execute in `backend/app/api/projects.py:163-165`. `runner.py` (`have_source`, read-only copy mount) is untouched.
- **ACT-1** — surfaced the existing backend resume (`resume_pipeline`, `pipeline.py:746`, `POST /pipeline/resume`) in the UI: `resume` added to `PipelineActionName` (`types.ts:37`), `ACTION_CALLERS` (`pipeline.ts:15`), label `Resume pipeline` (`labels.ts:112`); `ErrorPanel` gained a `projectId` prop and a resume button rendered only for `overall_status ∈ {failed, unavailable}`, driven by the existing `usePipelineAction` mutation. Wired in `ProjectWorkspacePage.tsx:95`.
- **ACT-2** — `_derive_verdict` (`backend/app/services/results.py:322`) now splits the applied-repair-without-passed-final-validation branch: `FINAL_VALIDATION_FAILED → failed`, `FINAL_VALIDATION_UNAVAILABLE → unavailable`, `FINAL_VALIDATION_NOT_RUN`/missing → `unavailable`.

## Verification (13 items)

### F-GAP1 — origin-aware source root resolution
1. **Single canonical resolver.** `source_root()` is the authoritative resolver for both origins; the pipeline's origin-aware logic now delegates to it (no forked copies introduced/remaining in the workload path).
2. **Upload-origin unchanged.** Resolver returns `workspace/{project_id}/source` — byte-for-byte the prior `source_dir()` result; upload projects behave identically (covered by the full pre-existing suite).
3. **Path-origin re-test uses the registered source.** `/retest` now passes the registered on-disk path to the runner instead of the missing `workspace/{pid}/source`. Regression test: `test_retest_api.py::test_retest_path_origin_uses_registered_source`.
4. **Path-origin evaluation uses the registered source.** `orchestrator.py` now calls `source_root()` instead of `source_dir()` unconditionally.
5. **Path-origin standalone `/execute` mounts the registered source.** Previously `execute_tests(generated_dir, project_id)` defaulted to `workspace/{pid}/source`, making `have_source=False` (runner.py:444) and silently skipping the mount. Now passes `source_root=ingestion.source_root(...)`. Regression test: `test_execution_api.py::test_execute_path_origin_mounts_registered_source`.
6. **Docker read-only mounting preserved.** `runner.py` is untouched: the source is copied into the sandbox temp dir and mounted `:ro`; the host path is never mounted and cannot be mutated by the container.
7. **Trust boundary intact.** The resolver reads the path from `.meta/meta.json` (forward-referenced once at registration); no per-request client-controlled path is honored. Unit test: `test_from_path.py::test_source_root_path_origin_uses_registered_location`.

### ACT-1 — surface pipeline resume in the UI
8. **Backend action reused, no new endpoint.** The frontend now drives the pre-existing `resumePipeline`/`resume_pipeline`; `resume` was added to the `PipelineActionName` union, `ACTION_CALLERS`, and `ACTION_LABELS`. No new mutation system introduced — the existing `usePipelineAction` (setQueryData + invalidate, 409 handling) is reused.
9. **Resume exposed only for `failed` / `unavailable`.** Backend `resume_pipeline` is a documented no-op for `waiting_for_user`, `waiting_for_approval`, `completed`, `rejected`; the button is gated to failed/unavailable, matching that contract. Render tests cover presence (failed, unavailable) and absence (blocked, rejected, completed, running).
10. **Resume absent at gates and after stops.** Backend `available_actions` is set only from `GATE_RETEST_ACTIONS`/`GATE_REPAIR_ACTIONS`/`GATE_APPROVAL_ACTIONS` (pipeline.py:696-700) and cleared to `[]` on stop (`_stop`, pipeline.py:555-559); `resume` is never emitted, so the gate renderer (`PipelineActions`) cannot show it.
11. **Interaction + error handling covered by tests.** Click posts resume, caches the returned running state with `current_stage: 'generate'`; network failure surfaces "Could not reach the server"; button disables while in flight. `frontend/src/test/components/ErrorPanel.test.tsx` (17 tests).

### ACT-2 — ResultsDigest / pipeline terminal alignment
12. **Digest agrees with pipeline on final-validation outcome.** Pipeline routing (pipeline.py:664-678): passed→complete, failed→failed, unavailable→unavailable. Digest now: `FINAL_VALIDATION_PASSED → passed`, `FINAL_VALIDATION_FAILED → failed`, `FINAL_VALIDATION_UNAVAILABLE → unavailable`. Live mismatch on `unavailable` is closed. Digest tests: `test_results_api.py::test_repair_applied_final_validation_{failed,unavailable,not_recorded_is_unavailable}`.
13. **Missing evidence can never produce false success.** `FINAL_VALIDATION_NOT_RUN` / absent final-validation object maps to `unavailable` (deterministic), never `passed`. Existing pass-path (`passed`) and gate paths (`repair_pending`, `rejected`) unchanged.

## Full qualification

| Gate | Command | Result |
|---|---|---|
| Backend test suite | `python -m pytest -q` | 688 passed, 5 skipped |
| Frontend test suite | `npx vitest run` | 25 files / 265 tests passed |
| Typecheck | `npm run typecheck` (tsc -b) | clean |
| Production build | `npm run build` | built (102 modules) |
| Git diff | `git diff --stat` | 16 files, +260/−53, all intended |

## Out of scope (unchanged by design)
- Pipeline state machine, gate action sets, and terminal routing semantics (no rename/redesign of `available_actions`).
- CI, auth, realtime, export changes, backward-compat removal, M11 repair internals, autonomous behavior, ResultsDigest redesign.

No commits or pushes were made. Changed files, in full:
`backend/app/{api/projects.py, evaluation/orchestrator.py, services/pipeline.py, services/project_ingestion.py, services/results.py, services/retest.py}`,
`backend/tests/{test_execution_api.py, test_from_path.py, test_results_api.py, test_retest_api.py}`,
`frontend/src/api/{labels.ts, pipeline.ts, types.ts}`,
`frontend/src/components/ErrorPanel.tsx`,
`frontend/src/pages/ProjectWorkspacePage.tsx`,
`frontend/src/test/components/ErrorPanel.test.tsx`.
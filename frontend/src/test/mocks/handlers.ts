import { http, HttpResponse } from 'msw'

import type {
  PipelineOverallStatus,
  PipelineState,
  ProjectDetails,
  ProjectMeta,
  RepairResult,
  ReTestResult,
  EvaluationResult,
  TestExecutionResult,
  DiagnosisResult,
  ProjectProfile,
  CodeMap,
  TestPlan,
  TestGenerationResult,
  ImprovementResult,
  StageRecord,
  StageStatus,
} from '../../api/types'

const PIPELINE_STAGE_ORDER = [
  'profile',
  'discover',
  'plan',
  'generate',
  'execute',
  'diagnose',
  'improve',
  'retest',
]

function stageHistoryStep(
  index: number,
  options: Partial<StageRecord> = {},
): StageRecord {
  const start = `2026-01-01T${String(9 + Math.floor(index / 4)).padStart(2, '0')}:${String((index % 4) * 15).padStart(2, '0')}:00Z`
  const startMs = Date.parse(start)
  return {
    stage: PIPELINE_STAGE_ORDER[index],
    status: 'success',
    start_time: start,
    end_time: new Date(startMs + 60_000).toISOString(),
    result_id: `${PIPELINE_STAGE_ORDER[index]}-demo`,
    reason: '',
    warnings: [],
    ...options,
  }
}

function fullHistory(status: StageStatus): StageRecord[] {
  return PIPELINE_STAGE_ORDER.map((_, index) =>
    stageHistoryStep(index, { status }),
  )
}

function pipelineFixture(
  status: PipelineOverallStatus,
  overrides: Partial<PipelineState> = {},
): PipelineState {
  const base: PipelineState = {
    schema_version: 1,
    project_id: 'demo_project',
    pipeline_id: 'demo_project',
    current_stage: 'completed',
    overall_status: status,
    completed_stages: PIPELINE_STAGE_ORDER,
    stage_history: fullHistory('success'),
    current_improvement_round: 0,
    maximum_improvement_rounds: 3,
    user_decision_required: false,
    available_actions: [],
    error: '',
    reason: '',
    warnings: [],
    created_at: '2026-01-01T09:00:00Z',
    updated_at: '2026-01-01T09:13:00Z',
  }

  const statusOverrides: Record<PipelineOverallStatus, Partial<PipelineState>> = {
    running: {
      current_stage: 'profiling',
      completed_stages: [],
      stage_history: [stageHistoryStep(0, { status: 'in_progress' })],
      current_improvement_round: 0,
    },
    waiting_for_user: {
      current_stage: 'awaiting_retest_decision',
      current_improvement_round: 3,
      user_decision_required: true,
      available_actions: ['retest', 'skip_retest'],
      reason: 'Improvements did not resolve the diagnosed failures.',
      stage_history: [
        ...fullHistory('success'),
        stageHistoryStep(7, { reason: 'Improvements did not resolve the diagnosed failures.' }),
      ],
    },
    waiting_for_approval: {
      current_stage: 'awaiting_repair_approval',
      current_improvement_round: 3,
      user_decision_required: true,
      available_actions: ['approve', 'reject'],
      stage_history: [
        ...fullHistory('success'),
        { ...stageHistoryStep(7), stage: 'repair', result_id: 'repair-demo' },
      ],
    },
    completed: {
      current_stage: 'completed',
      reason: 'Pipeline completed successfully.',
    },
    failed: {
      current_stage: 'executing',
      completed_stages: ['profile', 'discover', 'plan', 'generate'],
      stage_history: [
        ...PIPELINE_STAGE_ORDER.slice(0, 4).map((_, index) =>
          stageHistoryStep(index),
        ),
        stageHistoryStep(4, {
          status: 'failed',
          reason: '3 of 2 tests failed with assertion errors.',
        }),
      ],
      reason: 'Test execution failed: 3 of 2 tests failed.',
      error: '',
    },
    blocked: {
      current_stage: 'executing',
      completed_stages: ['profile', 'discover', 'plan', 'generate'],
      stage_history: [
        ...PIPELINE_STAGE_ORDER.slice(0, 4).map((_, index) =>
          stageHistoryStep(index),
        ),
        stageHistoryStep(4, {
          status: 'blocked',
          reason: 'Test execution requires an unavailable runtime.',
          warnings: ['Docker runtime unavailable.'],
        }),
      ],
      reason: 'Test execution blocked by an unavailable runtime.',
      warnings: ['Docker runtime unavailable.'],
    },
    unavailable: {
      current_stage: 'discovering',
      completed_stages: ['profile'],
      stage_history: [
        stageHistoryStep(0),
        stageHistoryStep(1, {
          status: 'unavailable',
          reason: 'Model provider API is unreachable.',
          warnings: ['The discovery model provider timed out.'],
        }),
      ],
      reason: 'Model provider API is unreachable.',
      warnings: ['The discovery model provider timed out.'],
    },
    rejected: {
      current_stage: 'completed',
      current_improvement_round: 3,
      user_decision_required: false,
      available_actions: [],
      stage_history: [
        ...fullHistory('success'),
        { ...stageHistoryStep(7), stage: 'repair', result_id: 'repair-demo' },
        {
          ...stageHistoryStep(7),
          stage: 'approve',
          status: 'rejected',
          result_id: '',
          reason: 'User rejected the repair candidate.',
        },
      ],
      reason: 'User rejected the repair candidate.',
    },
  }

  return { ...base, ...statusOverrides[status], ...overrides }
}

export { pipelineFixture }

const PIPELINE_BY_ID: Record<string, Partial<PipelineState>> = {
  p_running: pipelineFixture('running'),
  p_waiting_user: pipelineFixture('waiting_for_user'),
  p_waiting_approval: pipelineFixture('waiting_for_approval'),
  p_completed: pipelineFixture('completed'),
  p_failed: pipelineFixture('failed'),
  p_blocked: pipelineFixture('blocked'),
  p_unavailable: pipelineFixture('unavailable'),
  p_rejected: pipelineFixture('rejected'),
}

export {
  projectDetailsFixture,
  stageHistoryStep,
  codemapFixture,
  testPlanFixture,
  testGenerationFixture,
  improvementFixture,
  appliedRepairFixture,
}

function codemapFixture(overrides: Partial<CodeMap> = {}): CodeMap {
  return {
    schema_version: 1,
    project_id: 'demo_project',
    created_at: '2026-01-01T09:01:00Z',
    source_modules: [
      {
        path: 'calculator.py',
        language: 'python',
        functions: [
          {
            name: 'add',
            qualified_name: 'add',
            file_path: 'calculator.py',
            line_start: 1,
            line_end: 3,
            args: ['a', 'b'],
            decorators: [],
            has_docstring: false,
            is_async: false,
          },
        ],
        classes: [],
        imports: [],
      },
    ],
    test_functions: [
      {
        name: 'test_add',
        file_path: 'generated_tests/test_calculator.py',
        line_start: 1,
        line_end: 4,
        decorators: [],
        has_docstring: false,
        assertion_count: 1,
      },
    ],
    test_mappings: [
      {
        test_function: 'test_add',
        test_file: 'generated_tests/test_calculator.py',
        source_target: 'add',
        source_file: 'calculator.py',
        confidence: 0.95,
        method: 'semantic',
      },
    ],
    testable_targets: [
      {
        qualified_name: 'add',
        file_path: 'calculator.py',
        target_type: 'function',
        has_tests: true,
        test_count: 1,
        test_files: ['generated_tests/test_calculator.py'],
        mapped_tests: ['test_add'],
      },
    ],
    coverage_summary: {
      total_targets: 4,
      targets_with_tests: 1,
      targets_without_tests: 3,
      coverage_percentage: 25,
      untested_functions: ['subtract', 'multiply', 'divide'],
      untested_endpoints: [],
    },
    warnings: [],
    ...overrides,
  }
}

function testPlanFixture(overrides: Partial<TestPlan> = {}): TestPlan {
  return {
    schema_version: 1,
    project_id: 'demo_project',
    created_at: '2026-01-01T09:02:00Z',
    specs: [
      {
        target_qualified_name: 'add',
        target_file: 'calculator.py',
        target_type: 'function',
        priority: 1,
        test_type: 'unit',
        suggested_test_name: 'test_add_basic',
        preconditions: [],
        edge_cases: [],
        related_tested_targets: [],
        risk_score: 0.9,
      },
    ],
    summary: {
      total_specs: 4,
      critical_count: 1,
      high_count: 1,
      medium_count: 1,
      low_count: 1,
      by_type: { unit: 4 },
      untested_modules: [],
    },
    warnings: [],
    ...overrides,
  }
}

function testGenerationFixture(
  overrides: Partial<TestGenerationResult> = {},
): TestGenerationResult {
  return {
    schema_version: 1,
    project_id: 'demo_project',
    created_at: '2026-01-01T09:03:00Z',
    files: [
      {
        file_path: 'generated_tests/test_calculator.py',
        content: 'def test_add():\n    assert add(1, 2) == 3\n',
        target_count: 4,
        priority_range: '1-4',
        framework: 'pytest',
      },
    ],
    summary: {
      total_files: 1,
      total_test_functions: 4,
      total_edge_cases: 2,
      by_priority: { '1': 1, '2': 1, '3': 1, '4': 1 },
      by_type: { unit: 4 },
      framework_used: 'pytest',
    },
    warnings: [],
    merged_user_files: [],
    ...overrides,
  }
}

function improvementFixture(
  overrides: Partial<ImprovementResult> = {},
): ImprovementResult {
  return {
    schema_version: 1,
    project_id: 'demo_project',
    diagnosis_id: 'diag-demo',
    created_at: '2026-01-01T09:04:00Z',
    status: 'improved',
    changes: [
      {
        finding_id: 'f1',
        test_file: 'generated_tests/test_calculator.py',
        test_function: 'test_add',
        status: 'improved',
        reason: 'Fixed assertion',
        before: 'assert add(1, 2) == 5',
        after: 'assert add(1, 2) == 3',
      },
    ],
    files_modified: 1,
    warnings: [],
    ...overrides,
  }
}

function appliedRepairFixture(
  overrides: Partial<RepairResult> = {},
): RepairResult {
  return {
    schema_version: 1,
    project_id: 'demo_project',
    status: 'applied',
    retest_diagnosis_id: 'diag-demo',
    attempts: [],
    selected_candidate: null,
    approval_state: 'approved',
    application_state: 'applied',
    final_validation: { status: 'passed', execution_result: null, reason: '' },
    baseline_statuses: {},
    target_test_functions: [],
    warnings: [],
    reasons: [],
    created_at: '2026-01-01T09:05:00Z',
    ...overrides,
  }
}

function projectDetailsFixture(
  overrides: Partial<ProjectDetails> = {},
): ProjectDetails {
  const profile: ProjectProfile = {
    schema_version: 1,
    project_id: 'demo_project',
    name: 'calculator',
    origin: 'upload',
    created_at: '2026-01-01T09:00:00Z',
    languages: [{ name: 'Python', files: 4, source_lines: 120, percentage: 100 }],
    metrics: {
      total_files: 6,
      source_files: 3,
      test_files: 1,
      documentation_files: 1,
      configuration_files: 1,
      other_files: 0,
      total_lines: 180,
      source_lines: 120,
      functions: 4,
      classes: 1,
      methods: 2,
    },
    tests: { files: 1, frameworks: ['pytest'], example_files: [] },
    documentation: { files: 1, paths: ['README.md'] },
    dependencies: { manifests: ['requirements.txt'], packages_detected: 0, details: {} },
    api: { endpoints_detected: 0, endpoints: [] },
    complexity: { level: 'Small', reasons: ['4 functions across 3 source files'] },
    warnings: [],
    files: null,
  }

  const execution: TestExecutionResult = {
    schema_version: 1,
    project_id: 'demo_project',
    overall_status: 'failed',
    exit_code: 1,
    stdout: '',
    stderr: '',
    duration_seconds: 1.2,
    summary: {
      total_files: 1,
      total_test_functions: 2,
      passed: 0,
      failed: 1,
      errors: 1,
      skipped: 0,
    },
    file_results: [
      {
        file_path: 'generated_tests/test_calculator.py',
        status: 'failed',
        stdout: '',
        stderr: 'AssertionError',
        duration_seconds: 1.2,
      },
    ],
    warnings: [],
  }

  const diagnosis: DiagnosisResult = {
    schema_version: 1,
    project_id: 'demo_project',
    created_at: '2026-01-01T09:02:00Z',
    overall_status: 'failures_diagnosed',
    summary: {
      total_findings: 1,
      by_category: { assertion: 1 },
      by_severity: { high: 1 },
      linked_locations: 1,
      potential_bugs: 0,
    },
    findings: [
      {
        finding_id: 'f1',
        test_file: 'generated_tests/test_calculator.py',
        test_function: 'test_add',
        status: 'failed',
        failure_signature: 'hash-abc',
        exception_type: 'AssertionError',
        message: 'expected 4 got 5',
        traceback: '',
        linked_locations: [
          {
            source_file: 'calculator.py',
            line_start: 3,
            line_end: 3,
            qualified_name: 'add',
            confidence: 0.9,
          },
        ],
        category: 'assertion',
        severity: 'high',
      },
    ],
    potential_bugs: [],
    warnings: [],
  }

  const retest: ReTestResult = {
    schema_version: 1,
    project_id: 'demo_project',
    status: 'still_failing',
    diagnosis_id: 'diag-demo',
    improvement_id: 'improve-demo',
    selected_tests: [
      { test_file: 'generated_tests/test_calculator.py', test_function: 'test_add', improvement_status: 'improved' },
    ],
    execution_status: 'failed',
    comparisons: [
      {
        test_file: 'generated_tests/test_calculator.py',
        test_function: 'test_add',
        baseline_status: 'failed',
        retest_status: 'failed',
        verdict: 'still_failing',
        reason: 'same assertion failure',
      },
    ],
    summary: {
      selected: 1,
      executed: 1,
      fixed: 0,
      still_failing: 1,
      regression: 0,
      passed: 0,
      blocked: 0,
      unavailable: 0,
    },
    warnings: [],
    reasons: [],
    created_at: '2026-01-01T09:13:00Z',
  }

  const evaluation: EvaluationResult = {
    schema_version: 1,
    project_id: 'demo_project',
    status: 'completed',
    retest_id: 'retest-demo',
    coverage: {
      status: 'completed',
      method: 'dynamic-python-line',
      line_total: 120,
      line_covered: 80,
      line_percentage: 66.7,
      branch_total: 10,
      branch_covered: 5,
      branch_percentage: 50,
      files: [],
      warnings: [],
      reasons: [],
    },
    mutation: {
      status: 'completed',
      total_mutants: 4,
      killed: 3,
      survived: 1,
      timeout: 0,
      error: 0,
      valid_mutants: 4,
      mutation_score: 0.75,
      score_denominator: 'killed + survived (valid executable mutants)',
      mutants: [],
      warnings: [],
      reasons: [],
    },
    benchmark: {
      status: 'completed',
      component: 'test-execution',
      run_count: 3,
      warm_up_count: 1,
      measured_runs: [1.1, 1.2, 1.15],
      min_seconds: 1.1,
      mean_seconds: 1.15,
      median_seconds: 1.15,
      cpu_available: true,
      gpu_available: false,
      gpu_status: 'unavailable',
      warnings: [],
      reasons: [],
    },
    summary: 'Coverage 66.7%, mutation score 0.75',
    warnings: [],
    reasons: [],
    created_at: '2026-01-01T09:15:00Z',
  }

  const repair: RepairResult = {
    schema_version: 1,
    project_id: 'demo_project',
    status: 'validated_pending_approval',
    retest_diagnosis_id: 'diag-demo',
    attempts: [
      {
        attempt_number: 1,
        candidate_id: 'c1',
        file_path: 'calculator.py',
        source_location: 'L3-3',
        operation: 'replace binop body',
        before: '    return a - b',
        after: '    return a + b',
        rationale: 'test_add expects the sum',
        validation_status: 'passed',
        execution_result: null,
        failure_reason: '',
        created_at: '2026-01-01T09:16:00Z',
      },
    ],
    selected_candidate: {
      candidate_id: 'c1',
      file_path: 'calculator.py',
      source_location: 'L3-3',
      operation: 'replace binop body',
      before: '    return a - b',
      after: '    return a + b',
      rationale: 'test_add expects the sum',
      confidence: 0.97,
      attempt_number: 1,
      target_function: 'add',
    },
    approval_state: 'pending',
    application_state: 'not_applied',
    final_validation: { status: 'not_run', execution_result: null, reason: '' },
    baseline_statuses: { test_add: 'failed' },
    target_test_functions: ['test_add'],
    warnings: [],
    reasons: ['A validated candidate awaits explicit approval.'],
    created_at: '2026-01-01T09:17:00Z',
  }

  return {
    project_id: 'demo_project',
    name: 'calculator',
    origin: 'upload',
    source_path: null,
    file_count: 6,
    created_at: '2026-01-01T09:00:00Z',
    profiled: true,
    profile,
    codemap: null,
    test_plan: null,
    test_generation: null,
    execution,
    diagnosis,
    improvement: null,
    retest,
    evaluation,
    repair,
    ...overrides,
  }
}

const NOT_FOUND_DETAIL = { detail: 'Project metadata not found' }
const NO_PIPELINE_DETAIL = { detail: 'No pipeline state for this project.' }
const CONFLICT_DETAIL = {
  detail: 'Invalid pipeline gate: action retest not permitted at awaiting_repair_approval',
}

const ACTION_STATES: Record<string, Partial<PipelineState>> = {
  start: {
    current_stage: 'profile',
    overall_status: 'running',
    user_decision_required: false,
    available_actions: [],
  },
  resume: {
    current_stage: 'generate',
    overall_status: 'running',
    user_decision_required: false,
    available_actions: [],
  },
  retest: {
    current_stage: 'awaiting_repair_decision',
    overall_status: 'waiting_for_user',
    user_decision_required: true,
    available_actions: ['repair', 'skip_repair'],
  },
  'skip-retest': {
    current_stage: 'awaiting_repair_decision',
    overall_status: 'waiting_for_user',
    user_decision_required: true,
    available_actions: ['repair', 'skip_repair'],
  },
  repair: {
    current_stage: 'awaiting_repair_approval',
    overall_status: 'waiting_for_approval',
    user_decision_required: true,
    available_actions: ['approve', 'reject'],
  },
  'skip-repair': {
    current_stage: 'completed',
    overall_status: 'completed',
    user_decision_required: false,
    available_actions: [],
  },
  approve: {
    current_stage: 'completed',
    overall_status: 'completed',
    user_decision_required: false,
    available_actions: [],
  },
  reject: {
    current_stage: 'completed',
    overall_status: 'rejected',
    user_decision_required: false,
    available_actions: [],
  },
}

function projectMetaFixture(overrides: Partial<ProjectMeta> = {}): ProjectMeta {
  return {
    project_id: 'uploaded_abc123',
    name: 'uploaded-project',
    origin: 'upload',
    source_path: null,
    file_count: 1,
    created_at: '2026-01-01T10:00:00Z',
    profiled: false,
    ...overrides,
  }
}

export const handlers = [
  http.post('/api/projects/upload', async ({ request }) => {
    const formData = await request.formData()
    const files = formData.getAll('files')
    const names = files.map((f) => (f as File).name)
    if (names.includes('server-error.txt')) {
      return HttpResponse.json(
        { detail: 'Internal server error during upload.' },
        { status: 500 },
      )
    }
    if (names.includes('bad-path.txt')) {
      return HttpResponse.json(
        { detail: 'Path traversal rejected: ../evil.txt' },
        { status: 400 },
      )
    }
    return HttpResponse.json(
      projectMetaFixture({ file_count: files.length }),
    )
  }),

  http.get('/api/projects/:projectId', ({ params }) => {
    const projectId = String(params.projectId)
    if (projectId === 'missing') {
      return HttpResponse.json(NOT_FOUND_DETAIL, { status: 404 })
    }
    if (projectId === 'malformed') {
      return HttpResponse.text('this is not json', { status: 200 })
    }
    return HttpResponse.json(
      projectDetailsFixture({ project_id: projectId, name: projectId }),
    )
  }),

  http.get('/api/projects/:projectId/pipeline', ({ params }) => {
    const projectId = String(params.projectId)
    if (projectId === 'no_pipeline' || projectId === 'missing') {
      return HttpResponse.json(NO_PIPELINE_DETAIL, { status: 404 })
    }
    if (projectId === 'conflict') {
      return HttpResponse.json(CONFLICT_DETAIL, { status: 409 })
    }
    const byId = PIPELINE_BY_ID[projectId]
    if (byId !== undefined) {
      return HttpResponse.json(
        pipelineFixture(byId.overall_status!, {
          project_id: projectId,
          pipeline_id: projectId,
          ...byId,
        }),
      )
    }
    return HttpResponse.json(
      pipelineFixture('waiting_for_user', {
        project_id: projectId,
        pipeline_id: projectId,
      }),
    )
  }),

  http.post('/api/projects/:projectId/pipeline/:action', ({ params }) => {
    const projectId = String(params.projectId)
    const action = String(params.action)
    if (projectId === 'malformed') {
      return HttpResponse.text('this is not json', { status: 200 })
    }
    if (projectId === 'conflict') {
      return HttpResponse.json(CONFLICT_DETAIL, { status: 409 })
    }
    const target = ACTION_STATES[action] ?? {}
    const status =
      (target.overall_status as PipelineOverallStatus | undefined) ??
      'waiting_for_user'
    return HttpResponse.json(
      pipelineFixture(status, {
        project_id: projectId,
        pipeline_id: projectId,
        ...target,
      }),
    )
  }),
]
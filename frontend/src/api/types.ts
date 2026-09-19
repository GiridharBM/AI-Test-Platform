export type OriginMode = 'upload' | 'path'

export const PIPELINE_GATES = {
  RETEST: 'awaiting_retest_decision',
  REPAIR: 'awaiting_repair_decision',
  APPROVAL: 'awaiting_repair_approval',
} as const

export type PipelineOverallStatus =
  | 'running'
  | 'waiting_for_user'
  | 'waiting_for_approval'
  | 'completed'
  | 'failed'
  | 'blocked'
  | 'unavailable'
  | 'rejected'

export type StageStatus =
  | 'success'
  | 'failed'
  | 'blocked'
  | 'unavailable'
  | 'skipped'
  | 'approved'
  | 'rejected'
  | 'exhausted'
  | 'in_progress'

export type PipelineActionName =
  | 'retest'
  | 'skip_retest'
  | 'repair'
  | 'skip_repair'
  | 'approve'
  | 'reject'

export interface StageRecord {
  stage: string
  status: StageStatus
  start_time: string
  end_time: string
  result_id: string
  reason: string
  warnings: string[]
}

export interface PipelineState {
  schema_version: number
  project_id: string
  pipeline_id: string
  current_stage: string
  overall_status: PipelineOverallStatus
  completed_stages: string[]
  stage_history: StageRecord[]
  current_improvement_round: number
  maximum_improvement_rounds: number
  user_decision_required: boolean
  available_actions: PipelineActionName[]
  error: string
  reason: string
  warnings: string[]
  created_at: string
  updated_at: string
}

export interface DetectedEndpoint {
  method: string
  path: string
  source_file: string
  line: number
}

export interface ApiInfo {
  endpoints_detected: number
  endpoints: DetectedEndpoint[]
}

export interface ExistingTestInfo {
  files: number
  frameworks: string[]
  example_files: string[]
}

export interface DocumentationInfo {
  files: number
  paths: string[]
}

export interface DependencyInfo {
  manifests: string[]
  packages_detected: number | null
  details: Record<string, string>
}

export type ComplexityLevel = 'Small' | 'Medium' | 'Large'

export interface ComplexityInfo {
  level: ComplexityLevel
  reasons: string[]
}

export type FileCategory =
  | 'source'
  | 'test'
  | 'documentation'
  | 'configuration'
  | 'other'

export interface ProjectFile {
  path: string
  language: string | null
  category: FileCategory
  size_bytes: number
  lines: number
}

export interface LanguageStatistics {
  name: string
  files: number
  source_lines: number
  percentage: number
}

export interface ProjectMetrics {
  total_files: number
  source_files: number
  test_files: number
  documentation_files: number
  configuration_files: number
  other_files: number
  total_lines: number
  source_lines: number
  functions: number | null
  classes: number | null
  methods: number | null
}

export interface ProjectProfile {
  schema_version: number
  project_id: string
  name: string
  origin: OriginMode
  created_at: string
  languages: LanguageStatistics[]
  metrics: ProjectMetrics
  tests: ExistingTestInfo
  documentation: DocumentationInfo
  dependencies: DependencyInfo
  api: ApiInfo
  complexity: ComplexityInfo
  warnings: string[]
  files: ProjectFile[] | null
}

export interface SourceFunction {
  name: string
  qualified_name: string
  file_path: string
  line_start: number
  line_end: number
  args: string[]
  decorators: string[]
  has_docstring: boolean
  is_async: boolean
}

export interface SourceClass {
  name: string
  qualified_name: string
  file_path: string
  line_start: number
  line_end: number
  bases: string[]
  decorators: string[]
  has_docstring: boolean
  methods: SourceFunction[]
}

export interface SourceModule {
  path: string
  language: string
  functions: SourceFunction[]
  classes: SourceClass[]
  imports: string[]
}

export interface TestFunction {
  name: string
  file_path: string
  line_start: number
  line_end: number
  decorators: string[]
  has_docstring: boolean
  assertion_count: number
}

export interface TestMapping {
  test_function: string
  test_file: string
  source_target: string
  source_file: string
  confidence: number
  method: string
}

export interface TestableTarget {
  qualified_name: string
  file_path: string
  target_type: string
  has_tests: boolean
  test_count: number
  test_files: string[]
  mapped_tests: string[]
}

export interface CodeMapCoverageSummary {
  total_targets: number
  targets_with_tests: number
  targets_without_tests: number
  coverage_percentage: number
  untested_functions: string[]
  untested_endpoints: string[]
}

export interface CodeMap {
  schema_version: number
  project_id: string
  created_at: string
  source_modules: SourceModule[]
  test_functions: TestFunction[]
  test_mappings: TestMapping[]
  testable_targets: TestableTarget[]
  coverage_summary: CodeMapCoverageSummary
  warnings: string[]
}

export interface EdgeCase {
  parameter: string
  case_type: string
  description: string
}

export interface TestSpec {
  target_qualified_name: string
  target_file: string
  target_type: string
  priority: number
  test_type: string
  suggested_test_name: string
  preconditions: string[]
  edge_cases: EdgeCase[]
  related_tested_targets: string[]
  risk_score: number
}

export interface TestPlanSummary {
  total_specs: number
  critical_count: number
  high_count: number
  medium_count: number
  low_count: number
  by_type: Record<string, number>
  untested_modules: string[]
}

export interface TestPlan {
  schema_version: number
  project_id: string
  created_at: string
  specs: TestSpec[]
  summary: TestPlanSummary
  warnings: string[]
}

export interface GeneratedTestFile {
  file_path: string
  content: string
  target_count: number
  priority_range: string
  framework: string
}

export interface GenerationSummary {
  total_files: number
  total_test_functions: number
  total_edge_cases: number
  by_priority: Record<string, number>
  by_type: Record<string, number>
  framework_used: string
}

export interface TestGenerationResult {
  schema_version: number
  project_id: string
  created_at: string
  files: GeneratedTestFile[]
  summary: GenerationSummary
  warnings: string[]
  merged_user_files: string[]
}

export type ExecutionStatus =
  | 'passed'
  | 'failed'
  | 'error'
  | 'timeout'
  | 'unavailable'

export interface TestFunctionResult {
  test_function: string
  status: string
  duration_seconds: number | null
}

export interface TestFileResult {
  file_path: string
  status: string
  stdout: string
  stderr: string
  duration_seconds: number
  test_functions?: TestFunctionResult[]
}

export interface ExecutionSummary {
  total_files: number
  total_test_functions: number
  passed: number
  failed: number
  errors: number
  skipped: number
}

export interface TestExecutionResult {
  schema_version: number
  project_id: string
  overall_status: ExecutionStatus
  exit_code: number
  stdout: string
  stderr: string
  duration_seconds: number
  summary: ExecutionSummary
  file_results: TestFileResult[]
  warnings: string[]
}

export type DiagnosisOverallStatus =
  | 'no_failures'
  | 'failures_diagnosed'
  | 'no_execution'

export type DiagnosisCategory =
  | 'assertion'
  | 'exception'
  | 'import_error'
  | 'timeout'
  | 'collection_error'
  | 'syntax_error'
  | 'unknown'

export type Severity = 'high' | 'medium' | 'low'

export interface SourceLocation {
  source_file: string
  line_start: number
  line_end: number
  qualified_name: string
  confidence: number
}

export interface DiagnosisFinding {
  finding_id: string
  test_file: string
  test_function: string
  status: string
  failure_signature: string
  exception_type: string
  message: string
  traceback: string
  linked_locations: SourceLocation[]
  category: DiagnosisCategory
  severity: Severity
}

export interface PotentialBug {
  description: string
  source_file: string
  line_span: number[]
  confidence: number
  rationale: string
  model: string
}

export interface DiagnosisSummary {
  total_findings: number
  by_category: Record<string, number>
  by_severity: Record<string, number>
  linked_locations: number
  potential_bugs: number
}

export interface DiagnosisResult {
  schema_version: number
  project_id: string
  created_at: string
  overall_status: DiagnosisOverallStatus
  summary: DiagnosisSummary
  findings: DiagnosisFinding[]
  potential_bugs: PotentialBug[]
  warnings: string[]
}

export type ImprovementStatus = 'improved' | 'partial' | 'no_change' | 'blocked'

export interface ImprovementChange {
  finding_id: string
  test_file: string
  test_function: string
  status: ImprovementStatus
  reason: string
  before: string
  after: string
}

export interface ImprovementResult {
  schema_version: number
  project_id: string
  diagnosis_id: string
  created_at: string
  status: ImprovementStatus
  changes: ImprovementChange[]
  files_modified: number
  warnings: string[]
}

export type ReTestStatus =
  | 'fixed'
  | 'still_failing'
  | 'regression'
  | 'passed'
  | 'blocked'
  | 'unavailable'
  | 'no_op'

export type ReTestVerdict =
  | 'fixed'
  | 'still_failing'
  | 'regression'
  | 'passed'
  | 'blocked'
  | 'unavailable'

export interface ReTestSelection {
  test_file: string
  test_function: string
  improvement_status: string
}

export interface ReTestComparison {
  test_file: string
  test_function: string
  baseline_status: string
  retest_status: string
  verdict: ReTestVerdict
  reason: string
}

export interface ReTestSummary {
  selected: number
  executed: number
  fixed: number
  still_failing: number
  regression: number
  passed: number
  blocked: number
  unavailable: number
}

export interface ReTestResult {
  schema_version: number
  project_id: string
  status: ReTestStatus
  diagnosis_id: string
  improvement_id: string
  selected_tests: ReTestSelection[]
  execution_status: string
  comparisons: ReTestComparison[]
  summary: ReTestSummary
  warnings: string[]
  reasons: string[]
  created_at: string
}

export type EvaluationStatus =
  | 'completed'
  | 'unavailable'
  | 'blocked'
  | 'error'
  | 'not_run'

export interface CoverageFile {
  file_path: string
  executable_lines: number
  covered_lines: number
  missing_lines: number[]
  percentage: number
  branch_total: number
  branch_covered: number
}

export interface CoverageResult {
  status: EvaluationStatus
  method: string
  line_total: number
  line_covered: number
  line_percentage: number
  branch_total: number
  branch_covered: number
  branch_percentage: number | null
  files: CoverageFile[]
  warnings: string[]
  reasons: string[]
}

export type MutantStatus = 'killed' | 'survived' | 'timeout' | 'error'

export interface Mutant {
  id: string
  file_path: string
  line: number
  operator: string
  description: string
  status: MutantStatus
  reason: string
}

export interface MutationResult {
  status: EvaluationStatus
  total_mutants: number
  killed: number
  survived: number
  timeout: number
  error: number
  valid_mutants: number
  mutation_score: number | null
  score_denominator: string
  mutants: Mutant[]
  warnings: string[]
  reasons: string[]
}

export interface BenchmarkResult {
  status: EvaluationStatus
  component: string
  run_count: number
  warm_up_count: number
  measured_runs: number[]
  min_seconds: number | null
  mean_seconds: number | null
  median_seconds: number | null
  cpu_available: boolean
  gpu_available: boolean
  gpu_status: EvaluationStatus
  warnings: string[]
  reasons: string[]
}

export interface EvaluationResult {
  schema_version: number
  project_id: string
  status: EvaluationStatus
  retest_id: string
  coverage: CoverageResult
  mutation: MutationResult
  benchmark: BenchmarkResult
  summary: string
  warnings: string[]
  reasons: string[]
  created_at: string
}

export type RepairStatus =
  | 'candidate_generated'
  | 'validating'
  | 'validated_pending_approval'
  | 'approved'
  | 'applied'
  | 'rejected'
  | 'blocked'
  | 'unavailable'
  | 'failed'

export type RepairValidationStatus = 'passed' | 'failed' | 'unavailable'

export interface RepairCandidate {
  candidate_id: string
  file_path: string
  source_location: string
  operation: string
  before: string
  after: string
  rationale: string
  confidence: number
  attempt_number: number
  target_function: string
}

export interface RepairAttempt {
  attempt_number: number
  candidate_id: string
  file_path: string
  source_location: string
  operation: string
  before: string
  after: string
  rationale: string
  validation_status: RepairValidationStatus
  execution_result: Record<string, unknown> | null
  failure_reason: string
  created_at: string
}

export interface FinalValidation {
  status: 'passed' | 'failed' | 'unavailable' | 'not_run'
  execution_result: Record<string, unknown> | null
  reason: string
}

export interface RepairResult {
  schema_version: number
  project_id: string
  status: RepairStatus
  retest_diagnosis_id: string
  attempts: RepairAttempt[]
  selected_candidate: RepairCandidate | null
  approval_state: 'pending' | 'approved' | 'rejected'
  application_state: 'not_applied' | 'applied'
  final_validation: FinalValidation
  baseline_statuses: Record<string, string>
  target_test_functions: string[]
  warnings: string[]
  reasons: string[]
  created_at: string
}

export interface ProjectMeta {
  project_id: string
  name: string
  origin: OriginMode
  source_path: string | null
  file_count: number | null
  created_at: string
  profiled: boolean
}

export interface ProjectDetails extends ProjectMeta {
  profile: ProjectProfile | null
  codemap: CodeMap | null
  test_plan: TestPlan | null
  test_generation: TestGenerationResult | null
  execution: TestExecutionResult | null
  diagnosis: DiagnosisResult | null
  improvement: ImprovementResult | null
  retest: ReTestResult | null
  evaluation: EvaluationResult | null
  repair: RepairResult | null
}

export type DigestVerdict =
  | 'passed'
  | 'failed'
  | 'no_execution'
  | 'blocked'
  | 'unavailable'
  | 'repair_pending'
  | 'rejected'

export interface DigestTestCounts {
  total_files: number
  total_test_functions: number
  passed: number
  failed: number
  errors: number
  skipped: number
}

export interface DigestFailingTest {
  test_file: string
  test_function: string
  status: string
  category: string
  severity: string
  exception_type: string
  message: string
  source_file: string
  source_line_start: number | null
  source_line_end: number | null
  source_qualified_name: string
}

export interface DigestRepairState {
  status: string
  approval_state: string
  application_state: string
  final_validation_status: string
  final_validation_reason: string
  selected_operation: string
  selected_file_path: string
  selected_source_location: string
  selected_rationale: string
  confirmed_repair: boolean
  reasons: string[]
}

export interface DigestEvaluationState {
  status: string
  coverage_status: string
  line_coverage_percentage: number | null
  mutation_status: string
  mutation_score: number | null
  benchmark_status: string
  benchmark_median_seconds: number | null
}

export interface ResultsDigest {
  schema_version: number
  project_id: string
  created_at: string
  overall_verdict: DigestVerdict
  reason: string
  pipeline_status: string | null
  pipeline_current_stage: string | null
  execution_status: string | null
  execution_duration_seconds: number | null
  test_counts: DigestTestCounts | null
  diagnosis_status: string | null
  failing_tests: DigestFailingTest[]
  improvement_status: string | null
  improvement_changes: number | null
  improvement_files_modified: number | null
  retest_status: string | null
  repair: DigestRepairState | null
  evaluation: DigestEvaluationState | null
  warnings: string[]
}
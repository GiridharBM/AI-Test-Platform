import type {
  PipelineActionName,
  PipelineOverallStatus,
  StageStatus,
} from './types'

export const AUTO_PIPELINE_STAGES = [
  'profile',
  'discover',
  'plan',
  'generate',
  'execute',
  'diagnose',
  'improve',
  'retest',
] as const

export const STAGE_LABELS: Record<string, string> = {
  upload: 'Upload',
  profile: 'Profile',
  discover: 'Discover',
  plan: 'Plan',
  generate: 'Generate',
  execute: 'Execute',
  diagnose: 'Diagnose',
  improve: 'Improve',
  retest: 'Re-test',
  repair: 'Repair',
  approve: 'Approval',
  evaluate: 'Evaluation',
}

const STAGE_VERB_TO_KEY: Record<string, string> = {
  profiling: 'profile',
  discovering: 'discover',
  planning: 'plan',
  generating: 'generate',
  executing: 'execute',
  diagnosing: 'diagnose',
  improving: 'improve',
  retesting: 'retest',
  repairing: 'repair',
}

const GATE_LABELS: Record<string, string> = {
  awaiting_retest_decision: 'Awaiting retest decision',
  awaiting_repair_decision: 'Awaiting repair decision',
  awaiting_repair_approval: 'Awaiting repair approval',
}

export function stageKeyFromCurrentStage(currentStage: string): string | undefined {
  return STAGE_VERB_TO_KEY[currentStage]
}

export function currentStageLabel(currentStage: string): string {
  const key = STAGE_VERB_TO_KEY[currentStage]
  if (key !== undefined) {
    return STAGE_LABELS[key] ?? currentStage
  }
  if (currentStage === 'completed') {
    return 'Completed'
  }
  return GATE_LABELS[currentStage] ?? STAGE_LABELS[currentStage] ?? currentStage
}

export const OVERALL_STATUS_LABELS: Record<PipelineOverallStatus, string> = {
  running: 'Running',
  waiting_for_user: 'Waiting for user',
  waiting_for_approval: 'Waiting for approval',
  completed: 'Completed',
  failed: 'Failed',
  blocked: 'Blocked',
  unavailable: 'Unavailable',
  rejected: 'Rejected',
}

export function overallStatusLabel(status: string): string {
  return OVERALL_STATUS_LABELS[status as PipelineOverallStatus] ?? status
}

export const STAGE_STATUS_LABELS: Record<StageStatus, string> = {
  success: 'Success',
  failed: 'Failed',
  blocked: 'Blocked',
  unavailable: 'Unavailable',
  skipped: 'Skipped',
  approved: 'Approved',
  rejected: 'Rejected',
  exhausted: 'Exhausted',
  in_progress: 'In progress',
}

export function stageStatusLabel(status: string): string {
  return STAGE_STATUS_LABELS[status as StageStatus] ?? status
}

export function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return iso
  }
  return date.toLocaleString()
}

export const ACTION_LABELS: Record<PipelineActionName, string> = {
  retest: 'Run re-test',
  skip_retest: 'Skip re-test',
  repair: 'Run repair',
  skip_repair: 'Skip repair',
  approve: 'Approve and apply repair',
  reject: 'Reject repair',
  resume: 'Resume pipeline',
}

export function actionLabel(action: string): string {
  return ACTION_LABELS[action as PipelineActionName] ?? action
}

export const TERMINAL_ERROR_STATUSES: readonly PipelineOverallStatus[] = [
  'failed',
  'blocked',
  'unavailable',
  'rejected',
]

export function isTerminalErrorStatus(
  status: string,
): status is PipelineOverallStatus {
  return (TERMINAL_ERROR_STATUSES as readonly string[]).includes(status)
}
import { type KeyboardEvent, useEffect, useRef, useState } from 'react'

import { apiErrorMessage } from '../api/client'
import { ACTION_LABELS, actionLabel } from '../api/labels'
import type { PipelineActionName, PipelineState } from '../api/types'
import { usePipelineAction } from '../hooks/usePipeline'

interface PipelineActionsProps {
  projectId: string
  state: PipelineState
}

const PRIMARY_ACTIONS = new Set(['retest', 'repair', 'approve'])

type ConfirmingAction = Extract<PipelineActionName, 'approve' | 'reject'>

const CONFIRMATION_COPY: Record<
  ConfirmingAction,
  { title: string; body: string; confirmLabel: string }
> = {
  approve: {
    title: 'Approve and apply repair?',
    body: 'This will approve the validated repair candidate and apply the change to the project source code. The repair has not been applied yet.',
    confirmLabel: 'Approve and apply repair',
  },
  reject: {
    title: 'Reject repair?',
    body: 'This will reject the repair candidate. The source code is not changed and the pipeline ends as rejected.',
    confirmLabel: 'Reject repair',
  },
}

export function PipelineActions({ projectId, state }: PipelineActionsProps) {
  const mutation = usePipelineAction(projectId)
  const [confirmingAction, setConfirmingAction] =
    useState<ConfirmingAction | null>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const confirmRef = useRef<HTMLButtonElement>(null)
  const triggerRef = useRef<HTMLElement | null>(null)
  const actions = (state.user_decision_required ? state.available_actions : []).filter(
    (action): action is PipelineActionName => action in ACTION_LABELS,
  )

  useEffect(() => {
    if (confirmingAction !== null) {
      triggerRef.current = document.activeElement as HTMLElement | null
      cancelRef.current?.focus()
    }
  }, [confirmingAction])

  function closeDialog() {
    setConfirmingAction(null)
    requestAnimationFrame(() => triggerRef.current?.focus())
  }

  function trapFocus(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      closeDialog()
      return
    }
    if (event.key !== 'Tab') {
      return
    }
    const focusable = [cancelRef.current, confirmRef.current].filter(
      (el): el is HTMLButtonElement => el !== null,
    )
    if (focusable.length === 0) {
      return
    }
    const active = document.activeElement
    const currentIndex = focusable.indexOf(active as HTMLButtonElement)
    if (currentIndex === -1) {
      return
    }
    event.preventDefault()
    const nextIndex = event.shiftKey
      ? (currentIndex - 1 + focusable.length) % focusable.length
      : (currentIndex + 1) % focusable.length
    focusable[nextIndex].focus()
  }

  if (actions.length === 0) {
    return null
  }

  function requestAction(action: PipelineActionName) {
    if (action === 'approve' || action === 'reject') {
      setConfirmingAction(action)
      return
    }
    mutation.mutate(action)
  }

  const confirmation =
    confirmingAction !== null ? CONFIRMATION_COPY[confirmingAction] : null

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex flex-wrap gap-2">
        {actions.map((action) => (
          <button
            key={action}
            type="button"
            onClick={() => requestAction(action)}
            disabled={mutation.isPending || confirmingAction !== null}
            aria-label={actionLabel(action)}
            className={
              PRIMARY_ACTIONS.has(action)
                ? 'rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-slate-950 hover:bg-amber-500 disabled:opacity-50'
                : 'rounded-md border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50'
            }
          >
            {actionLabel(action)}
          </button>
        ))}
        {mutation.isPending && (
          <span role="status" className="self-center text-xs text-slate-300">
            Working…
          </span>
        )}
      </div>

      {mutation.isError && mutation.error !== null && (
        <p role="alert" className="mt-3 text-sm text-red-300">
          Action failed: {apiErrorMessage(mutation.error)}
        </p>
      )}

      {confirmation !== null && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirmation-dialog-title"
          onKeyDown={trapFocus}
          className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/70 p-4"
        >
          <div className="w-full max-w-md rounded-lg border border-slate-700 bg-slate-900 p-5">
            <h3
              id="confirmation-dialog-title"
              className="text-base font-semibold text-white"
            >
              {confirmation.title}
            </h3>
            <p className="mt-2 text-sm text-slate-300">{confirmation.body}</p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                ref={cancelRef}
                type="button"
                onClick={() => setConfirmingAction(null)}
                disabled={mutation.isPending}
                className="rounded-md border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                ref={confirmRef}
                type="button"
                onClick={() => {
                  if (confirmingAction !== null) {
                    mutation.mutate(confirmingAction)
                  }
                  closeDialog()
                }}
                disabled={mutation.isPending}
                className="rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-slate-950 hover:bg-amber-500 disabled:opacity-50"
              >
                {confirmation.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
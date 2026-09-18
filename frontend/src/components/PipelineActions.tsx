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

export function PipelineActions({ projectId, state }: PipelineActionsProps) {
  const mutation = usePipelineAction(projectId)
  const [confirmingApprove, setConfirmingApprove] = useState(false)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const approveRef = useRef<HTMLButtonElement>(null)
  const triggerRef = useRef<HTMLElement | null>(null)
  const actions = (state.user_decision_required ? state.available_actions : []).filter(
    (action): action is PipelineActionName => action in ACTION_LABELS,
  )

  useEffect(() => {
    if (confirmingApprove) {
      triggerRef.current = document.activeElement as HTMLElement | null
      cancelRef.current?.focus()
    }
  }, [confirmingApprove])

  function closeApproveDialog() {
    setConfirmingApprove(false)
    requestAnimationFrame(() => triggerRef.current?.focus())
  }

  function trapFocus(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      closeApproveDialog()
      return
    }
    if (event.key !== 'Tab') {
      return
    }
    const focusable = [cancelRef.current, approveRef.current].filter(
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
    if (action === 'approve') {
      setConfirmingApprove(true)
      return
    }
    mutation.mutate(action)
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex flex-wrap gap-2">
        {actions.map((action) => (
          <button
            key={action}
            type="button"
            onClick={() => requestAction(action)}
            disabled={mutation.isPending || confirmingApprove}
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

      {confirmingApprove && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="approve-dialog-title"
          onKeyDown={trapFocus}
          className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/70 p-4"
        >
          <div className="w-full max-w-md rounded-lg border border-slate-700 bg-slate-900 p-5">
            <h3 id="approve-dialog-title" className="text-base font-semibold text-white">
              Approve and apply repair?
            </h3>
            <p className="mt-2 text-sm text-slate-300">
              This will approve the validated repair candidate and apply the
              change to the project source code. The repair has not been
              applied yet.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                ref={cancelRef}
                type="button"
                onClick={() => setConfirmingApprove(false)}
                disabled={mutation.isPending}
                className="rounded-md border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                ref={approveRef}
                type="button"
                onClick={() => {
                  mutation.mutate('approve')
                  closeApproveDialog()
                }}
                disabled={mutation.isPending}
                className="rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-slate-950 hover:bg-amber-500 disabled:opacity-50"
              >
                Approve and apply repair
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
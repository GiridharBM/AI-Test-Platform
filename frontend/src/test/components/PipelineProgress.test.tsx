import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PipelineProgress } from '../../components/PipelineProgress'

describe('PipelineProgress', () => {
  it('shows the eight auto-chain stages in canonical order', () => {
    render(
      <PipelineProgress currentStage="profiling" completedStages={[]} />,
    )
    const steps = screen.getAllByLabelText(/(done|in progress|pending)/)
    expect(
      steps.map((step) => step.textContent),
    ).toEqual(
      expect.arrayContaining([
        expect.stringMatching(/Profile/),
        expect.stringMatching(/Discover/),
        expect.stringMatching(/Plan/),
        expect.stringMatching(/Generate/),
        expect.stringMatching(/Execute/),
        expect.stringMatching(/Diagnose/),
        expect.stringMatching(/Improve/),
        expect.stringMatching(/Re-test/),
      ]),
    )
  })

  it('marks the current stage as in progress', () => {
    render(
      <PipelineProgress currentStage="generating" completedStages={['profile', 'discover', 'plan']} />,
    )
    expect(
      screen.getByLabelText('Generate: in progress'),
    ).toBeDefined()
    expect(screen.getByLabelText('Profile: done')).toBeDefined()
    expect(screen.getByLabelText('Execute: pending')).toBeDefined()
  })

  it('uses completed_stages for history, never inferring future completion', () => {
    render(
      <PipelineProgress currentStage="diagnosing" completedStages={['profile', 'discover', 'plan', 'generate', 'execute']} />,
    )
    expect(screen.getByLabelText('Diagnose: in progress')).toBeDefined()
    expect(screen.getByLabelText('Improve: pending')).toBeDefined()
    expect(screen.getByLabelText('Re-test: pending')).toBeDefined()
    expect(screen.queryByLabelText('Re-test: done')).toBeNull()
  })

  it('shows evaluation as a standalone, non-chained stage', () => {
    render(
      <PipelineProgress currentStage="profiling" completedStages={[]} />,
    )
    expect(screen.getByText(/M10 · Evaluation/)).toBeDefined()
    expect(screen.getByText(/Standalone/)).toBeDefined()
  })
})
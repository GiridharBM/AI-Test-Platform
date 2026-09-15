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

  it('renders the outcome pill when overallStatus is provided', () => {
    render(
      <PipelineProgress
        currentStage="profiling"
        completedStages={[]}
        overallStatus="running"
      />,
    )
    expect(screen.getByText('Outcome: Running')).toBeDefined()
  })

  it('renders the outcome pill for completed status', () => {
    render(
      <PipelineProgress
        currentStage="completed"
        completedStages={['profile', 'discover', 'plan', 'generate', 'execute', 'diagnose', 'improve', 'retest']}
        overallStatus="completed"
      />,
    )
    expect(screen.getByText('Outcome: Completed')).toBeDefined()
  })

  it('does not render a standalone Completed text node', () => {
    render(
      <PipelineProgress
        currentStage="completed"
        completedStages={['profile', 'discover', 'plan', 'generate', 'execute', 'diagnose', 'improve', 'retest']}
        overallStatus="completed"
      />,
    )
    expect(screen.queryByText('Completed')).toBeNull()
  })

  it('does not add in-progress labels when outcome pill is shown', () => {
    render(
      <PipelineProgress
        currentStage="completed"
        completedStages={['profile', 'discover', 'plan', 'generate', 'execute', 'diagnose', 'improve', 'retest']}
        overallStatus="completed"
      />,
    )
    expect(screen.queryByLabelText(/in progress/)).toBeNull()
  })

  it('renders the decision gate chip when userDecisionRequired is true', () => {
    render(
      <PipelineProgress
        currentStage="awaiting_retest_decision"
        completedStages={[]}
        overallStatus="waiting_for_user"
        userDecisionRequired
      />,
    )
    expect(screen.getByText('Waiting for a decision')).toBeDefined()
    expect(screen.getByLabelText('Pipeline decision gate')).toBeDefined()
  })

  it('does not render the decision gate chip when userDecisionRequired is false', () => {
    render(
      <PipelineProgress
        currentStage="profiling"
        completedStages={[]}
        overallStatus="running"
        userDecisionRequired={false}
      />,
    )
    expect(screen.queryByText('Waiting for a decision')).toBeNull()
  })

  it('does not render outcome or gate when no optional props are passed', () => {
    render(
      <PipelineProgress currentStage="profiling" completedStages={[]} />,
    )
    expect(screen.queryByText(/^Outcome:/)).toBeNull()
    expect(screen.queryByText('Waiting for a decision')).toBeNull()
  })
})
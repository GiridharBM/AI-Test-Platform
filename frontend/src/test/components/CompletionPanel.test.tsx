import { cleanup, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { CompletionPanel } from '../../components/CompletionPanel'
import { projectDetailsFixture } from '../mocks/handlers'

beforeEach(() => {
  cleanup()
})

describe('CompletionPanel', () => {
  it('renders the Pipeline completed heading', () => {
    render(
      <CompletionPanel project={projectDetailsFixture()} />,
    )
    expect(screen.getByText('Pipeline completed')).toBeDefined()
  })

  it('does not render a bare Completed text node', () => {
    render(
      <CompletionPanel project={projectDetailsFixture()} />,
    )
    expect(screen.queryByText('Completed')).toBeNull()
  })

  it('does not render the word Success', () => {
    render(
      <CompletionPanel project={projectDetailsFixture()} />,
    )
    expect(screen.queryByText('Success')).toBeNull()
  })

  it('does not claim all tests passed', () => {
    render(
      <CompletionPanel project={projectDetailsFixture()} />,
    )
    expect(screen.queryByText(/all tests passed/i)).toBeNull()
  })

  it('shows pending approval when repair is validated but not yet approved', () => {
    render(
      <CompletionPanel
        project={projectDetailsFixture({
          repair: {
            ...projectDetailsFixture().repair!,
            approval_state: 'pending',
            application_state: 'not_applied',
            final_validation: { status: 'passed', execution_result: null, reason: '' },
          },
        })}
      />,
    )
    expect(
      screen.getByText(/awaiting approval/),
    ).toBeDefined()
  })

  it('shows repair validated when final validation passed', () => {
    render(
      <CompletionPanel
        project={projectDetailsFixture({
          repair: {
            ...projectDetailsFixture().repair!,
            final_validation: { status: 'passed', execution_result: null, reason: '' },
          },
        })}
      />,
    )
    expect(screen.getByText('Repair validated')).toBeDefined()
  })

  it('shows repair approved when approval_state is approved', () => {
    render(
      <CompletionPanel
        project={projectDetailsFixture({
          repair: {
            ...projectDetailsFixture().repair!,
            approval_state: 'approved',
          },
        })}
      />,
    )
    expect(screen.getByText('Repair approved')).toBeDefined()
  })

  it('shows applied repair wording for upload origin', () => {
    render(
      <CompletionPanel
        project={projectDetailsFixture({
          origin: 'upload',
          repair: {
            ...projectDetailsFixture().repair!,
            approval_state: 'approved',
            application_state: 'applied',
            final_validation: { status: 'passed', execution_result: null, reason: '' },
          },
        })}
      />,
    )
    expect(
      screen.getByText('Repair applied to the platform workspace copy.'),
    ).toBeDefined()
  })

  it('shows applied repair wording for path origin', () => {
    render(
      <CompletionPanel
        project={projectDetailsFixture({
          origin: 'path',
          repair: {
            ...projectDetailsFixture().repair!,
            approval_state: 'approved',
            application_state: 'applied',
            final_validation: { status: 'passed', execution_result: null, reason: '' },
          },
        })}
      />,
    )
    expect(
      screen.getByText('Repair applied to the project source.'),
    ).toBeDefined()
  })

  it('shows rejected repair wording', () => {
    render(
      <CompletionPanel
        project={projectDetailsFixture({
          repair: {
            ...projectDetailsFixture().repair!,
            approval_state: 'rejected',
          },
        })}
      />,
    )
    expect(
      screen.getByText('Repair was rejected and not applied.'),
    ).toBeDefined()
  })

  it('renders nothing when repair is null', () => {
    render(
      <CompletionPanel project={projectDetailsFixture({ repair: null })} />,
    )
    expect(screen.getByText('Pipeline completed')).toBeDefined()
    expect(screen.queryByText(/repair/i)).toBeNull()
  })
})

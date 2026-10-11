// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { $newChatRunAction } from '@/store/new-chat-run'
import { $currentCwd, $gatewayState } from '@/store/session'

import type { SpecDetail, SpecSummary } from './spec-model'

const requestGateway = vi.fn()

vi.mock('../gateway/hooks/use-gateway-request', () => ({
  useGatewayRequest: () => ({ requestGateway })
}))

vi.mock('@/store/notifications', () => ({ notify: vi.fn(), notifyError: vi.fn() }))

const CWD = '/work/app'

function summary(name: string, overrides: Partial<SpecSummary> = {}): SpecSummary {
  return {
    documents: { design: true, requirements: true, tasks: true },
    legacy: false,
    name,
    path: `${CWD}/.kiro/specs/${name}`,
    phase: 'implementation',
    progress: { completed: 1, in_progress: 1, optional: 1, total: 3 },
    spec_type: 'feature',
    workflow_type: 'requirements-first',
    ...overrides
  }
}

function detail(name: string, overrides: Partial<SpecDetail> = {}): SpecDetail {
  return {
    ...summary(name),
    content: {
      requirements: '# Requirements Document\n\n### Requirement 1\n\nWHEN searching, THE System SHALL rank results',
      design: '# Design Document\n\n## Overview',
      tasks: '# Implementation Plan'
    },
    files: {
      requirements: `${CWD}/.kiro/specs/${name}/requirements.md`,
      design: `${CWD}/.kiro/specs/${name}/design.md`,
      tasks: `${CWD}/.kiro/specs/${name}/tasks.md`
    },
    next_task: '2.1',
    tasks: [
      {
        depth: 0,
        details: ['Create search/index.py'],
        id: '1',
        line: 2,
        optional: false,
        requirements: ['1.1'],
        status: 'completed',
        title: 'Set up the index'
      },
      {
        depth: 0,
        details: [],
        id: '2',
        line: 6,
        optional: false,
        requirements: [],
        status: 'in_progress',
        title: 'Query support'
      },
      {
        depth: 1,
        details: [],
        id: '2.1',
        line: 7,
        optional: false,
        requirements: ['1.2'],
        status: 'not_started',
        title: 'Parse queries'
      },
      {
        depth: 1,
        details: [],
        id: '2.2',
        line: 9,
        optional: true,
        requirements: [],
        status: 'not_started',
        title: 'Property tests'
      }
    ],
    ...overrides
  }
}

let specs: SpecSummary[] = []
let details: Record<string, SpecDetail> = {}

async function renderView() {
  const { SpecsView } = await import('./index')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <SpecsView />
      </QueryClientProvider>
    )
  })
}

const run = vi.fn()

beforeEach(() => {
  $gatewayState.set('open')
  $currentCwd.set(CWD)
  $newChatRunAction.set(run)
  specs = [summary('offline-search')]
  details = { 'offline-search': detail('offline-search') }
  requestGateway.mockImplementation((method: string, params: { cwd: string; name?: string }) => {
    if (method === 'spec.list') {
      return Promise.resolve({ specs })
    }

    if (method === 'spec.get') {
      return Promise.resolve(details[params.name!])
    }

    return Promise.reject(new Error(method))
  })
})

afterEach(() => {
  cleanup()
  run.mockReset()
  requestGateway.mockReset()
  $newChatRunAction.set(null)
})

describe('SpecsView', () => {
  it('asks for a project when the chat has no workspace', async () => {
    $currentCwd.set('')
    await renderView()
    expect(screen.getByText('Open a project to use specs')).toBeTruthy()
    expect(requestGateway).not.toHaveBeenCalled()
  })

  it("lists the workspace's specs and opens the newest document tab", async () => {
    await renderView()

    await waitFor(() => expect(screen.getAllByTestId('spec-list-item')).toHaveLength(1))
    expect(requestGateway).toHaveBeenCalledWith('spec.list', { cwd: CWD })
    expect(screen.getByText('1/3 tasks', { selector: 'span' })).toBeTruthy()
    // Tasks exist → the task list tab is open with Kiro's checkbox states.
    const tasks = await screen.findAllByTestId('spec-task')
    expect(tasks.map(task => task.dataset.status)).toEqual(['completed', 'in_progress', 'not_started', 'not_started'])
  })

  it('creates a spec in each mode through /spec in a new chat', async () => {
    await renderView()

    const box = screen.getByLabelText('New spec')
    fireEvent.change(box, { target: { value: 'offline search' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create spec' }))
    expect(run).toHaveBeenLastCalledWith('/spec new offline search')

    fireEvent.change(box, { target: { value: 'dark mode' } })
    fireEvent.click(screen.getByRole('button', { name: 'Autopilot' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create spec' }))
    expect(run).toHaveBeenLastCalledWith('/spec auto dark mode')
  })

  it('starts the next task, any task, or all of them', async () => {
    await renderView()
    await screen.findAllByTestId('spec-task')

    fireEvent.click(within(screen.getByTestId('spec-next-step')).getByRole('button'))
    expect(run).toHaveBeenLastCalledWith('/spec task offline-search 2.1')

    const optional = screen.getAllByTestId('spec-task').find(task => task.dataset.task === '2.2')!
    fireEvent.click(within(optional).getByRole('button', { name: /Start task/ }))
    expect(run).toHaveBeenLastCalledWith('/spec task offline-search 2.2')

    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /Run all tasks/ }))
    expect(run).toHaveBeenLastCalledWith('/spec run offline-search --optional')

    const done = screen.getAllByTestId('spec-task').find(task => task.dataset.task === '1')!
    expect(within(done).queryByRole('button')).toBeNull()
  })

  it('approves the newest document and sends requested changes', async () => {
    specs = [
      summary('offline-search', {
        documents: { design: false, requirements: true, tasks: false },
        phase: 'requirements'
      })
    ]
    details = {
      'offline-search': detail('offline-search', {
        documents: { design: false, requirements: true, tasks: false },
        next_task: null,
        phase: 'requirements',
        tasks: []
      })
    }
    await renderView()

    await waitFor(() => expect(screen.getByTestId('spec-doc-requirements').textContent).toContain('THE System SHALL'))

    fireEvent.click(within(screen.getByTestId('spec-next-step')).getByRole('button', { name: 'Approve → design' }))
    expect(run).toHaveBeenLastCalledWith('/spec approve offline-search requirements')

    fireEvent.click(screen.getByRole('button', { name: 'Request changes' }))
    fireEvent.change(screen.getByPlaceholderText('What should change?'), { target: { value: 'cover offline mode' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(run).toHaveBeenLastCalledWith('/spec refine offline-search requirements cover offline mode')

    fireEvent.click(screen.getByRole('tab', { name: /Design/ }))
    expect(screen.getByText('Approve the requirements to generate the design.')).toBeTruthy()
  })
})

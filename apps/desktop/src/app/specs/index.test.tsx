// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { $newChatRunAction } from '@/store/new-chat-run'
import { notify, notifyError } from '@/store/notifications'
import { $activeSessionId, $currentCwd, $gatewayState } from '@/store/session'
import { $workspaceChangeTick } from '@/store/workspace-events'

import type { SpecDetail, SpecRun, SpecSummary } from './spec-model'

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
let runs: SpecRun[] = []
let runResult: { output: string; run: null | SpecRun; spec: string } | Error = { output: '', run: null, spec: '' }

function specRun(overrides: Partial<SpecRun> = {}): SpecRun {
  return {
    activity: [],
    error: '',
    finished_at: null,
    id: 'spec_1',
    label: 'Starting task 2.1 of offline-search: Parse queries',
    mode: 'accept-edits',
    spec: 'offline-search',
    started_at: Date.now() / 1000,
    status: 'running',
    summary: '',
    ...overrides
  }
}

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

// Spec work never opens a chat: the shell's new-chat action must stay unused.
const openChat = vi.fn()

const specRunCalls = () =>
  requestGateway.mock.calls.filter(([method]) => method === 'spec.run').map(([, params]) => params.args)

beforeEach(() => {
  $gatewayState.set('open')
  $currentCwd.set(CWD)
  $activeSessionId.set('sess-7')
  $newChatRunAction.set(openChat)
  specs = [summary('offline-search')]
  details = { 'offline-search': detail('offline-search') }
  runs = []
  runResult = { output: 'Started.', run: specRun(), spec: 'offline-search' }
  requestGateway.mockImplementation((method: string, params: { cwd: string; name?: string }) => {
    switch (method) {
      case 'spec.list':
        return Promise.resolve({ specs })

      case 'spec.get':
        return Promise.resolve(details[params.name!])

      case 'spec.runs':
        return Promise.resolve({ runs })

      case 'spec.run':
        return runResult instanceof Error ? Promise.reject(runResult) : Promise.resolve(runResult)

      case 'spec.stop':
        return Promise.resolve({ stopped: true })

      default:
        return Promise.reject(new Error(method))
    }
  })
})

afterEach(() => {
  expect(openChat).not.toHaveBeenCalled()
  cleanup()
  openChat.mockReset()
  requestGateway.mockReset()
  vi.mocked(notify).mockReset()
  vi.mocked(notifyError).mockReset()
  $newChatRunAction.set(null)
  $activeSessionId.set(null)
})

describe('SpecsView', () => {
  it('asks for a project when the chat has no workspace', async () => {
    $currentCwd.set('')
    await renderView()
    expect(screen.getByText('Open a project to use specs')).toBeTruthy()
    expect(requestGateway).not.toHaveBeenCalled()
  })

  it('creates a spec headlessly from the welcome composer', async () => {
    specs = []
    await renderView()

    expect(await screen.findByText('Plan it before you build it')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('New spec'), { target: { value: 'offline search' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create spec' }))

    await waitFor(() =>
      expect(requestGateway).toHaveBeenCalledWith('spec.run', {
        args: 'new offline search',
        cwd: CWD,
        session_id: 'sess-7'
      })
    )
  })

  it("lists the workspace's specs and opens the newest document", async () => {
    await renderView()

    await waitFor(() => expect(screen.getAllByTestId('spec-list-item')).toHaveLength(1))
    expect(requestGateway).toHaveBeenCalledWith('spec.list', { cwd: CWD })
    expect(screen.getAllByText('1/3 tasks').length).toBeGreaterThan(0)
    const tasks = await screen.findAllByTestId('spec-task')
    expect(tasks.map(task => task.dataset.status)).toEqual(['completed', 'in_progress', 'not_started', 'not_started'])
  })

  it('creates another spec in any mode from the New spec button', async () => {
    await renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'New spec' }))
    fireEvent.change(screen.getByLabelText('New spec'), { target: { value: 'dark mode' } })
    fireEvent.click(screen.getByRole('button', { name: 'Autopilot' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create spec' }))

    await waitFor(() => expect(specRunCalls()).toEqual(['auto dark mode']))
    expect(screen.queryByRole('button', { name: 'Create spec' })).toBeNull()
  })

  it('starts the next task in the background', async () => {
    await renderView()
    await screen.findAllByTestId('spec-task')

    fireEvent.click(within(screen.getByTestId('spec-next-step')).getByRole('button'))
    await waitFor(() => expect(specRunCalls()).toEqual(['task offline-search 2.1']))
  })

  it("shows the agent's live work in place and holds the spec's actions", async () => {
    runs = [
      specRun({
        activity: [
          { at: 1, kind: 'tool', text: 'read_file  src/search.py' },
          { at: 2, kind: 'tool', text: 'patch  src/search.py' }
        ]
      })
    ]
    await renderView()

    const card = await screen.findByTestId('spec-run')
    expect(card.dataset.status).toBe('running')
    expect(within(card).getByTestId('spec-run-activity').textContent).toContain('patch  src/search.py')
    // No next-step offer and no actions while the agent works on this spec.
    expect(screen.queryByTestId('spec-next-step')).toBeNull()
    expect((screen.getByRole('button', { name: /Run all tasks/ }) as HTMLButtonElement).disabled).toBe(true)

    fireEvent.click(within(card).getByRole('button', { name: /Stop/ }))
    await waitFor(() => expect(requestGateway).toHaveBeenCalledWith('spec.stop', { run_id: 'spec_1' }))
  })

  it("shows the agent's reply once it finishes", async () => {
    runs = [specRun({ status: 'completed', summary: 'Do the requirements look good?', finished_at: 2 })]
    await renderView()

    const card = await screen.findByTestId('spec-run')
    expect(card.dataset.status).toBe('completed')
    expect(within(card).getByTestId('spec-run-reply').textContent).toContain('Do the requirements look good?')
    expect(screen.getByTestId('spec-next-step')).toBeTruthy()
  })

  it('reports a refused action instead of starting anything', async () => {
    runResult = new Error("'offline-search' is already being worked on")
    await renderView()
    await screen.findAllByTestId('spec-task')

    fireEvent.click(within(screen.getByTestId('spec-next-step')).getByRole('button'))
    await waitFor(() => expect(notifyError).toHaveBeenCalledWith(runResult, 'Could not start the agent'))
  })

  it("shows the message of an action that doesn't need the agent", async () => {
    const output = "Task list approved — 'offline-search' is ready."
    runResult = { output, run: null, spec: 'offline-search' }
    await renderView()
    await screen.findAllByTestId('spec-task')

    fireEvent.click(within(screen.getByTestId('spec-next-step')).getByRole('button'))
    await waitFor(() => expect(notify).toHaveBeenCalledWith(expect.objectContaining({ message: output })))
  })

  it('starts any task from its row', async () => {
    await renderView()
    await screen.findAllByTestId('spec-task')

    const optional = screen.getAllByTestId('spec-task').find(task => task.dataset.task === '2.2')!
    fireEvent.click(within(optional).getByRole('button', { name: /Start task/ }))
    await waitFor(() => expect(specRunCalls()).toEqual(['task offline-search 2.2']))

    const done = screen.getAllByTestId('spec-task').find(task => task.dataset.task === '1')!
    expect(within(done).queryByRole('button')).toBeNull()
  })

  it('runs all remaining tasks, optional ones on request', async () => {
    await renderView()
    await screen.findAllByTestId('spec-task')

    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /Run all tasks/ }))
    await waitFor(() => expect(specRunCalls()).toEqual(['run offline-search --optional']))
  })

  function requirementsOnly() {
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
  }

  it('approves the newest document', async () => {
    requirementsOnly()
    await renderView()

    await waitFor(() => expect(screen.getByTestId('spec-doc-requirements').textContent).toContain('THE System SHALL'))
    fireEvent.click(within(screen.getByTestId('spec-next-step')).getByRole('button', { name: 'Approve → design' }))
    await waitFor(() => expect(specRunCalls()).toEqual(['approve offline-search requirements']))

    fireEvent.click(screen.getByRole('tab', { name: /Design/ }))
    expect(screen.getByText('Approve the requirements to generate the design.')).toBeTruthy()
  })

  it('sends requested changes for a document', async () => {
    requirementsOnly()
    await renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'Request changes' }))
    fireEvent.change(screen.getByPlaceholderText('What should change?'), { target: { value: 'cover offline mode' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(specRunCalls()).toEqual(['refine offline-search requirements cover offline mode']))
  })

  it('keeps showing the specs when a background refresh fails', async () => {
    await renderView()
    await screen.findAllByTestId('spec-task')

    requestGateway.mockImplementation(() => Promise.reject(new Error('gateway hiccup')))
    act(() => $workspaceChangeTick.set($workspaceChangeTick.get() + 1))

    await new Promise(resolve => setTimeout(resolve, 50))
    expect(screen.getAllByTestId('spec-list-item')).toHaveLength(1)
    expect(screen.getByTestId('spec-panel')).toBeTruthy()
    expect(screen.queryByText('Could not load specs')).toBeNull()
  })

  it('keeps the current spec on screen while another one loads', async () => {
    specs = [summary('offline-search'), summary('dark-mode')]
    details = { 'offline-search': detail('offline-search'), 'dark-mode': detail('dark-mode') }
    let releaseDarkMode: (value: SpecDetail) => void = () => undefined
    const base = requestGateway.getMockImplementation()!

    requestGateway.mockImplementation((method: string, params: { cwd: string; name?: string }) =>
      method === 'spec.get' && params.name === 'dark-mode'
        ? new Promise<SpecDetail>(resolve => (releaseDarkMode = resolve))
        : base(method, params)
    )
    await renderView()
    await screen.findByTestId('spec-panel')

    fireEvent.click(screen.getAllByTestId('spec-list-item')[1]!)
    expect(screen.getByTestId('spec-panel').textContent).toContain('offline-search')

    await act(async () => releaseDarkMode(details['dark-mode']!))
    await waitFor(() => expect(screen.getByTestId('spec-panel').textContent).toContain('dark-mode'))
  })
})

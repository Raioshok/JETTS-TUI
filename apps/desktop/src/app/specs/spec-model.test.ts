import { describe, expect, it } from 'vitest'

import {
  approveCommand,
  canApprove,
  createCommand,
  currentStage,
  nextAction,
  refineCommand,
  runAllCommand,
  type SpecDetail,
  startTaskCommand
} from './spec-model'

function spec(documents: Partial<SpecDetail['documents']>, nextTask: null | string = null): SpecDetail {
  return {
    content: { design: '', requirements: '', tasks: '' },
    documents: { design: false, requirements: false, tasks: false, ...documents },
    files: { design: '', requirements: '', tasks: '' },
    legacy: false,
    name: 'offline-search',
    next_task: nextTask,
    path: '/p/.kiro/specs/offline-search',
    phase: 'requirements',
    progress: { completed: 0, in_progress: 0, optional: 0, total: 0 },
    spec_type: 'feature',
    tasks: [],
    workflow_type: 'requirements-first'
  }
}

describe('spec commands', () => {
  it('map each action onto the /spec command the backend runs', () => {
    expect(createCommand('step', '  offline\n search ')).toBe('/spec new offline search')
    expect(createCommand('quick', 'x')).toBe('/spec quick x')
    expect(createCommand('auto', 'x')).toBe('/spec auto x')
    expect(approveCommand('s', 'design')).toBe('/spec approve s design')
    expect(refineCommand('s', 'requirements', 'add\nfuzzy  search')).toBe(
      '/spec refine s requirements add fuzzy search'
    )
    expect(startTaskCommand('s', '2.1')).toBe('/spec task s 2.1')
    expect(runAllCommand('s')).toBe('/spec run s')
    expect(runAllCommand('s', true)).toBe('/spec run s --optional')
  })
})

describe('spec workflow', () => {
  it('a stage is approvable only while it is the newest document', () => {
    const reqs = spec({ requirements: true })
    expect(canApprove(reqs, 'requirements')).toBe(true)
    expect(canApprove(reqs, 'design')).toBe(false)

    const design = spec({ requirements: true, design: true })
    expect(canApprove(design, 'requirements')).toBe(false)
    expect(canApprove(design, 'design')).toBe(true)
    expect(canApprove(spec({ requirements: true, design: true, tasks: true }), 'tasks')).toBe(false)
  })

  it('opens on the newest document', () => {
    expect(currentStage(spec({}))).toBe('requirements')
    expect(currentStage(spec({ requirements: true, design: true }))).toBe('design')
  })

  it('offers exactly the step that moves the spec forward', () => {
    expect(nextAction(spec({}))).toEqual({ kind: 'wait', stage: 'requirements' })
    expect(nextAction(spec({ requirements: true }))).toEqual({ kind: 'approve', stage: 'requirements' })
    expect(nextAction(spec({ requirements: true, design: true }))).toEqual({ kind: 'approve', stage: 'design' })
    expect(nextAction(spec({ requirements: true, design: true, tasks: true }, '2.1'))).toEqual({
      kind: 'start',
      taskId: '2.1'
    })
    expect(nextAction(spec({ requirements: true, design: true, tasks: true }))).toEqual({ kind: 'done' })
  })
})

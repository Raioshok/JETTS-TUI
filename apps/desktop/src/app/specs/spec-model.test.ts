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
  specSignature,
  startTaskCommand,
  stepStates
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
    expect(createCommand('step', '  offline\n search ')).toBe('new offline search')
    expect(createCommand('quick', 'x')).toBe('quick x')
    expect(createCommand('auto', 'x')).toBe('auto x')
    expect(approveCommand('s', 'design')).toBe('approve s design')
    expect(refineCommand('s', 'requirements', 'add\nfuzzy  search')).toBe('refine s requirements add fuzzy search')
    expect(startTaskCommand('s', '2.1')).toBe('task s 2.1')
    expect(runAllCommand('s')).toBe('run s')
    expect(runAllCommand('s', true)).toBe('run s --optional')
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

describe('spec progress', () => {
  it('walks the four steps through drafting, review and done', () => {
    expect(stepStates(spec({}))).toEqual({
      requirements: 'drafting',
      design: 'upcoming',
      tasks: 'upcoming',
      build: 'upcoming'
    })
    expect(stepStates(spec({ requirements: true })).requirements).toBe('review')
    expect(stepStates(spec({ requirements: true, design: true }))).toMatchObject({
      requirements: 'done',
      design: 'review'
    })

    const started = {
      ...spec({ requirements: true, design: true, tasks: true }),
      progress: { completed: 1, in_progress: 0, optional: 0, total: 3 }
    }

    expect(stepStates(started)).toMatchObject({ tasks: 'done', build: 'drafting' })
    expect(stepStates({ ...started, phase: 'done' }).build).toBe('done')
  })

  it('signature moves exactly when the agent changes something', () => {
    const before = spec({ requirements: true })
    expect(specSignature(before)).toBe(specSignature(spec({ requirements: true })))
    expect(specSignature(spec({ requirements: true, design: true }))).not.toBe(specSignature(before))
    expect(specSignature({ ...before, progress: { completed: 0, in_progress: 1, optional: 0, total: 3 } })).not.toBe(
      specSignature(before)
    )
  })
})

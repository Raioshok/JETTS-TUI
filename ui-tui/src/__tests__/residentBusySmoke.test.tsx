import { PassThrough } from 'stream'

import { Box, renderSync, ScrollBox, Text } from '@jetts-tui/ink'
import React, { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { ResidentInputTarget, ResidentWorkspaceSidebar, visibleResidentAgents } from '../components/residentWorkspace.js'
import { TextInput } from '../components/textInput.js'
import type { SessionActiveItem } from '../gatewayTypes.js'
import { stripAnsi } from '../lib/text.js'
import { DEFAULT_THEME } from '../theme.js'
import type { SubagentProgress } from '../types.js'

const sessions: SessionActiveItem[] = [{
  current: true,
  id: 'parent',
  model: 'deepseek/deepseek-v4-flash',
  preview: 'Verifying model provider URLs',
  status: 'working',
  title: 'URL audit'
}]

const subagents: SubagentProgress[] = Array.from({ length: 3 }, (_, index) => ({
  depth: 0,
  goal: `Verify source ${index + 1}`,
  id: `child-${index}`,
  index,
  notes: [`Checking URLs in source ${index + 1}`],
  parentId: null,
  status: 'running',
  taskCount: 3,
  thinking: [],
  toolCount: 1,
  tools: []
}))

const renderFrame = () => {
  const stdout = new PassThrough()
  const stdin = new PassThrough()
  const stderr = new PassThrough()
  let output = ''

  Object.assign(stdout, { columns: 120, isTTY: false, rows: 32 })
  Object.assign(stdin, { isTTY: false })
  Object.assign(stderr, { isTTY: false })
  stdout.on('data', chunk => { output += chunk.toString() })

  const instance = renderSync(
    <Box flexDirection="column" height={32} width={120}>
      <Box flexDirection="row" flexGrow={1} flexShrink={1} height={26} minHeight={0}>
        <ResidentWorkspaceSidebar currentSessionId="parent" onNew={() => {}} onOpenAgents={() => {}} onSelect={() => {}} sessions={sessions} subagents={subagents} t={DEFAULT_THEME} unread={new Map()} />
        <ScrollBox flexDirection="column" flexGrow={1} flexShrink={1}>
          {Array.from({ length: 45 }, (_, index) => <Text key={index}>Tool output {index}: long running audit</Text>)}
        </ScrollBox>
      </Box>
      <ResidentInputTarget currentSessionId="parent" sessions={sessions} t={DEFAULT_THEME} />
      <Text>› type while busy</Text>
    </Box>,
    { patchConsole: false, stderr: stderr as NodeJS.WriteStream, stdin: stdin as NodeJS.ReadStream, stdout: stdout as NodeJS.WriteStream }
  )

  instance.unmount()
  instance.cleanup()

  return stripAnsi(output).split('\n')
}

describe('busy resident workspace smoke', () => {
  it('shows active children before completed history when the sidebar is full', () => {
    const completed = Array.from({ length: 5 }, (_, index) => ({
      ...subagents[0]!,
      goal: `Completed ${index}`,
      id: `completed-${index}`,
      status: 'completed' as const
    }))

    expect(visibleResidentAgents([...completed, ...subagents]).slice(0, 3).map(agent => agent.id))
      .toEqual(subagents.map(agent => agent.id))
  })

  it('keeps navigation, activity, and composer visible beside long tool output', () => {
    const lines = renderFrame()
    const frame = lines.join('\n')

    expect(frame).toContain('SESSIONS')
    expect(frame).toContain('URL audit')
    expect(frame).toContain('＋ new session')
    expect(frame).toContain('COMMS')
    expect(frame).toContain('CHILD AGENTS')
    expect(frame).toContain('3 active')
    expect(frame).toContain('Verify source 1')
    expect(frame).toContain('INPUT → URL audit')
    expect(frame).toContain('› type while busy')
  })

  it('accepts typing and submission while the agent is busy', async () => {
    const stdout = new PassThrough()
    const stdin = new PassThrough()
    const stderr = new PassThrough()
    const submitted = vi.fn()

    Object.assign(stdout, { columns: 120, isTTY: true, rows: 32 })
    Object.assign(stdin, { isTTY: true, setRawMode: () => {}, ref: () => {}, unref: () => {} })
    Object.assign(stderr, { isTTY: false })
    stdout.on('data', () => {})

    function BusyComposer() {
      const [draft, setDraft] = useState('')

      return <Box flexDirection="column" height={3}><Text>● STEER AGENT</Text><TextInput color={DEFAULT_THEME.color.text} columns={80} onChange={setDraft} onSubmit={submitted} value={draft} /></Box>
    }

    const instance = renderSync(<BusyComposer />, {
      patchConsole: false,
      stderr: stderr as NodeJS.WriteStream,
      stdin: stdin as NodeJS.ReadStream,
      stdout: stdout as NodeJS.WriteStream
    })

    stdin.write('smoke')
    await new Promise(resolve => setTimeout(resolve, 30))
    stdin.write('\r')
    await new Promise(resolve => setTimeout(resolve, 30))

    expect(submitted).toHaveBeenCalledWith('smoke')
    instance.unmount()
    instance.cleanup()
  })
})

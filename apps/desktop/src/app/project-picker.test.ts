import { describe, expect, it } from 'vitest'

import type { SidebarProjectTree } from '@/app/chat/sidebar/projects/workspace-groups'

import { workspaceOptions } from './project-picker'

function project(overrides: Partial<SidebarProjectTree>): SidebarProjectTree {
  return { id: 'p', label: 'P', path: null, repos: [], sessionCount: 0, ...overrides }
}

describe('workspaceOptions', () => {
  it("lists the sidebar's projects by name, skipping Home and archived ones", () => {
    const options = workspaceOptions(
      [
        project({ id: 'a', label: 'App', path: '/work/app' }),
        project({ id: 'home', label: 'Home', isNoProject: true }),
        project({ id: 'old', label: 'Old', path: '/work/old', archived: true })
      ],
      []
    )

    expect(options).toEqual([{ label: 'App', path: '/work/app' }])
  })

  it("falls back to a project's first repo when it has no root path", () => {
    const repoProject = project({
      label: 'Mono',
      repos: [{ path: '/work/mono/api' } as SidebarProjectTree['repos'][number]]
    })

    expect(workspaceOptions([repoProject], [])).toEqual([{ label: 'Mono', path: '/work/mono/api' }])
  })

  it('adds the chat and picked folders once, labelled by folder name', () => {
    const options = workspaceOptions(
      [project({ label: 'App', path: '/work/app' })],
      ['/work/app/', '/tmp/scratch', '', '/tmp/scratch']
    )

    expect(options).toEqual([
      { label: 'App', path: '/work/app' },
      { label: 'scratch', path: '/tmp/scratch' }
    ])
  })
})

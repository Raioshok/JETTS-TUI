import { useStore } from '@nanostores/react'
import { atom } from 'nanostores'
import { useEffect } from 'react'

import type { SidebarProjectTree } from '@/app/chat/sidebar/projects/workspace-groups'
import { Codicon } from '@/components/ui/codicon'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { useI18n } from '@/i18n'
import { selectDesktopPaths } from '@/lib/desktop-fs'
import { notifyError } from '@/store/notifications'
import { $projectTree, refreshProjectTree } from '@/store/projects'

// Pages that do work in a project (Orchestrator, Specs) let you pick which.
// Each page keeps its own pick; null follows the current chat's project.
// Window-scoped and in memory: a pick holds while you work, and a fresh
// window starts from wherever its chat is.
export const $orchestratorWorkspace = atom<null | string>(null)
export const $specsWorkspace = atom<null | string>(null)

const BROWSE = '__browse__'

export interface WorkspaceOption {
  label: string
  path: string
}

const leaf = (path: string) =>
  path
    .split(/[\\/]+/)
    .filter(Boolean)
    .pop() ?? path

const samePath = (a: string, b: string) => a.replace(/[\\/]+$/, '') === b.replace(/[\\/]+$/, '')

/** Projects you can run in — the sidebar's projects (named and auto-detected
 *  repos) — plus the current chat's folder and the picked one when no project
 *  covers them, so the selection always has a row. */
export function workspaceOptions(tree: readonly SidebarProjectTree[], extras: readonly string[]): WorkspaceOption[] {
  const options: WorkspaceOption[] = []

  const add = (path: string, label: string) => {
    const trimmed = path.trim()

    if (trimmed && !options.some(option => samePath(option.path, trimmed))) {
      options.push({ label, path: trimmed })
    }
  }

  for (const project of tree) {
    if (project.isNoProject || project.archived) {
      continue
    }

    const path = project.path || project.repos.find(repo => repo.path)?.path || ''
    add(path, project.label || leaf(path))
  }

  for (const path of extras) {
    add(path, leaf(path))
  }

  return options
}

interface ProjectPickerProps {
  /** The folder in use (the pick, else the current chat's). */
  value: string
  /** The current chat's folder, offered even if no project covers it. */
  chatCwd: string
  onChange: (path: string) => void
}

export function ProjectPicker({ chatCwd, onChange, value }: ProjectPickerProps) {
  const { t } = useI18n()
  const o = t.projectPicker
  const tree = useStore($projectTree)
  const options = workspaceOptions(tree, [chatCwd, value])

  // The sidebar normally keeps the project list fresh; cover a cold start.
  useEffect(() => {
    if ($projectTree.get().length === 0) {
      void refreshProjectTree()
    }
  }, [])

  const browse = async () => {
    try {
      const [dir] = await selectDesktopPaths({
        defaultPath: value || chatCwd || undefined,
        directories: true,
        multiple: false,
        title: o.pickProject
      })

      if (dir) {
        onChange(dir)
      }
    } catch (error) {
      notifyError(error, o.browseFailed)
    }
  }

  const choose = (next: string) => {
    if (next === BROWSE) {
      void browse()
    } else {
      onChange(next)
    }
  }

  return (
    <Select onValueChange={choose} value={value || undefined}>
      <SelectTrigger
        aria-label={o.project}
        className="h-8 w-auto min-w-44 max-w-72 gap-1.5 rounded-md text-xs"
        data-testid="project-picker"
      >
        <Codicon className="shrink-0 text-(--ui-text-tertiary)" name="folder" size="0.8rem" />
        <SelectValue placeholder={o.pickProject} />
      </SelectTrigger>
      <SelectContent>
        {options.length > 0 && (
          <SelectGroup>
            <SelectLabel>{o.projects}</SelectLabel>
            {options.map(option => (
              <SelectItem key={option.path} title={option.path} value={option.path}>
                {option.label}
              </SelectItem>
            ))}
          </SelectGroup>
        )}
        <SelectGroup className={options.length > 0 ? 'mt-1 border-t border-(--ui-stroke-tertiary) pt-1' : undefined}>
          <SelectItem value={BROWSE}>{o.browseFolder}</SelectItem>
        </SelectGroup>
      </SelectContent>
    </Select>
  )
}

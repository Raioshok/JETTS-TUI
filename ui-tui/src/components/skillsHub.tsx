import { Box, Text, useInput, useStdout } from '@jetts-tui/ink'
import { useEffect, useState } from 'react'

import type { GatewayClient } from '../gatewayClient.js'
import { rpcErrorMessage } from '../lib/rpc.js'
import type { Theme } from '../theme.js'

import { OverlayHint, useOverlayKeys, windowItems, windowOffset } from './overlayControls.js'
import { chipRowProps } from './overlayPrimitives.js'
import { clampOverlayWidth } from './overlayPrimitives.js'

const VISIBLE = 12
const MIN_WIDTH = 40
const MAX_WIDTH = 90

export function SkillsHub({ gw, maxWidth, onClose, t }: SkillsHubProps) {
  const [skillsByCat, setSkillsByCat] = useState<Record<string, string[]>>({})
  const [selectedCat, setSelectedCat] = useState('')
  const [catIdx, setCatIdx] = useState(0)
  const [skillIdx, setSkillIdx] = useState(0)
  const [stage, setStage] = useState<'actions' | 'category' | 'skill'>('category')
  const [info, setInfo] = useState<null | SkillInfo>(null)
  const [installing, setInstalling] = useState(false)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)

  const [filter, setFilter] = useState('')

  const { stdout } = useStdout()
  const visibleLimit = Math.max(4, Math.min(VISIBLE, (stdout?.rows ?? 24) - 12))
  const terminalWidth = Math.max(1, (stdout?.columns ?? 80) - 6)
  const preferredWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, terminalWidth))
  const width = clampOverlayWidth(preferredWidth, maxWidth)

  useEffect(() => {
    gw.request<{ skills?: Record<string, string[]> }>('skills.manage', { action: 'list' })
      .then(r => {
        setSkillsByCat(r?.skills ?? {})
        setErr('')
        setLoading(false)
      })
      .catch((e: unknown) => {
        setErr(rpcErrorMessage(e))
        setLoading(false)
      })
  }, [gw])

  const allCats = Object.keys(skillsByCat).sort()
  const needle = filter.trim().toLowerCase()

  const cats =
    stage === 'category' && needle
      ? allCats.filter(
          c => c.toLowerCase().includes(needle) || (skillsByCat[c] ?? []).some(s => s.toLowerCase().includes(needle))
        )
      : allCats

  const rawSkills = selectedCat ? (skillsByCat[selectedCat] ?? []) : []
  const skills = stage === 'skill' && needle ? rawSkills.filter(s => s.toLowerCase().includes(needle)) : rawSkills
  const skillName = skills[skillIdx] ?? ''

  const back = () => {
    if ((stage === 'category' || stage === 'skill') && filter) {
      setFilter('')
      setCatIdx(0)
      setSkillIdx(0)

      return
    }

    if (stage === 'actions') {
      setStage('skill')
      setInfo(null)
      setErr('')

      return
    }

    if (stage === 'skill') {
      setStage('category')
      setSkillIdx(0)
      setFilter('')

      return
    }

    onClose()
  }

  const listStage = stage === 'category' || stage === 'skill'
  useOverlayKeys({ disabled: installing || listStage, onBack: back, onClose })

  const inspect = (name: string) => {
    setInfo(null)
    setErr('')

    gw.request<{ info?: SkillInfo }>('skills.manage', { action: 'inspect', query: name })
      .then(r => setInfo(r?.info ?? { name }))
      .catch((e: unknown) => setErr(rpcErrorMessage(e)))
  }

  const install = (name: string) => {
    setInstalling(true)
    setErr('')

    gw.request<{ installed?: boolean; name?: string }>('skills.manage', { action: 'install', query: name })
      .then(() => onClose())
      .catch((e: unknown) => setErr(rpcErrorMessage(e)))
      .finally(() => setInstalling(false))
  }

  useInput((ch, key) => {
    if (installing) {
      return
    }

    if (stage === 'actions') {
      if (key.return) {
        setStage('skill')
        setInfo(null)
        setErr('')

        return
      }

      if (ch.toLowerCase() === 'x' && skillName) {
        install(skillName)

        return
      }

      if (ch.toLowerCase() === 'i' && skillName) {
        inspect(skillName)
      }

      return
    }

    if (key.escape) {
      back()

      return
    }

    if (ch === 'q' && !filter) {
      onClose()

      return
    }

    const count = stage === 'category' ? cats.length : skills.length
    const sel = stage === 'category' ? catIdx : skillIdx
    const setSel = stage === 'category' ? setCatIdx : setSkillIdx

    if ((key.upArrow || (key as { wheelUp?: boolean }).wheelUp) && sel > 0) {
      setSel(v => Math.max(0, v - 1))

      return
    }

    if ((key.downArrow || (key as { wheelDown?: boolean }).wheelDown) && sel < count - 1) {
      setSel(v => Math.min(count - 1, v + 1))

      return
    }

    if (key.pageUp && count > 0) {
      setSel(v => Math.max(0, v - visibleLimit))

      return
    }

    if (key.pageDown && count > 0) {
      setSel(v => Math.min(count - 1, v + visibleLimit))

      return
    }

    if (key.home && count > 0) {
      setSel(0)

      return
    }

    if (key.end && count > 0) {
      setSel(count - 1)

      return
    }

    if (key.backspace || key.delete) {
      setFilter(f => f.slice(0, -1))
      setSel(0)

      return
    }

    if (ch === '\u0015' || (key.ctrl && ch.toLowerCase() === 'u')) {
      setFilter('')
      setSel(0)

      return
    }

    if (key.return) {
      if (stage === 'category') {
        const cat = cats[catIdx]

        if (!cat) {
          return
        }

        setSelectedCat(cat)
        setSkillIdx(0)
        setFilter('')
        setStage('skill')

        return
      }

      const name = skills[skillIdx]

      if (name) {
        setStage('actions')
        inspect(name)
      }

      return
    }

    const n = !filter ? (ch === '0' ? 10 : parseInt(ch, 10)) : Number.NaN

    if (!Number.isNaN(n) && n >= 1 && n <= Math.min(10, count)) {
      const next = windowOffset(count, sel, visibleLimit) + n - 1

      if (stage === 'category') {
        const cat = cats[next]

        if (cat) {
          setSelectedCat(cat)
          setCatIdx(next)
          setSkillIdx(0)
          setFilter('')
          setStage('skill')
        }

        return
      }

      const name = skills[next]

      if (name) {
        setSkillIdx(next)
        setStage('actions')
        inspect(name)
      }

      return
    }

    if (ch && ch.length === 1 && ch >= ' ' && !key.ctrl && !key.meta) {
      setFilter(f => f + ch)
      setSel(0)
    }
  })

  if (loading) {
    return <Text color={t.color.muted}>loading skills…</Text>
  }

  if (err && stage === 'category') {
    return (
      <Box flexDirection="column" width={width}>
        <Text color={t.color.label}>error: {err}</Text>
        <OverlayHint t={t}>Esc/q cancel</OverlayHint>
      </Box>
    )
  }

  if (!allCats.length) {
    return (
      <Box flexDirection="column" width={width}>
        <Text color={t.color.muted}>no skills available</Text>
        <OverlayHint t={t}>Esc/q cancel</OverlayHint>
      </Box>
    )
  }

  if (stage === 'category') {
    const rows = cats.map(c => `${c} · ${skillsByCat[c]?.length ?? 0} skills`)
    const { items, offset } = windowItems(rows, catIdx, visibleLimit)

    return (
      <Box flexDirection="column" width={width}>
        <Text bold color={t.color.accent}>
          Skills Hub
        </Text>

        <Text color={filter ? t.color.accent : t.color.muted} wrap="truncate-end">
          {filter ? `filter: ${filter}▎` : 'select a category · type to filter'}
        </Text>
        {!rows.length ? <Text color={t.color.muted}>no categories match "{filter}"</Text> : null}
        {offset > 0 && <Text color={t.color.muted}> ↑ {offset} more</Text>}

        {items.map((row, i) => {
          const idx = offset + i

          return (
            <Text color={t.color.muted} {...chipRowProps(t, catIdx === idx)} key={row} wrap="truncate-end">
              {catIdx === idx ? '▸ ' : '  '}
              {i + 1}. {row}
            </Text>
          )
        })}

        {offset + visibleLimit < rows.length && (
          <Text color={t.color.muted}> ↓ {rows.length - offset - visibleLimit} more</Text>
        )}
        <OverlayHint t={t}>↑/↓ select · Enter open · type filter · Esc clear/close</OverlayHint>
      </Box>
    )
  }

  if (stage === 'skill') {
    const { items, offset } = windowItems(skills, skillIdx, visibleLimit)

    return (
      <Box flexDirection="column" width={width}>
        <Text bold color={t.color.accent}>
          {selectedCat}
        </Text>

        <Text color={filter ? t.color.accent : t.color.muted} wrap="truncate-end">
          {filter ? `filter: ${filter}▎ · ` : ''}
          {skills.length} skill(s)
        </Text>
        {!skills.length ? (
          <Text color={t.color.muted}>{filter ? `no skills match "${filter}"` : 'no skills in this category'}</Text>
        ) : null}
        {offset > 0 && <Text color={t.color.muted}> ↑ {offset} more</Text>}

        {items.map((row, i) => {
          const idx = offset + i

          return (
            <Text color={t.color.muted} {...chipRowProps(t, skillIdx === idx)} key={row} wrap="truncate-end">
              {skillIdx === idx ? '▸ ' : '  '}
              {i + 1}. {row}
            </Text>
          )
        })}

        {offset + visibleLimit < skills.length && (
          <Text color={t.color.muted}> ↓ {skills.length - offset - visibleLimit} more</Text>
        )}
        <OverlayHint t={t}>
          {skills.length ? '↑/↓ select · Enter open · 1-9,0 quick · Esc back · q close' : 'Esc back · q close'}
        </OverlayHint>
      </Box>
    )
  }

  return (
    <Box flexDirection="column" width={width}>
      <Text bold color={t.color.accent}>
        {info?.name ?? skillName}
      </Text>

      <Text color={t.color.muted}>{info?.category ?? selectedCat}</Text>
      {info?.description ? <Text color={t.color.text}>{info.description}</Text> : null}
      {info?.path ? <Text color={t.color.muted}>path: {info.path}</Text> : null}
      {!info && !err ? <Text color={t.color.muted}>loading…</Text> : null}
      {err ? <Text color={t.color.label}>error: {err}</Text> : null}
      {installing ? <Text color={t.color.accent}>installing…</Text> : null}

      <OverlayHint t={t}>i reinspect · x reinstall · Enter/Esc back · q close</OverlayHint>
    </Box>
  )
}

interface SkillInfo {
  category?: string
  description?: string
  name?: string
  path?: string
}

interface SkillsHubProps {
  gw: GatewayClient
  maxWidth?: number
  onClose: () => void
  t: Theme
}

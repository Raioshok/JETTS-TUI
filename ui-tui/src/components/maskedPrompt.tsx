import { Box, Text } from '@jetts-tui/ink'
import { useState } from 'react'

import type { Theme } from '../theme.js'

import { TextInput } from './textInput.js'

export function MaskedPrompt({ cols = 80, icon, label, onSubmit, sub, t }: MaskedPromptProps) {
  const [value, setValue] = useState('')

  return (
    <Box borderColor={t.color.warn} borderStyle="round" flexDirection="column" paddingX={1}>
      <Text bold color={t.color.warn}>
        {icon} {label}
      </Text>

      {sub && <Text color={t.color.muted}> {sub}</Text>}

      <Box>
        <Text color={t.color.label}>{'> '}</Text>
        <TextInput
          color={t.color.text}
          columns={Math.max(20, cols - 10)}
          mask="*"
          onChange={setValue}
          onSubmit={submitted => {
            if (submitted.trim()) {
              onSubmit(submitted)
            }
          }}
          value={value}
        />
      </Box>

      <Text color={t.color.muted}>Enter submit · Esc/Ctrl+C cancel</Text>
    </Box>
  )
}

interface MaskedPromptProps {
  cols?: number
  icon: string
  label: string
  onSubmit: (v: string) => void
  sub?: string
  t: Theme
}

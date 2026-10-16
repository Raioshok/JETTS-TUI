import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { getDiscordRpcStatus, testDiscordRpc } from '@/jettstui'
import { DiscordIcon, ExternalLink, Loader2, Zap } from '@/lib/icons'
import { notify, notifyError } from '@/store/notifications'
import type { JettsTUIConfigRecord } from '@/types/jettstui'

import { getNested, setNested } from './helpers'

const PRESET_OPTIONS = [
  {
    id: 'pairing',
    title: 'Pairing',
    details: '⚡ Pairing with JettsTUI ({model})',
    state: '📂 Workspace: {project}'
  },
  {
    id: 'vibe_coding',
    title: 'Vibe Coding',
    details: '✨ Vibe Coding: {project}',
    state: '🧠 {model} • Flow State'
  },
  {
    id: 'autonomous',
    title: 'Autonomous',
    details: '🤖 Autonomous Agent Running',
    state: '⚡ 12 tools active • {project}'
  },
  {
    id: 'fine_tuning',
    title: 'Fine-Tuning',
    details: '🔬 Local LLM Fine-Tuning ({model})',
    state: '🎯 RTX 3060 CUDA • {project}'
  },
  {
    id: 'idle',
    title: 'Idle / Ready',
    details: 'JettsTUI — Ready to Code',
    state: '📂 {project}'
  }
]

export function DiscordRpcSettings({
  config,
  onConfigChange
}: {
  config: JettsTUIConfigRecord
  onConfigChange: (updated: JettsTUIConfigRecord) => void
}) {
  const [testing, setTesting] = useState(false)

  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['discord-rpc-status'],
    queryFn: getDiscordRpcStatus,
    refetchInterval: 5000
  })

  const isEnabled = Boolean(getNested(config, 'discord_rpc.enabled'))
  const currentPreset = String(getNested(config, 'discord_rpc.preset') ?? 'pairing')
  const customDetails = getNested(config, 'discord_rpc.details')
  const customState = getNested(config, 'discord_rpc.state')

  const activePresetInfo = PRESET_OPTIONS.find(p => p.id === currentPreset) ?? PRESET_OPTIONS[0]

  const displayDetails = customDetails
    ? String(customDetails).replace('{model}', 'Qwen-2.5-Coder').replace('{project}', 'JETTS-TUI')
    : activePresetInfo.details.replace('{model}', 'Qwen-2.5-Coder').replace('{project}', 'JETTS-TUI')

  const displayState = customState
    ? String(customState).replace('{model}', 'Qwen-2.5-Coder').replace('{project}', 'JETTS-TUI')
    : activePresetInfo.state.replace('{model}', 'Qwen-2.5-Coder').replace('{project}', 'JETTS-TUI')

  async function handleTest() {
    try {
      setTesting(true)
      const res = await testDiscordRpc()

      if (res.ok) {
        notify({
          kind: 'success',
          title: 'Discord Presence Active',
          message: 'Test activity sent! Check your Discord profile.'
        })
      } else {
        notifyError(new Error(res.error || 'Discord IPC rejected activity'), 'Test Failed')
      }

      void refetchStatus()
    } catch (err) {
      notifyError(err, 'Failed to connect to Discord')
    } finally {
      setTesting(false)
    }
  }

  function handleSelectPreset(presetId: string) {
    onConfigChange(setNested(config, 'discord_rpc.preset', presetId))
  }

  return (
    <div className="mb-6 flex flex-col gap-4">
      {/* Discord Profile Card Preview */}
      <div className="relative overflow-hidden rounded-2xl border border-[#5865F2]/30 bg-[#2B2D31] p-5 shadow-lg text-[#F2F3F5]">
        <div className="flex items-center justify-between pb-3 border-b border-[#35373C]">
          <div className="flex items-center gap-2 text-xs font-bold tracking-wider text-[#949BA4] uppercase">
            <DiscordIcon className="size-4 text-[#5865F2]" />
            <span>Playing a Game</span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${
                status?.connected ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'
              }`}
            >
              <span className={`size-1.5 rounded-full ${status?.connected ? 'bg-emerald-400' : 'bg-amber-400'}`} />
              {status?.connected ? 'Connected to Discord' : 'Discord Not Running'}
            </span>
          </div>
        </div>

        {/* Card Body */}
        <div className="flex gap-4 pt-4">
          {/* Large Image with Small Badge */}
          <div className="relative size-16 shrink-0 rounded-xl bg-[#1E1F22] p-1 border border-[#35373C] flex items-center justify-center overflow-hidden">
            <img
              alt="JettsTUI"
              className="size-full object-contain rounded-lg"
              src="https://raw.githubusercontent.com/Raioshok/JETTS-TUI/main/apps/desktop/assets/icon.png"
            />
            <div className="absolute -bottom-1 -right-1 size-5 rounded-full bg-[#1E1F22] p-0.5 flex items-center justify-center">
              <span className="size-3 rounded-full bg-[#5865F2] flex items-center justify-center text-[8px] text-white font-bold">
                ⚡
              </span>
            </div>
          </div>

          {/* Details & State */}
          <div className="flex flex-col justify-center min-w-0">
            <div className="font-bold text-sm text-[#F2F3F5] truncate">JettsTUI</div>
            <div className="text-xs text-[#DBDEE1] truncate font-medium">{displayDetails}</div>
            <div className="text-xs text-[#949BA4] truncate">{displayState}</div>
            <div className="text-[11px] text-[#57F287] font-mono mt-0.5">⏱️ 00:42:15 elapsed</div>
          </div>
        </div>

        {/* Buttons Simulation */}
        <div className="mt-4 grid grid-cols-2 gap-2">
          <a
            className="flex items-center justify-center gap-1.5 rounded-md bg-[#4E5058]/40 hover:bg-[#4E5058]/70 px-3 py-2 text-xs font-semibold text-white transition-colors"
            href="https://github.com/Raioshok/JETTS-TUI"
            rel="noreferrer"
            target="_blank"
          >
            <span>⭐ Star on GitHub</span>
            <ExternalLink className="size-3 opacity-70" />
          </a>
          <a
            className="flex items-center justify-center gap-1.5 rounded-md bg-[#4E5058]/40 hover:bg-[#4E5058]/70 px-3 py-2 text-xs font-semibold text-white transition-colors"
            href="https://github.com/Raioshok/JETTS-TUI"
            rel="noreferrer"
            target="_blank"
          >
            <span>🚀 Try JettsTUI</span>
            <ExternalLink className="size-3 opacity-70" />
          </a>
        </div>

        {/* Card Footer Actions */}
        <div className="mt-4 flex items-center justify-between pt-3 border-t border-[#35373C]/80">
          <div className="text-xs text-[#949BA4]">
            {isEnabled ? 'Rich Presence is active for this computer.' : 'Enable presence below to advertise on Discord.'}
          </div>
          <Button
            className="gap-1.5 bg-[#5865F2] hover:bg-[#4752C4] text-white border-0 text-xs h-7"
            disabled={testing}
            onClick={handleTest}
            size="sm"
          >
            {testing ? <Loader2 className="size-3.5 animate-spin" /> : <Zap className="size-3.5" />}
            <span>Test Presence (5s)</span>
          </Button>
        </div>
      </div>

      {/* Preset Picker Cards */}
      <div className="flex flex-col gap-2">
        <label className="text-xs font-semibold text-foreground">Activity Preset</label>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {PRESET_OPTIONS.map(preset => {
            const isSelected = currentPreset === preset.id

            return (
              <button
                className={`flex flex-col items-start gap-1 p-2.5 rounded-xl border text-left transition-all ${
                  isSelected
                    ? 'border-[#5865F2] bg-[#5865F2]/10 text-foreground font-medium ring-1 ring-[#5865F2]'
                    : 'border-border/60 bg-card hover:bg-muted/40 text-muted-foreground'
                }`}
                key={preset.id}
                onClick={() => handleSelectPreset(preset.id)}
                type="button"
              >
                <div className="text-xs font-semibold text-foreground flex items-center justify-between w-full">
                  <span>{preset.title}</span>
                  {isSelected && <span className="size-1.5 rounded-full bg-[#5865F2]" />}
                </div>
                <div className="text-[11px] text-muted-foreground line-clamp-1">{preset.details}</div>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

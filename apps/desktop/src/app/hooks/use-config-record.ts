import { useQuery } from '@tanstack/react-query'

import { getJettsTUIConfigRecord } from '@/jettstui'
import { queryClient, writeCache } from '@/lib/query-client'
import type { JettsTUIConfigRecord } from '@/types/jettstui'

// One shared cache for the whole profile config record (`GET /api/config`).
// Every settings surface (MCP, model, config) reads and writes through this key
// so a save in one shows in the others, and revisiting a tab paints the cache
// instead of blanking on a fresh fetch.
//
// Distinct from session/hooks/use-jettstui-config.ts, which is side-effecting —
// it pushes personality/cwd/voice/… into the session stores for live chat.
export const JETTSTUI_CONFIG_KEY = ['jettstui-config-record'] as const

// staleTime 0 → serve cache instantly, background-revalidate on every mount.
export const useJettsTUIConfigRecord = () =>
  useQuery({ queryKey: JETTSTUI_CONFIG_KEY, queryFn: getJettsTUIConfigRecord, staleTime: 0 })

export const setJettsTUIConfigCache = writeCache<JettsTUIConfigRecord>(JETTSTUI_CONFIG_KEY)

export const invalidateJettsTUIConfig = () => queryClient.invalidateQueries({ queryKey: JETTSTUI_CONFIG_KEY })

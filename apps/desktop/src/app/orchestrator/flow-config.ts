// Pure helpers for the Orchestrator page — the shapes the `orchestrator.get` /
// `orchestrator.save` RPCs exchange (agent/orchestrator.py owns the truth) and
// the select-value encoding the role pickers use.

export const ORCHESTRATOR_ROLE_IDS = ['planner', 'executor', 'reviewer', 'verifier'] as const

export type OrchestratorRoleId = (typeof ORCHESTRATOR_ROLE_IDS)[number]

export interface OrchestratorRoleModel {
  provider: string
  model: string
}

/** How Auto trades cost for quality (agent/orchestrator.py BALANCE_MODES). */
export const BALANCE_MODES = ['economy', 'balanced', 'quality'] as const

export type BalanceMode = (typeof BALANCE_MODES)[number]

export const DEFAULT_BALANCE: BalanceMode = 'balanced'

export interface OrchestratorConfig {
  enabled: boolean
  max_review_rounds: number
  /** Absent from configs saved before the balance setting existed. */
  auto_balance?: BalanceMode
  roles: Record<OrchestratorRoleId, OrchestratorRoleModel>
}

export interface OrchestratorAssignment extends OrchestratorRoleModel {
  auto: boolean
  /** '$' … '$$$$', or '' when the model's price is unknown. */
  cost_tier?: string
  reason: string
  role: OrchestratorRoleId
}

export interface OrchestratorPayload {
  assignments: Record<OrchestratorRoleId, OrchestratorAssignment>
  config: OrchestratorConfig
}

/** Select value for "let Auto pick" — never a valid `provider:model`. */
export const AUTO_CHOICE = '__auto__'

export const MAX_REVIEW_ROUNDS = 5

/** `provider:model`, or AUTO_CHOICE when the role has no pinned model. */
export function roleChoice(role: OrchestratorRoleModel | undefined): string {
  return role?.model ? `${role.provider}:${role.model}` : AUTO_CHOICE
}

/** Decode a select value. The model half may itself contain ':' (e.g.
 *  `openrouter:anthropic/claude-sonnet-4:beta`), so split on the first one. */
export function parseRoleChoice(choice: string): OrchestratorRoleModel {
  if (choice === AUTO_CHOICE) {
    return { provider: '', model: '' }
  }

  const at = choice.indexOf(':')

  return at < 0 ? { provider: '', model: choice } : { provider: choice.slice(0, at), model: choice.slice(at + 1) }
}

export function withRoleChoice(
  config: OrchestratorConfig,
  role: OrchestratorRoleId,
  choice: string
): OrchestratorConfig {
  return { ...config, roles: { ...config.roles, [role]: parseRoleChoice(choice) } }
}

export function withReviewRounds(config: OrchestratorConfig, rounds: number): OrchestratorConfig {
  const clamped = Math.max(0, Math.min(MAX_REVIEW_ROUNDS, Math.round(rounds)))

  return { ...config, max_review_rounds: clamped }
}

export function isBalanceMode(value: unknown): value is BalanceMode {
  return BALANCE_MODES.includes(value as BalanceMode)
}

export function balanceOf(config: OrchestratorConfig): BalanceMode {
  return isBalanceMode(config.auto_balance) ? config.auto_balance : DEFAULT_BALANCE
}

export function withBalance(config: OrchestratorConfig, balance: BalanceMode): OrchestratorConfig {
  return { ...config, auto_balance: balance }
}

/** The chat message that hands a task to the `orchestrate` tool. */
export function orchestratePrompt(task: string): string {
  return `Run this task through the orchestrator flow with the orchestrate tool, then summarize each stage's outcome for me:\n\n${task.trim()}`
}

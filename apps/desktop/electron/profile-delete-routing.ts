// Profile-delete routing logic for the `jettstui:api` IPC handler.
//
// When the renderer issues DELETE /api/profiles/<name>, the handler must
// tear down that profile's backend (primary window backend or pool backend)
// and then route the *next* request away from the just-deleted profile's
// pool backend -- spawning a fresh one would call ensure_jettstui_home() and
// recreate the profile directory the delete just removed, leaving a zombie
// process behind (issue #52279).
//
// These helpers are pure so they can be unit-tested without Electron.

/**
 * Parse a `jettstui:api` request into the profile name a DELETE targets, or
 * null when the request is not a profile-delete at all (wrong method, wrong
 * path, empty/invalid name).
 */
export function profileNameFromDeleteRequest(request) {
  if (!request || String(request.method || 'GET').toUpperCase() !== 'DELETE') {
    return null
  }

  const match = String(request.path || '').match(/^\/api\/profiles\/([^/?#]+)(?:[?#].*)?$/)

  if (!match) {
    return null
  }

  let raw = ''

  try {
    raw = decodeURIComponent(match[1])
  } catch {
    return null
  }

  const name = raw.trim()

  if (!name) {
    return null
  }

  if (name.toLowerCase() === 'default') {
    return 'default'
  }

  return name.toLowerCase()
}

/**
 * Parse a profile RENAME (PATCH /api/profiles/<name> with a `new_name` body)
 * into the profile being renamed, or null when the request is not a rename.
 *
 * A rename moves the profile directory. Its backend must be torn down first,
 * exactly like a delete: on Windows a directory with open handles (state.db,
 * logs) cannot be renamed at all ("[WinError 5] Access is denied"), and on
 * POSIX a backend left running would keep writing to the old path.
 */
export function profileNameFromRenameRequest(request) {
  if (!request || String(request.method || 'GET').toUpperCase() !== 'PATCH') {
    return null
  }

  const newName = request.body && typeof request.body === 'object' ? request.body.new_name : undefined

  if (typeof newName !== 'string' || !newName.trim()) {
    return null
  }

  return profileNameFromDeleteRequest({ ...request, method: 'DELETE' })
}

/** The profile a delete OR rename targets — both need its backend torn down. */
export function profileNameFromLifecycleRequest(request) {
  return profileNameFromDeleteRequest(request) ?? profileNameFromRenameRequest(request)
}

export type ProfileDeleteAction = 'noop' | 'teardown-primary' | 'teardown-pool'

export interface ProfileDeleteDecision {
  action: ProfileDeleteAction
  profile: string | null
}

export interface ProfileDeleteDecisionDeps {
  isDefaultProfile: (profile: string) => boolean
  isValidProfileName: (profile: string) => boolean
  primaryProfileKey: () => string
}

/**
 * Pure decision logic for prepareProfileDeleteRequest: given the parsed
 * profile name (or null), decide which side-effecting branch the caller
 * should take and what profile name it should ultimately report as
 * torn-down. No I/O, no async -- the caller performs the actual teardown
 * based on `action`.
 */
export function decideProfileDeleteAction(
  profile: string | null,
  deps: ProfileDeleteDecisionDeps
): ProfileDeleteDecision {
  if (!profile || deps.isDefaultProfile(profile) || !deps.isValidProfileName(profile)) {
    return { action: 'noop', profile: null }
  }

  if (profile === deps.primaryProfileKey()) {
    return { action: 'teardown-primary', profile }
  }

  return { action: 'teardown-pool', profile }
}

/**
 * Route the next `jettstui:api` request away from the primary/window backend
 * whenever a profile was just torn down -- otherwise ensureBackend would
 * spawn a fresh pool backend for the deleted profile, whose
 * ensure_jettstui_home() recreates the directory the delete just removed.
 */
export function resolveRouteProfile(
  tornDownProfile: string | null,
  profile: string | undefined
): string | null | undefined {
  return tornDownProfile ? null : profile
}

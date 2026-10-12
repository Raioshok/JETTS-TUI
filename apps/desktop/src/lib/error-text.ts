/**
 * The text a person should read for a failure.
 *
 * Backend REST calls cross Electron's IPC bridge, so a rejected call arrives as
 * `Error invoking remote method 'jettstui:api': Error: 400: {"detail":"…"}`.
 * Shown verbatim, that is plumbing, not a message. This strips the IPC
 * wrapper, the HTTP status prefix, and the FastAPI `{"detail": …}` envelope
 * (including validation-error lists), leaving the sentence the backend meant.
 *
 * Callers that branch on the raw shape (404 "route missing", 401/403 reauth)
 * keep reading `error.message`; this is for display only.
 */

const IPC_WRAPPER = /^Error invoking remote method '[^']+':\s*/
const ERROR_PREFIX = /^(?:Error:\s*)+/
const STATUS_PREFIX = /^(\d{3}):\s*([\s\S]*)$/

function detailFromBody(body: string): string | null {
  const trimmed = body.trim()

  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) {
    return null
  }

  try {
    const parsed: unknown = JSON.parse(trimmed)
    const envelope = parsed as { detail?: unknown; error?: unknown; message?: unknown }
    const detail = envelope?.detail ?? envelope?.error ?? envelope?.message

    if (typeof detail === 'string') {
      return detail
    }

    // FastAPI validation errors: [{ loc, msg, type }, …]
    if (Array.isArray(detail)) {
      const messages = detail
        .map(item => (typeof item === 'string' ? item : (item as { msg?: unknown })?.msg))
        .filter((msg): msg is string => typeof msg === 'string' && msg.length > 0)

      return messages.length ? messages.join('; ') : null
    }

    if (detail && typeof detail === 'object' && typeof (detail as { message?: unknown }).message === 'string') {
      return (detail as { message: string }).message
    }
  } catch {
    // Not JSON after all — fall through to the raw text.
  }

  return null
}

export function errorText(error: unknown, fallback = ''): string {
  const raw =
    error instanceof Error
      ? error.message
      : typeof error === 'string'
        ? error
        : error == null
          ? ''
          : fallback || String(error)

  let text = raw.trim().replace(IPC_WRAPPER, '').replace(ERROR_PREFIX, '').trim()
  const status = text.match(STATUS_PREFIX)

  if (status) {
    text = detailFromBody(status[2]) ?? (status[2].trim() || `HTTP ${status[1]}`)
  } else {
    text = detailFromBody(text) ?? text
  }

  return text.trim() || fallback
}

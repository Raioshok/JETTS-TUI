export function logError(error: unknown): void {
  if (!process.env.JETTSTUI_INK_DEBUG_ERRORS) {
    return
  }

  console.error(error)
}

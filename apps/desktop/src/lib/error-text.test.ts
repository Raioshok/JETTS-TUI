import { describe, expect, it } from 'vitest'

import { errorText } from './error-text'

describe('errorText', () => {
  it('unwraps an IPC-bridged REST error to the backend detail', () => {
    const err = new Error(
      `Error invoking remote method 'jettstui:api': Error: 400: {"detail":"Cannot create a profile named 'default' — it is the built-in profile."}`
    )

    expect(errorText(err)).toBe("Cannot create a profile named 'default' — it is the built-in profile.")
  })

  it('joins FastAPI validation errors', () => {
    const err = new Error(`422: {"detail":[{"loc":["body","name"],"msg":"field required"},{"msg":"too short"}]}`)

    expect(errorText(err)).toBe('field required; too short')
  })

  it('keeps plain messages, and a status-only body readable', () => {
    expect(errorText(new Error('Something broke'))).toBe('Something broke')
    expect(errorText(new Error('Error: 500: Internal Server Error'))).toBe('Internal Server Error')
    expect(errorText(new Error('503: '))).toBe('HTTP 503')
  })

  it('falls back for empty or non-error values', () => {
    expect(errorText(undefined, 'Failed')).toBe('Failed')
    expect(errorText(new Error(''), 'Failed')).toBe('Failed')
    expect(errorText('just text')).toBe('just text')
    expect(errorText({ weird: true }, 'Failed')).toBe('Failed')
  })
})

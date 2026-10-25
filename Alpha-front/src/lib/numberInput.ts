const WHITESPACE = /[\s\u00A0\u202F]/g
const NUMERIC = /^\d+(\.\d+)?$/

export function parseNumericInput(value: string): number | null {
  const normalized = value.replace(WHITESPACE, '')
  if (!NUMERIC.test(normalized)) {
    return null
  }
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

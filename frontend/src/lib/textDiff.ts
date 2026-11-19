export type DiffKind = 'same' | 'added' | 'removed'
export interface DiffPart { text: string; kind: DiffKind; numeric: boolean }

const NUMBER = /^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:년|월|일|시|분|초|원|명|건|회|번|개|주|개월|%|퍼센트)?$/u
const NUMBER_GLOBAL = /[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:년|월|일|시|분|초|원|명|건|회|번|개|주|개월|%|퍼센트)?/gu
const TOKENS = /[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:년|월|일|시|분|초|원|명|건|회|번|개|주|개월|%|퍼센트)?|\s+|[\p{L}\p{M}]+|[^\s]/gu

export function diffWords(original: string, simple: string) {
  if (original.length + simple.length > 20_000) {
    // shortcut: very long sentences keep shared numeric markers but skip word diff to bound browser memory.
    return { original: coarseParts(original, 'removed'), simple: coarseParts(simple, 'added') }
  }
  const left = original.match(TOKENS) ?? []
  const right = simple.match(TOKENS) ?? []
  const operations: { text: string; kind: DiffKind }[] = []

  if (left.length * right.length > 100_000) {
    // shortcut: very long sentence pairs use common prefix/suffix only; upgrade if production documents exceed this bound.
    let start = 0
    while (start < left.length && start < right.length && left[start] === right[start]) {
      operations.push({ text: left[start++], kind: 'same' })
    }
    let endLeft = left.length
    let endRight = right.length
    while (endLeft > start && endRight > start && left[endLeft - 1] === right[endRight - 1]) { endLeft--; endRight-- }
    operations.push(...left.slice(start, endLeft).map((text) => ({ text, kind: 'removed' as const })))
    operations.push(...right.slice(start, endRight).map((text) => ({ text, kind: 'added' as const })))
    for (let i = endLeft; i < left.length; i++) operations.push({ text: left[i], kind: 'same' })
  } else {
    const rows = Array.from({ length: left.length + 1 }, () => new Uint32Array(right.length + 1))
    for (let i = left.length - 1; i >= 0; i--) {
      for (let j = right.length - 1; j >= 0; j--) {
        rows[i][j] = left[i] === right[j] ? rows[i + 1][j + 1] + 1 : Math.max(rows[i + 1][j], rows[i][j + 1])
      }
    }
    let i = 0
    let j = 0
    while (i < left.length || j < right.length) {
      if (i < left.length && j < right.length && left[i] === right[j]) operations.push({ text: left[i++], kind: 'same' }), j++
      else if (i < left.length && (j === right.length || rows[i + 1][j] >= rows[i][j + 1])) operations.push({ text: left[i++], kind: 'removed' })
      else operations.push({ text: right[j++], kind: 'added' })
    }
  }

  const originalParts = parts(operations.filter((part) => part.kind !== 'added'))
  const simpleParts = parts(operations.filter((part) => part.kind !== 'removed'))
  return { original: originalParts, simple: simpleParts }
}

function coarseParts(text: string, kind: DiffKind) {
  const result: DiffPart[] = []
  let cursor = 0
  let count = 0
  for (const match of text.matchAll(NUMBER_GLOBAL)) {
    if (count++ >= 1000) break
    const index = match.index!
    if (index > cursor) result.push({ text: text.slice(cursor, index), kind, numeric: false })
    result.push({ text: match[0], kind, numeric: true })
    cursor = index + match[0].length
  }
  if (cursor < text.length) result.push({ text: text.slice(cursor), kind, numeric: false })
  return result.length ? result : [{ text, kind, numeric: false }]
}

function parts(operations: { text: string; kind: DiffKind }[]): DiffPart[] {
  return operations.reduce<DiffPart[]>((result, part) => {
    const numeric = NUMBER.test(part.text)
    const previous = result.at(-1)
    if (previous && previous.kind === part.kind && previous.numeric === numeric) previous.text += part.text
    else result.push({ ...part, numeric })
    return result
  }, [])
}

import { afterEach, describe, expect, it, vi } from 'vitest'
import { diffWords } from '@/lib/textDiff'
import { smoothHeight } from '@/lib/smoothHeight'

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('text differences', () => {
  it('handles empty input and uses bounded diffs for long sentences', () => {
    expect(diffWords('', '')).toEqual({ original: [], simple: [] })

    const coarse = diffWords('문장 2026년 '.repeat(1700), '쉬운 말 2026년 '.repeat(1700))
    expect(coarse.original.every((part) => part.kind === 'removed')).toBe(true)
    expect(coarse.original.some((part) => part.numeric)).toBe(true)

    const prefixSuffix = diffWords('가,'.repeat(600) + '끝', '나,'.repeat(600) + '끝')
    expect(prefixSuffix.original.at(-1)).toMatchObject({ text: ',끝', kind: 'same' })
    expect(prefixSuffix.simple.at(-1)).toMatchObject({ text: ',끝', kind: 'same' })
  })
})

describe('smooth height transition', () => {
  it('finishes immediately when reduced motion is preferred', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    const done = vi.fn()

    smoothHeight.onEnter(document.createElement('div'), done)

    expect(done).toHaveBeenCalledOnce()
  })

  it('animates height and clears styles when the animation finishes', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    vi.stubGlobal('getComputedStyle', vi.fn(() => ({ paddingTop: '2px', paddingBottom: '2px', marginTop: '1px', marginBottom: '1px' })))
    const animation = { cancel: vi.fn(), onfinish: null as null | (() => void), oncancel: null as null | (() => void) }
    const el = document.createElement('div')
    const animate = vi.fn(() => animation as unknown as Animation)
    Object.defineProperty(el, 'animate', { value: animate })
    const done = vi.fn()

    smoothHeight.onEnter(el, done)

    expect(el.style.overflow).toBe('hidden')
    expect(animate).toHaveBeenCalledOnce()
    animation.onfinish?.()
    expect(el.style.overflow).toBe('')
    expect(el.style.boxSizing).toBe('')
    expect(done).toHaveBeenCalledOnce()
    expect(animation.cancel).toHaveBeenCalledOnce()
  })
})

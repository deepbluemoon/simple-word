import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ApiError, sendFeedback, simplify } from '@/api/simpleWord'
import C5VerdictBadge from '@/components/common/C5VerdictBadge.vue'
import { findResult, readHistory, saveResult } from '@/stores/history'

let storage: { getItem: (key: string) => string | null; setItem: (key: string, value: string) => void; clear: () => void }
beforeEach(() => {
  const values = new Map<string, string>()
  storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => { values.set(key, value) }, clear: () => values.clear() }
  vi.stubGlobal('localStorage', storage)
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); storage.clear() })

describe('Simple Word API', () => {
  it('uploads the file as multipart form data', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ model_version: 'v1', sentences: [] })))
    const file = new File(['안내'], '안내.txt', { type: 'text/plain' })
    await simplify(file)
    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe('/simplify')
    expect((options?.body as FormData).get('file')).toBe(file)
  })

  it.each([[400, '파일을 확인해 주세요'], [429, '요청이 많아'], [500, '문장을 바꾸지 못했어요']])('translates %i responses to Korean', async (status, message) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status }))
    await expect(simplify(new File(['x'], 'x.txt'))).rejects.toMatchObject({ status, message: expect.stringContaining(message) })
  })

  it('posts sentence feedback with the server contract', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{"saved":true}'))
    await sendFeedback('v1', '원문', '쉬운 말', 'down')
    expect(fetch).toHaveBeenCalledWith('/feedback', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_version: 'v1', original: '원문', simple: '쉬운 말', vote: 'down' }),
    }))
  })
})

describe('result display and local history', () => {
  it('labels fallback sentences as 원문 유지', () => {
    const wrapper = mount(C5VerdictBadge, { props: { fallback: true } })
    expect(wrapper.text()).toContain('원문 유지')
  })

  it('keeps recent results in local storage and restores an individual result', () => {
    const result = { id: 'a1', filename: '안내.txt', model_version: 'v1', created_at: '2026-11-19T00:00:00Z', sentences: [{ original: '원문', simple: '쉬운 말', fallback: true }] }
    saveResult(result)
    expect(readHistory()).toEqual([result])
    expect(findResult('a1')).toEqual(result)
  })
})

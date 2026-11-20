import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ApiError, sendFeedback, simplify } from '@/api/simpleWord'
import C5VerdictBadge from '@/components/common/C5VerdictBadge.vue'
import C11ModelServerState from '@/components/common/C11ModelServerState.vue'
import S5FeedbackPanel from '@/views/S5FeedbackPanel.vue'
import S4Result from '@/views/S4Result.vue'
import { findResult, readHistory, saveResult } from '@/stores/history'
import { diffWords } from '@/lib/textDiff'
import { groupParagraphs, groupSentenceParagraphs, readReaderSize, saveReaderSize } from '@/lib/reader'

let storage: { getItem: (key: string) => string | null; setItem: (key: string, value: string) => void; clear: () => void }
beforeEach(() => {
  const values = new Map<string, string>()
  storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => { values.set(key, value) }, clear: () => values.clear() }
  vi.stubGlobal('localStorage', storage)
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); storage.clear() })

describe('Simple Word API', () => {
  it('uploads the file as multipart form data', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ model_version: 'v1', sentences: [] })))
    const file = new File(['안내'], '안내.txt', { type: 'text/plain' })
    await simplify(file)
    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe('/simplify')
    expect((options?.body as FormData).get('file')).toBe(file)
  })

  it.each([[400, '파일을 읽지 못했어요'], [429, '요청이 많아'], [500, '문장을 바꾸지 못했어요']])('translates %i responses to Korean', async (status, message) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status }))
    await expect(simplify(new File(['x'], 'x.txt'))).rejects.toMatchObject({ status, message: expect.stringContaining(message) })
  })

  it('explains the 100-sentence limit in Korean', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Document exceeds 100-sentence limit' }), { status: 400 }))
    await expect(simplify(new File(['x'], 'x.txt'))).rejects.toMatchObject({ message: expect.stringContaining('100문장') })
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

  it('automatically retries a busy response after Retry-After', async () => {
    vi.useFakeTimers()
    const fetch = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{}', { status: 429, headers: { 'Retry-After': '1' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ model_version: 'v1', sentences: [] })))
    const countdown = vi.fn()
    const pending = simplify(new File(['내용'], '안내.txt'), countdown)
    await vi.advanceTimersByTimeAsync(0)
    expect(countdown).toHaveBeenCalledWith(1)
    await vi.advanceTimersByTimeAsync(1000)
    await expect(pending).resolves.toMatchObject({ model_version: 'v1' })
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(countdown).toHaveBeenLastCalledWith(0)
    vi.useRealTimers()
  })
})

describe('result display and local history', () => {
  it('labels fallback sentences as 원문 유지', () => {
    const wrapper = mount(C5VerdictBadge, { props: { fallback: true } })
    expect(wrapper.text()).toContain('원문 유지')
    expect(wrapper.attributes('data-fallback')).toBe('true')
  })

  it('describes model health in text and marks delayed service accessibly', () => {
    const wrapper = mount(C11ModelServerState, { props: { status: null, slow: true } })
    expect(wrapper.text()).toContain('응답이 지연되고 있어요')
    expect(wrapper.get('.status').attributes('aria-live')).toBe('polite')
  })

  it('shows feedback confirmation as a persistent live status after voting', async () => {
    vi.spyOn(await import('@/api/simpleWord'), 'sendFeedback').mockResolvedValue(undefined)
    const wrapper = mount(S5FeedbackPanel, { props: { modelVersion: 'v1', original: '원문', simple: '쉬운 말' } })
    await wrapper.get('button').trigger('click')
    expect(wrapper.get('[role="status"]').text()).toBe('의견 감사합니다.')
    expect(wrapper.get('button').attributes('aria-pressed')).toBe('true')
  })

  it('keeps recent results in local storage and restores an individual result', () => {
    const result = { id: 'a1', filename: '안내.txt', model_version: 'v1', created_at: '2026-11-19T00:00:00Z', sentences: [{ original: '원문', simple: '쉬운 말', fallback: true }] }
    saveResult(result)
    expect(readHistory()).toEqual([result])
    expect(findResult('a1')).toEqual(result)
  })

  it('diffs changed words and marks identical numeric dates on both sides', () => {
    const diff = diffWords('신청은 2026년 12월 31일까지 제출해야 합니다.', '2026년 12월 31일까지 신청하세요.')
    expect(diff.original.some((part) => part.kind === 'removed' && part.text.includes('제출해야'))).toBe(true)
    expect(diff.simple.some((part) => part.kind === 'added' && part.text.includes('신청하세요'))).toBe(true)
    expect(diff.original.filter((part) => part.numeric).map((part) => part.text)).toEqual(['2026년', '12월', '31일'])
    expect(diff.simple.filter((part) => part.numeric).map((part) => part.text)).toEqual(['2026년', '12월', '31일'])
  })

  it('groups easy sentences by paragraph and stores the three-step reader size', () => {
    const sentences = [
      { original: 'A', simple: '가', fallback: false, paragraph: 0 },
      { original: 'B', simple: '나', fallback: true, paragraph_id: 0 },
      { original: 'C', simple: '다', fallback: false, paragraph: 1, paragraph_id: 1 },
    ]
    expect(groupParagraphs(sentences)).toEqual(['가 B', '다'])
    expect(groupSentenceParagraphs(sentences).map((paragraph) => paragraph.length)).toEqual([2, 1])
    saveReaderSize('large')
    expect(readReaderSize()).toBe('large')
  })

  it('opens the continuous document first and reveals selected sentence notes by keyboard', async () => {
    saveResult({
      id: 'doc-view', filename: '안내.txt', model_version: 'v1', created_at: '2026-11-19T00:00:00Z',
      sentences: [
        { original: '신청서를 제출해야 합니다.', simple: '신청서를 내야 합니다.', fallback: false, paragraph: 0 },
        { original: '수수료는 400원입니다.', simple: '수수료는 400원입니다.', fallback: true, fallback_reason: 'numbers', paragraph: 1 },
      ],
    })
    const wrapper = mount(S4Result, { props: { id: 'doc-view' }, global: { stubs: { C1Rail: true, RouterLink: true } } })
    expect(wrapper.get('[role="tab"][aria-selected="true"]').text()).toBe('문서 보기')
    expect(wrapper.get('.document-paragraph').text()).toContain('신청서를 바뀐 부분: 내야 합니다.')
    expect(wrapper.get('.document-sentence mark').text()).toContain('바뀐 부분: 내야')
    await wrapper.findAll('.document-sentence')[1].trigger('keydown.enter')
    expect(wrapper.get('.clause-note').text()).toContain('숫자나 날짜를 안전하게 지키려고 원문을 유지했어요.')
  })
})

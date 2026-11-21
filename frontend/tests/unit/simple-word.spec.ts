import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ApiError, sendFeedback, simplify } from '@/api/simpleWord'
import C5VerdictBadge from '@/components/common/C5VerdictBadge.vue'
import C11ModelServerState from '@/components/common/C11ModelServerState.vue'
import S5FeedbackPanel from '@/views/S5FeedbackPanel.vue'
import S4Result from '@/views/S4Result.vue'
import SampleFilesMotion from '@/components/common/SampleFilesMotion.vue'
import { getFeedbackVote, saveFeedbackVote } from '@/stores/feedbackVotes'
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

  it.each([[408, '파일을 처리하는 데 시간이 오래 걸렸어요'], [413, '파일은 5MB 이하여야 해요'], [415, 'PDF 파일은 지원하지 않아요'], [503, '서비스가 잠시 바빠요']])('explains upload failure %i', async (status, message) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('<html>proxy error</html>', { status }))
    await expect(simplify(new File(['x'], 'x.pdf'))).rejects.toMatchObject({ status, message: expect.stringContaining(message) })
  })

  it('explains the 100-sentence limit in Korean', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Document exceeds 100-sentence limit' }), { status: 400 }))
    await expect(simplify(new File(['x'], 'x.txt'))).rejects.toMatchObject({ message: expect.stringContaining('100문장') })
  })

  it('posts sentence feedback with the server contract', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{"saved":true}'))
    await sendFeedback('request-1', 'result-1', 2, 'v1', '원문', '쉬운 말', 'down')
    expect(fetch).toHaveBeenCalledWith('/feedback', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id: 'request-1', result_id: 'result-1', sentence_index: 2, model_version: 'v1', original: '원문', simple: '쉬운 말', vote: 'down' }),
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

  it('loads each sample with its document extension and MIME type', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(new ArrayBuffer(4)))
    const wrapper = mount(SampleFilesMotion)
    const buttons = wrapper.findAll('.sfm-use')
    expect(wrapper.findAll('.sfm-kind').map((badge) => badge.text())).toEqual(['TXT', 'DOCX', 'HWPX'])
    expect(buttons.map((button) => button.get('.sfm-use-kind').text())).toEqual(['TXT', 'DOCX', 'HWPX'])
    for (const button of buttons) await button.trigger('click')
    await flushPromises()
    const selected = wrapper.emitted('select')!.map(([file]) => file as File)
    expect(selected.map(({ name, type }) => [name, type])).toEqual([
      ['주민 안내문 예시.txt', 'text/plain'],
      ['지원 신청서 예시.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
      ['시설 이용 안내 예시.hwpx', 'application/vnd.hancom.hwpx'],
    ])
  })

  it('labels preserved title lines without treating them as model fallback', async () => {
    saveResult({
      id: 'title-result', filename: '안내.txt', model_version: 'v1', created_at: '2026-11-19T00:00:00Z',
      sentences: [
        { original: '제목: 안내', simple: '제목: 안내', fallback: false, title: true, paragraph_id: 0 },
        { original: '신청서를 제출합니다.', simple: '신청서를 내요.', fallback: false, title: false, paragraph_id: 1 },
      ],
    })
    const wrapper = mount(S4Result, { props: { id: 'title-result' }, global: { stubs: { C1Rail: true, RouterLink: true } } })
    expect(wrapper.findAll('.document-sentence')[0].text()).toContain('제목·원문 유지')
    await wrapper.get('#sentences-tab').trigger('click')
    expect(wrapper.findAll('.verdict')[0].text()).toBe('제목·원문 유지')
    expect(wrapper.get('.compare blockquote[aria-label="원문 문장"]').text()).toBe('제목: 안내')
  })

  it('describes model health in text and marks delayed service accessibly', () => {
    const wrapper = mount(C11ModelServerState, { props: { status: null, slow: true } })
    expect(wrapper.text()).toContain('응답이 지연되고 있어요')
    expect(wrapper.get('.status').attributes('aria-live')).toBe('polite')
  })

  it('lets the user change a vote and announces the update once', async () => {
    const send = vi.spyOn(await import('@/api/simpleWord'), 'sendFeedback').mockResolvedValue(undefined)
    const props = { requestId: 'request-feedback', resultId: 'feedback-test', sentenceIndex: 1, modelVersion: 'v1', original: '원문', simple: '쉬운 말' }
    const wrapper = mount(S5FeedbackPanel, { props })
    await wrapper.get('button').trigger('click')
    expect(send).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[role="status"]').text()).toBe('의견이 저장됐어요.')
    expect(wrapper.get('button').attributes('aria-pressed')).toBe('true')
    expect(getFeedbackVote(props.resultId, props.sentenceIndex)).toBe('up')
    expect(wrapper.get('[role="status"]').attributes('aria-live')).toBeUndefined()
    await wrapper.get('button').trigger('click')
    expect(send).toHaveBeenCalledTimes(1)
    await wrapper.findAll('button')[1].trigger('click')
    expect(send).toHaveBeenCalledTimes(2)
    expect(send).toHaveBeenLastCalledWith('request-feedback', 'feedback-test', 1, 'v1', '원문', '쉬운 말', 'down')
    expect(wrapper.get('[role="status"]').text()).toBe('의견을 변경했어요.')
    expect(getFeedbackVote(props.resultId, props.sentenceIndex)).toBe('down')
    const remounted = mount(S5FeedbackPanel, { props })
    expect(remounted.findAll('button')[1].attributes('aria-pressed')).toBe('true')
    expect(remounted.findAll('button')[0].attributes('disabled')).toBeUndefined()
  })

  it('keeps recent results in local storage and restores an individual result', () => {
    const result = { id: 'a1', filename: '안내.txt', model_version: 'v1', created_at: '2026-11-19T00:00:00Z', sentences: [{ original: '원문', simple: '쉬운 말', fallback: true }] }
    saveResult(result)
    expect(readHistory()).toEqual([result])
    expect(findResult('a1')).toEqual(result)
  })

  it('prunes votes for results that fell out of recent history', () => {
    for (let i = 0; i < 11; i++) {
      saveResult({ id: `history-${i}`, filename: '안내.txt', model_version: 'v1', created_at: '2026-11-19T00:00:00Z', sentences: [] })
      saveFeedbackVote(`history-${i}`, 0, 'up')
    }
    expect(readHistory()).toHaveLength(10)
    expect(getFeedbackVote('history-0', 0)).toBeNull()
    expect(getFeedbackVote('history-1', 0)).toBe('up')
  })

  it('does not prune votes when history is read after a failed save', () => {
    storage.setItem = () => { throw new Error('storage full') }
    const result = { id: 'memory-result', filename: '안내.txt', model_version: 'v1', created_at: '2026-11-19T00:00:00Z', sentences: [] }
    saveResult(result)
    saveFeedbackVote(result.id, 0, 'up')
    expect(readHistory()).toEqual([])
    expect(findResult(result.id)).toEqual(result)
    expect(getFeedbackVote(result.id, 0)).toBe('up')
  })

  it('diffs changed words and marks identical numeric dates on both sides', () => {
    const diff = diffWords('신청은 2026년 12월 31일까지 제출해야 합니다.', '2026년 12월 31일까지 신청하세요.')
    expect(diff.original.some((part) => part.kind === 'removed' && part.text.includes('제출해야'))).toBe(true)
    expect(diff.simple.some((part) => part.kind === 'added' && part.text.includes('신청하세요'))).toBe(true)
    expect(diff.original.filter((part) => part.numeric).map((part) => part.text)).toEqual(['2026년', '12월', '31일'])
    expect(diff.simple.filter((part) => part.numeric).map((part) => part.text)).toEqual(['2026년', '12월', '31일'])
  })

  it('does not mark or diff identical long text', () => {
    const text = '같은 내용 '.repeat(4_001)
    const diff = diffWords(text, text)
    expect(diff.original).toEqual([{ text, kind: 'same', numeric: false }])
    expect(diff.simple).toEqual(diff.original)
    expect(diffWords('2025년 기준', '2025년 기준').original[0].numeric).toBe(true)
  })

  it('groups easy sentences by paragraph and stores the three-step reader size', () => {
    const sentences = [
      { original: 'A', simple: '가', fallback: false, paragraph_id: 0 },
      { original: 'B', simple: '나', fallback: true, paragraph_id: 0 },
      { original: 'C', simple: '다', fallback: false, paragraph_id: 1 },
    ]
    expect(groupParagraphs(sentences)).toEqual(['가 B', '다'])
    expect(groupSentenceParagraphs(sentences).map((paragraph) => paragraph.length)).toEqual([2, 1])
    saveReaderSize('large')
    expect(readReaderSize()).toBe('large')
  })

  it('opens the easy document, annotates original terms, and keeps keyboard tabs accessible', async () => {
    saveResult({
      id: 'doc-view', request_id: 'request-doc-view', term_licenses: { 국립국어원_15130006: '국립국어원 공공언어 평가용 용어 목록 · 공공누리 제1유형', 법제처_법령정보지식베이스: '법제처 법령용어-일상용어 연계 · 이용허락범위 제한 없음' }, filename: '안내.txt', model_version: 'v1', created_at: '2026-11-19T00:00:00Z',
      sentences: [
        { original: '익일 신청서를 제출해야 합니다.', simple: '다음 날 신청서를 내야 합니다.', fallback: false, paragraph_id: 0, terms: [{ text: '익일', start: 0, end: 2, easy: ['다음 날'], source: '국립국어원_15130006' }] },
        { original: '스마트 그리드가 좋아요.', simple: '스마트 안내가 좋아요.', fallback: false, paragraph_id: 1, terms: [{ text: '스마트 그리드', start: 0, end: 7, easy: ['지능형 전력망'], source: 'law' }] },
        { original: '수수료는 400원입니다.', simple: '수수료는 400원으로 산정합니다.', fallback: true, fallback_reason: 'numbers', paragraph_id: 2 },
      ],
    })
    const wrapper = mount(S4Result, { props: { id: 'doc-view' }, global: { stubs: { C1Rail: true, RouterLink: true } } })
    expect(wrapper.get('[role="tab"][aria-selected="true"]').text()).toBe('쉬운 말로 읽기')
    expect(wrapper.find('#simple-panel .document-sentence').text()).toContain('신청서를')
    expect(wrapper.findAll('#simple-panel .document-paragraph')[2].text()).toContain('수수료는 400원입니다.')
    await wrapper.find('#sentences-tab').trigger('click')
    expect(wrapper.get('.comparison-summary').text()).toContain('2 / 3개 문장에서 말이 바뀌었어요')
    await wrapper.find('#original-tab').trigger('click')
    expect(wrapper.get('.term-ruby rt').text()).toBe('뜻: 다음 날')
    expect(wrapper.findAll('.term-ruby')).toHaveLength(2)
    expect(wrapper.get('.term-ruby mark > span[aria-hidden="true"]').text()).toBe('익일')
    expect(wrapper.findAll('.term-ruby mark > span[aria-hidden="true"]')[1].text()).toBe('스마트 그리드')
    expect(wrapper.findAll('#original-panel .document-sentence')[0].text()).toContain('제출해야')
    await wrapper.get('.term-ruby').trigger('click')
    expect(wrapper.get('.clause-note').text()).toContain('국립국어원 공공언어 평가용 용어 목록 · 공공누리 제1유형')
    expect(wrapper.get('.document-legend').text()).toContain('법제처 법령용어-일상용어 연계 · 이용허락범위 제한 없음')
    expect(wrapper.get('.clause-note').text()).toContain('다음 날 신청서를 내야 합니다.')
    await wrapper.find('#simple-tab').trigger('click')
    expect(wrapper.findAll('.term-choice[aria-pressed="true"]')).toHaveLength(0)
    await wrapper.find('#original-tab').trigger('click')
    expect(wrapper.findAll('.term-choice[aria-pressed="true"]')).toHaveLength(0)
    expect(wrapper.find('.document-sentence').element.tagName).toBe('SPAN')
    expect(wrapper.find('.document-sentence').attributes('role')).toBe('button')
    expect(wrapper.find('.document-sentence').attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('.term-ruby').attributes('tabindex')).toBeUndefined()
    await wrapper.findAll('.document-sentence')[2].trigger('keydown.enter')
    expect(wrapper.get('.clause-note').text()).toContain('숫자나 날짜를 안전하게 지키려고 원문을 유지했어요.')
    await wrapper.find('#original-tab').trigger('keydown', { key: 'Home' })
    expect(wrapper.get('[role="tab"][aria-selected="true"]').text()).toBe('쉬운 말로 읽기')
    await wrapper.find('#simple-tab').trigger('keydown', { key: 'End' })
    expect(wrapper.get('[role="tab"][aria-selected="true"]').text()).toBe('문장별 보기')
    await wrapper.find('#sentences-tab').trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.get('[role="tab"][aria-selected="true"]').text()).toBe('쉬운 말로 읽기')
    await wrapper.find('#simple-tab').trigger('keydown', { key: 'ArrowLeft' })
    expect(wrapper.get('[role="tab"][aria-selected="true"]').text()).toBe('문장별 보기')
  })
})

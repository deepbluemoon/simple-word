import { expect, test } from '@playwright/test'

test('nginx CSP allows the built Vue app and its styles', async ({ page }) => {
  await page.addInitScript(() => {
    window.addEventListener('securitypolicyviolation', (event) => {
      const root = document.documentElement
      const previous = root.getAttribute('data-csp-violations') ?? ''
      root.setAttribute('data-csp-violations', `${previous}${event.violatedDirective}:${event.blockedURI};`)
    })
  })
  let finishRequest!: () => void
  const pendingResponse = new Promise<void>((resolve) => { finishRequest = resolve })
  await page.route('**/simplify', async (route) => {
    await pendingResponse
    await route.fulfill({ json: { model_version: 'e2e', sentences: [{ original: '안내 문장입니다.', simple: '안내 문장입니다.', fallback: false, paragraph_id: 0 }] } })
  })
  const response = await page.goto('/')
  const policy = response?.headers()['content-security-policy'] ?? ''
  expect(policy).toContain("default-src 'self'")
  expect(policy).toContain("style-src 'self'")
  await page.getByRole('button', { name: '글 붙여넣기' }).click()
  await page.getByRole('textbox', { name: '쉬운 말로 바꿀 공문서 내용' }).fill('안내 문장입니다.')
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('progressbar', { name: '문서 처리 진행률' })).toBeVisible()
  finishRequest()
  await expect(page.getByRole('heading', { name: '쉬운 말로 바꾼 결과' })).toBeVisible()
  await expect(page.getByText('쉬운 말은 이해를 돕기 위한 것이며, 정확한 내용은 원문이 기준입니다.')).toBeVisible()
  expect(await page.locator('html').getAttribute('data-csp-violations')).toBeNull()
})

test('uploads a public document, sends sentence feedback, and restores the result after reload', async ({ page }) => {
  const firstSentence = '거버넌스 신청 안내 내용을 확인해 주세요, 필요한 서류를 빠짐없이 준비하고 접수 창구에 제출한 뒤 담당자의 확인을 기다려 주시기 바랍니다, 접수 결과는 등록한 연락처로 안내해 드립니다.'
  const source = `${firstSentence}\n\n수수료는 400원입니다.`
  await page.setViewportSize({ width: 400, height: 800 })
  await page.goto('/')
  await page.locator('input[type=file]').setInputFiles({
    name: '주민 안내문.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from(source),
  })
  await expect(page.getByText('주민 안내문.txt')).toBeVisible()
  const simplifyResponse = page.waitForResponse((response) => new URL(response.url()).pathname === '/simplify' && response.request().method() === 'POST')
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  const actual = await (await simplifyResponse).json()
  expect(actual.sentences.map((sentence: { original: string }) => sentence.original)).toEqual([firstSentence, '수수료는 400원입니다.'])
  expect(actual.sentences.map((sentence: { paragraph_id: number }) => sentence.paragraph_id)).toEqual([0, 1])
  expect(actual.sentences[0]).toEqual(expect.objectContaining({ simple: expect.any(String), fallback: expect.any(Boolean) }))
  expect(actual.sentences[0].terms).toEqual(expect.arrayContaining([expect.objectContaining({ text: '거버넌스', easy: expect.arrayContaining(['협치']) })]))
  await expect(page.getByRole('heading', { name: '쉬운 말로 바꾼 결과' })).toBeVisible()
  await expect(page.getByText('쉬운 말은 이해를 돕기 위한 것이며, 정확한 내용은 원문이 기준입니다.')).toBeVisible()
  await expect(page.getByRole('navigation', { name: '진행 단계' })).toContainText('문장 나누기 완료')
  await expect(page.getByRole('tab', { name: '쉬운 말로 읽기' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('#simple-panel .document-paragraph')).toHaveCount(2)
  const longSentence = page.locator('.document-sentence').first()
  expect(await longSentence.evaluate((element) => element.tagName)).toBe('SPAN')
  expect(await longSentence.evaluate((element) => element.getClientRects().length)).toBeGreaterThan(1)
  expect(await longSentence.getAttribute('role')).toBeNull()
  await page.getByRole('tab', { name: '문장별 보기' }).click()
  const expectedChanged = actual.sentences.filter((sentence: { original: string; simple: string; fallback: boolean }) => (sentence.fallback ? sentence.original : sentence.simple) !== sentence.original).length
  await expect(page.locator('#sentences-panel .comparison-summary')).toContainText(`${expectedChanged} / ${actual.sentences.length}개 문장에서 말이 바뀌었어요`)
  await page.getByRole('tab', { name: '원문 보기' }).click()
  await expect(page.locator('.term-ruby rt').first()).toContainText('협치')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.locator('.term-ruby').first().click()
  await expect(page.locator('.clause-note')).toContainText(actual.sentences[0].original)
  await expect(page.locator('.clause-note')).toContainText(actual.sentences[0].fallback ? actual.sentences[0].original : actual.sentences[0].simple)
  await expect(page.locator('.clause-note')).toContainText('국립국어원 공공언어 평가용 용어 목록 · 공공누리 제1유형')
  const feedbackResponse = page.waitForResponse((response) => new URL(response.url()).pathname === '/feedback' && response.request().method() === 'POST')
  await page.getByRole('button', { name: /좋아요/ }).first().click()
  expect((await feedbackResponse).status()).toBe(200)
  await expect(page.getByText('의견이 저장됐어요.')).toBeVisible()
  const changedVote = page.waitForResponse((response) => new URL(response.url()).pathname === '/feedback' && response.request().method() === 'POST')
  await page.getByRole('button', { name: /아쉬워요/ }).first().click()
  expect((await changedVote).status()).toBe(200)
  await expect(page.getByText('의견을 변경했어요.')).toBeVisible()
  expect(Object.values(await page.evaluate(() => JSON.parse(localStorage.getItem('simple-word.feedback-votes') ?? '{}')))).toEqual(['down'])
  const resultUrl = page.url()
  await page.reload()
  expect(page.url()).toBe(resultUrl)
  await expect(page.getByRole('heading', { name: '쉬운 말로 바꾼 결과' })).toBeVisible()
  await expect(page.getByText('주민 안내문.txt')).toBeVisible()
})

test('keeps a conservative title unchanged while simplifying the body', async ({ page }) => {
  await page.route('**/simplify', (route) => route.fulfill({ json: {
    model_version: 'e2e',
    sentences: [
      { original: '제목: 신청 안내', simple: '제목: 신청 안내', fallback: false, title: true, paragraph_id: 0 },
      { original: '신청서를 제출하세요.', simple: '신청서를 내세요.', fallback: false, title: false, paragraph_id: 1 },
    ],
  } }))
  await page.goto('/')
  await page.locator('input[type=file]').setInputFiles({
    name: '안내.txt', mimeType: 'text/plain', buffer: Buffer.from('제목: 신청 안내\n\n신청서를 제출하세요.'),
  })
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByText('제목·원문 유지')).toBeVisible()
  await expect(page.locator('.document-sentence').first()).toContainText('제목: 신청 안내')
  await expect(page.locator('.document-sentence').last()).toContainText('내세요.')
  await page.getByRole('tab', { name: '문장별 보기' }).click()
  await expect(page.locator('.verdict').first()).toHaveText('제목·원문 유지')
})

test('accepts pasted text and keeps reading controls usable at 400px', async ({ page }) => {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.setViewportSize({ width: 400, height: 800 })
  await page.goto('/')
  await page.getByRole('button', { name: '글 붙여넣기' }).click()
  await page.getByRole('textbox', { name: '쉬운 말로 바꿀 공문서 내용' }).fill('첫 문장은 2026년 12월 31일까지 신청해야 합니다.\n\n다음 안내는 400원입니다.')
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('heading', { name: '쉬운 말로 바꾼 결과' })).toBeVisible()
  await page.getByRole('button', { name: '쉬운 말 복사' }).click()
  await expect(page.getByRole('status').filter({ hasText: '쉬운 말을 복사했어요.' })).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('첫 문장은')
  const [easyDownload] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: '쉬운 말 .txt', exact: true }).click()])
  expect(easyDownload.suggestedFilename()).toBe('붙여넣은 공문서-쉬운말.txt')
  const [comparisonDownload] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: '원문·쉬운 말 .txt' }).click()])
  expect(comparisonDownload.suggestedFilename()).toBe('붙여넣은 공문서-원문-쉬운말.txt')
  await page.getByRole('tab', { name: '문장별 보기' }).click()
  await expect(page.locator('#sentences-panel .sentence-card')).toHaveCount(2)
  await page.getByRole('button', { name: '글자 크게' }).click()
  await expect(page.getByRole('button', { name: '글자 크게' })).toHaveAttribute('aria-pressed', 'true')
  await page.reload()
  await expect(page.getByRole('button', { name: '글자 크게' })).toHaveAttribute('aria-pressed', 'true')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('shows a retry countdown after 429 and retries successfully', async ({ page }) => {
  let attempts = 0
  await page.route('**/simplify', async (route) => {
    attempts++
    if (attempts === 1) {
      await route.fulfill({ status: 429, headers: { 'Retry-After': '3' }, body: 'busy' })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ model_version: 'dummy', sentences: [{ original: '신청 안내입니다.', simple: '신청 안내입니다.', fallback: false }] }),
    })
  })
  await page.goto('/')
  await page.locator('input[type=file]').setInputFiles({
    name: '안내.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('신청 안내입니다.'),
  })
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('status').filter({ hasText: '3초 뒤 자동으로 다시 시도해요.' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '쉬운 말로 바꾼 결과' })).toBeVisible({ timeout: 10_000 })
  expect(attempts).toBe(2)
})

test('explains the 5 MB file limit', async ({ page }) => {
  await page.goto('/')
  await page.locator('input[type=file]').setInputFiles({
    name: '큰 안내.txt',
    mimeType: 'text/plain',
    buffer: Buffer.alloc(5 * 1024 * 1024 + 1, 65),
  })
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('alert')).toHaveText('파일은 5MB 이하여야 해요.')
})

test('rejects PDF and explains supported file types', async ({ page }) => {
  await page.goto('/')
  const input = page.locator('input[type=file]')
  await expect(input).toHaveAttribute('accept', '.txt,.docx,.hwpx')
  await expect(page.getByText('TXT · DOCX · HWPX 파일을 올릴 수 있어요.')).toBeVisible()
  await input.setInputFiles({
    name: '안내.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF not processed'),
  })
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('alert')).toHaveText('PDF 파일은 지원하지 않아요. TXT, DOCX, HWPX 파일을 올려 주세요.')
})

test('explains the 100-sentence limit', async ({ page }) => {
  const sentences = Array.from({ length: 101 }, (_, index) => `안내 문장 ${index + 1}입니다.`).join('\n')
  await page.goto('/')
  await page.getByRole('button', { name: '글 붙여넣기' }).click()
  await page.getByRole('textbox', { name: '쉬운 말로 바꿀 공문서 내용' }).fill(sentences)
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('alert')).toHaveText('공문서는 한 번에 100문장까지 바꿀 수 있어요. 파일을 나눠서 올려 주세요.')
})

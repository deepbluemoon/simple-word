import { expect, test } from '@playwright/test'

test('uploads a public document, sends sentence feedback, and restores the result after reload', async ({ page }) => {
  await page.goto('/')
  await page.locator('input[type=file]').setInputFiles({
    name: '주민 안내문.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('신청은 2026년 12월 31일까지 해야 합니다.\n수수료는 400원입니다.'),
  })
  await expect(page.getByText('주민 안내문.txt')).toBeVisible()
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('heading', { name: '쉬운 말로 바꾼 결과' })).toBeVisible()
  await expect(page.getByText('신청은 2026년 12월 31일까지 해야 합니다.').first()).toBeVisible()
  await page.getByRole('button', { name: /좋아요/ }).first().click()
  await expect(page.getByText('의견을 보냈어요.')).toBeVisible()
  const resultUrl = page.url()
  await page.reload()
  expect(page.url()).toBe(resultUrl)
  await expect(page.getByRole('heading', { name: '쉬운 말로 바꾼 결과' })).toBeVisible()
  await expect(page.getByText('주민 안내문.txt')).toBeVisible()
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
  await page.getByRole('button', { name: '쉬운 말만 보기' }).click()
  await expect(page.getByLabel('쉬운 말 이어 읽기').locator('article')).toHaveCount(2)
  await page.getByRole('button', { name: '글자 크게' }).click()
  await expect(page.getByRole('button', { name: '글자 크게' })).toHaveAttribute('aria-pressed', 'true')
  await page.reload()
  await expect(page.getByRole('button', { name: '글자 크게' })).toHaveAttribute('aria-pressed', 'true')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

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

export interface SentenceResult {
  original: string
  simple: string
  fallback: boolean
  fallback_reason?: 'numbers' | 'preserve' | 'length' | null
  paragraph_id?: number
}

export interface AnalysisResult {
  id: string
  filename: string
  model_version: string
  created_at: string
  sentences: SentenceResult[]
}

export class ApiError extends Error {
  constructor(readonly status: number, message: string, readonly retryAfterSec = 0) { super(message) }
}

export async function simplify(
  file: File,
  onRetryCountdown?: (seconds: number) => void,
): Promise<Omit<AnalysisResult, 'id' | 'filename' | 'created_at'>> {
  let response = await upload(file)
  if (response.status === 429) {
    const seconds = retryAfterSeconds(response)
    for (let remaining = seconds; remaining > 0; remaining--) {
      onRetryCountdown?.(remaining)
      await new Promise((resolve) => setTimeout(resolve, 1000))
    }
    onRetryCountdown?.(0)
    response = await upload(file)
  }
  if (!response.ok) throw new ApiError(response.status, await responseMessage(response), retryAfterSeconds(response))
  return response.json() as Promise<Omit<AnalysisResult, 'id' | 'filename' | 'created_at'>>
}

function upload(file: File) {
  const body = new FormData()
  body.append('file', file)
  return fetch('/simplify', { method: 'POST', body })
}

export async function sendFeedback(model_version: string, original: string, simple: string, vote: 'up' | 'down') {
  const response = await fetch('/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_version, original, simple, vote }),
  })
  if (!response.ok) throw new ApiError(response.status, await responseMessage(response))
}

export async function loadHealth(): Promise<{ model_versions: { version: string; roles: string[] }[] }> {
  const response = await fetch('/health')
  if (!response.ok) throw new ApiError(response.status, '상태를 확인하지 못했어요.')
  return response.json()
}

async function responseMessage(response: Response): Promise<string> {
  if (response.status === 400) {
    const body = await response.clone().json().catch(() => ({})) as { detail?: string }
    const detail = body.detail ?? ''
    if (/sentence limit/i.test(detail)) return '공문서는 한 번에 100문장까지 바꿀 수 있어요. 파일을 나눠서 올려 주세요.'
    if (/5\s*MB/i.test(detail)) return '파일은 5MB 이하여야 해요.'
    if (/empty/i.test(detail)) return '내용이 비어 있는 파일이에요. 내용을 넣어 다시 올려 주세요.'
    if (/supported files/i.test(detail)) return 'TXT, DOCX, HWPX, PDF 파일만 올릴 수 있어요.'
    return '파일을 읽지 못했어요. 파일 형식과 내용을 확인해 주세요.'
  }
  if (response.status === 429) return '요청이 많아 잠시 기다리고 있어요. 조금 뒤 다시 시도해 주세요.'
  if (response.status === 500) return '문장을 바꾸지 못했어요. 잠시 뒤 다시 시도해 주세요.'
  return '요청을 처리하지 못했어요. 잠시 뒤 다시 시도해 주세요.'
}

function retryAfterSeconds(response: Response) {
  const value = Number(response.headers.get('Retry-After'))
  return Number.isFinite(value) && value > 0 ? Math.min(30, Math.ceil(value)) : 1
}

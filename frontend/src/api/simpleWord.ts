export interface SentenceResult {
  original: string
  simple: string
  fallback: boolean
}

export interface AnalysisResult {
  id: string
  filename: string
  model_version: string
  created_at: string
  sentences: SentenceResult[]
}

export class ApiError extends Error {
  constructor(readonly status: number, message: string) { super(message) }
}

export async function simplify(file: File): Promise<Omit<AnalysisResult, 'id' | 'filename' | 'created_at'>> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch('/simplify', { method: 'POST', body })
  if (!response.ok) throw new ApiError(response.status, await responseMessage(response))
  return response.json() as Promise<Omit<AnalysisResult, 'id' | 'filename' | 'created_at'>>
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
  if (response.status === 400) return '파일을 확인해 주세요. 지원 형식은 TXT, DOCX, HWPX, PDF이며 비어 있거나 너무 큰 파일은 올릴 수 없어요.'
  if (response.status === 429) return '요청이 많아 잠시 기다리고 있어요. 조금 뒤 다시 시도해 주세요.'
  if (response.status === 500) return '문장을 바꾸지 못했어요. 잠시 뒤 다시 시도해 주세요.'
  return '요청을 처리하지 못했어요. 잠시 뒤 다시 시도해 주세요.'
}

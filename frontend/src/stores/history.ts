import type { AnalysisResult } from '@/api/simpleWord'
import { pruneFeedbackVotes } from '@/stores/feedbackVotes'

const KEY = 'simple-word.recent-results'
const LIMIT = 10
const recent = new Map<string, AnalysisResult>()

export function readHistory(): AnalysisResult[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    const history = Array.isArray(value) ? value.filter(isResult) : []
    pruneFeedbackVotes(history.map((item) => item.id))
    return history
  } catch { return [] }
}

export function saveResult(result: AnalysisResult) {
  recent.set(result.id, result)
  try {
    const history = [result, ...readHistory().filter((item) => item.id !== result.id)].slice(0, LIMIT)
    localStorage.setItem(KEY, JSON.stringify(history))
    pruneFeedbackVotes(history.map((item) => item.id))
  }
  catch { /* 저장 공간이 없으면 현재 결과는 서버 응답으로 계속 보여 준다. */ }
}

export function findResult(id: string) { return recent.get(id) ?? readHistory().find((item) => item.id === id) ?? null }

function isResult(value: unknown): value is AnalysisResult {
  if (!value || typeof value !== 'object') return false
  const item = value as Partial<AnalysisResult>
  return typeof item.id === 'string' && typeof item.filename === 'string' && typeof item.model_version === 'string'
    && typeof item.created_at === 'string' && Array.isArray(item.sentences)
    && item.sentences.every((sentence) => sentence && typeof sentence.original === 'string' && typeof sentence.simple === 'string' && typeof sentence.fallback === 'boolean')
}

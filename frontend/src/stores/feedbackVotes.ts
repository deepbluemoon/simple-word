import { reactive } from 'vue'

type Vote = 'up' | 'down'
const KEY = 'simple-word.feedback-votes'
const votes = reactive<Record<string, Vote>>({})
let loaded = false

function loadVotes() {
  if (loaded) return
  loaded = true
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(KEY) ?? '{}')
    if (!stored || typeof stored !== 'object' || Array.isArray(stored)) return
    for (const [key, value] of Object.entries(stored)) {
      if (value === 'up' || value === 'down') votes[key] = value
    }
  } catch { /* storage can be disabled or contain invalid JSON */ }
}

function voteKey(resultId: string, sentenceIndex: number) { return `${resultId}:${sentenceIndex}` }

export function getFeedbackVote(resultId: string, sentenceIndex: number): Vote | null {
  loadVotes()
  return votes[voteKey(resultId, sentenceIndex)] ?? null
}

export function saveFeedbackVote(resultId: string, sentenceIndex: number, vote: Vote) {
  loadVotes()
  votes[voteKey(resultId, sentenceIndex)] = vote
  try { localStorage.setItem(KEY, JSON.stringify(votes)) } catch { /* in-memory vote still applies this session */ }
}

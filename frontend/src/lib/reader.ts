import type { SentenceResult } from '@/api/simpleWord'

export type ReaderSize = 'small' | 'medium' | 'large'
const SIZE_KEY = 'simple-word.reader-size'

export function readReaderSize(): ReaderSize {
  try {
    const size = localStorage.getItem(SIZE_KEY)
    return size === 'small' || size === 'large' ? size : 'medium'
  } catch { return 'medium' }
}

export function saveReaderSize(size: ReaderSize) {
  try { localStorage.setItem(SIZE_KEY, size) } catch { /* storage may be disabled */ }
}

export function groupParagraphs(sentences: SentenceResult[]) {
  return groupSentenceParagraphs(sentences).map((paragraph) =>
    paragraph.map((sentence) => sentence.fallback ? sentence.original : sentence.simple).join(' '),
  )
}

export function groupSentenceParagraphs(sentences: SentenceResult[]) {
  const paragraphs: SentenceResult[][] = []
  let currentId: number | undefined
  for (const sentence of sentences) {
    const id = sentence.paragraph_id ?? 0
    if (id !== currentId) { paragraphs.push([]); currentId = id }
    paragraphs.at(-1)!.push(sentence)
  }
  return paragraphs
}

export const samples = [
  { id: 'notice', extension: 'txt', mime: 'text/plain', file: '주민 안내문 예시.txt', name: '주민 안내문', count: '3문장', kind: 'TXT' },
  { id: 'application', extension: 'docx', mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', file: '지원 신청서 예시.docx', name: '지원 신청서 안내', count: '3문장', kind: 'DOCX' },
  { id: 'facility', extension: 'hwpx', mime: 'application/vnd.hancom.hwpx', file: '시설 이용 안내 예시.hwpx', name: '시설 이용 안내', count: '3문장', kind: 'HWPX' },
] as const

export async function loadSample(sample: typeof samples[number]) {
  const response = await fetch(`/samples/${sample.id}.${sample.extension}`)
  if (!response.ok) throw new Error('Sample file could not be loaded')
  return new File([await response.arrayBuffer()], sample.file, { type: sample.mime })
}

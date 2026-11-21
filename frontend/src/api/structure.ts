import { useMutation } from '@tanstack/react-query'
import { post } from './client.ts'

type Tag<Value> = {
  value: Value
  confidence: number
  probabilities: Record<string, number>
}

export type StructureCard = {
  title: string
  summary: string
  problem: string
  solution: string
  results: string
  kind: string | null
  stage: string | null
  domains: string[]
  support_needs: string[]
  keywords: string[]
}

export type StructureResult = {
  card: StructureCard
  tags: {
    kind: Tag<string | null>
    stage: Tag<string | null>
    domains: Tag<string[]>
    support_needs: Tag<string[]>
  }
  is_innovation: number
  missing: (keyof StructureCard)[]
  questions: string[]
  engine: { tags: string; text: string }
}

export function useStructureText() {
  return useMutation({ mutationFn: (text: string) => post<StructureResult>('/structure', { text }) })
}

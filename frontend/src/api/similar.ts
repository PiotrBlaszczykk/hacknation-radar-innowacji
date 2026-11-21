import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from './client.ts'
import type { Innovation } from './types.ts'

export const noveltyMinLength = 30

export const relationLabel = {
  to_samo: 'Rozwiązuje ten sam problem w ten sam sposób',
  ten_sam_problem: 'Rozwiązuje ten sam problem inaczej',
  podobna_metoda: 'Stosuje podobną metodę do innego problemu',
  niepowiazane: 'Brak wspólnego problemu lub metody',
}

type Relation = keyof typeof relationLabel

export type SimilarInnovation = {
  innovation: Innovation
  similarity: number
  relation: Relation | null
  probabilities: Partial<Record<Relation, number>>
  overlap: number
  shared: { domains: string[]; keywords: string[] }
  same_organization: boolean
}

export type NoveltyResult = {
  novelty: number
  verdict: string
  nearest: SimilarInnovation[]
  compared: number
  engine: string
}

export function labelForRelation(relation: SimilarInnovation['relation']) {
  return relation ? relationLabel[relation] : 'Ma zbliżony opis'
}

export function comparedLabel(count: number) {
  return count === 1
    ? 'Porównano z 1 rozwiązaniem w radarze.'
    : `Porównano z ${count} rozwiązaniami w radarze.`
}

function checkIdea(text: string, signal?: AbortSignal) {
  return api<NoveltyResult>('/novelty', {
    method: 'POST',
    body: JSON.stringify({ text }),
    signal,
  })
}

export function useCheckIdea() {
  return useMutation({ mutationFn: (text: string) => checkIdea(text) })
}

export function useSimilarHints(text: string) {
  return useQuery({
    queryKey: ['novelty', text],
    queryFn: ({ signal }) => checkIdea(text, signal),
    enabled: text.trim().length >= noveltyMinLength,
    retry: false,
    staleTime: 60_000,
    gcTime: 60_000,
  })
}

export function useSimilar(id: number, limit = 5) {
  return useQuery({
    queryKey: ['similar', id, limit],
    queryFn: ({ signal }) => api<NoveltyResult>(`/innovations/${id}/similar?limit=${limit}`, { signal }),
    retry: false,
    staleTime: 60_000,
  })
}

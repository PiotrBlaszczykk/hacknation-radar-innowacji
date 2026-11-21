import { useQuery } from '@tanstack/react-query'
import { api } from './client.ts'
import type { Need } from './matching.ts'

export type CoverageStatus = 'fits' | 'partial' | 'no_solution' | 'insufficient_data'

type Review = {
  need_id: number
  status: CoverageStatus
  reason: string
  conditions: { requirement: string; status: 'supported' | 'missing' | 'unverified' }[]
  decisions: Record<string, { engine: string; confidence: number }>
}

export type Opportunity = {
  id: number
  title: string
  description: string | null
  status: CoverageStatus
  incomplete: boolean
  organization_count: number
  sources: Need[]
  alternatives: {
    id: number
    title: string
    source_url: string | null
    excerpt: string
    status: CoverageStatus
    reviews: Review[]
  }[]
}

export function useOpportunities() {
  return useQuery({
    queryKey: ['opportunities'],
    staleTime: 0,
    queryFn: () => api<{
      items: Opportunity[]
      incomplete: boolean
      missing_need_embeddings: number
      missing_card_embeddings: number
    }>('/opportunities'),
  })
}

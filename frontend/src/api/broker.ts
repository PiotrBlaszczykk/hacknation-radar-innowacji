import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api, patch } from './client.ts'
import type { Innovation, InnovationFull, Organization } from './types.ts'

type Counts = Record<string, number>
type BrokerList<T> = { items: T[]; total: number }

type BrokerSummary = {
  innovations: {
    total: number
    by_origin: Counts
    by_kind: Counts
    by_status: Counts
    radar_claimed: number
  }
  assessments: { total: number; average_score: number | null; low_confidence: number }
  paths: { total: number; by_path: Counts }
  matches: { by_status: Counts; innovations_with_contact: number; radar_innovations_matched: number }
  median_days: { to_assessment: number | null; to_contact: number | null }
  organizations: { total: number; by_kind: Counts }
}

export type BrokerCard = Pick<Innovation, 'id' | 'title' | 'origin' | 'claimed' | 'status' | 'score'> & {
  organization: Pick<Organization, 'id' | 'name'> | null
  needs_review: boolean
  has_path: boolean
  matches_count: number
  interest_count: number
}

export type BrokerColumn = { status: string; total: number; items: BrokerCard[] }

export type QueueItem = {
  innovation_id: number
  title: string
  type: 'low_confidence' | 'path_approval' | 'match_interest' | 'unclaimed_profile'
  description: string
  match_id: number | null
}

type DuplicateInnovation = Pick<Innovation, 'id' | 'title' | 'organization'>
type DuplicatePair = {
  left: DuplicateInnovation
  right: DuplicateInnovation
  relation: 'to_samo' | 'ten_sam_problem'
}

export const useBrokerSummary = () =>
  useQuery({ queryKey: ['broker', 'summary'], queryFn: () => api<BrokerSummary>('/broker/summary'), staleTime: 0 })

export const useBrokerBoard = () =>
  useQuery({
    queryKey: ['broker', 'board'],
    queryFn: () => api<{ columns: BrokerColumn[] }>('/broker/board'),
    staleTime: 0,
  })

export const useBrokerQueue = () =>
  useQuery({
    queryKey: ['broker', 'queue'],
    queryFn: () => api<BrokerList<QueueItem>>('/broker/queue'),
    staleTime: 0,
  })

export function useBrokerDuplicates() {
  return useQuery({
    queryKey: ['broker', 'duplicates'],
    queryFn: async () => {
      try {
        return await api<BrokerList<DuplicatePair>>('/duplicates?limit=20')
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
  })
}

export function useMoveInnovation() {
  const client = useQueryClient()

  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      patch<InnovationFull>(`/innovations/${id}`, { status }),
    onSuccess: async (innovation) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['broker'], predicate: (query) => query.queryKey[1] !== 'duplicates' }),
        client.invalidateQueries({ queryKey: ['innovation', innovation.id] }),
        client.invalidateQueries({ queryKey: ['innovations'] }),
      ])
    },
  })
}

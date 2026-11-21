import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, patch, post, query } from './client.ts'
import type { Innovation, Organization, Page } from './types.ts'

export type NeedInput = {
  title: string
  description: string
  domains: string[]
  offers: string[]
}

export type Need = Omit<NeedInput, 'description'> & {
  id: number
  description: string | null
  status: 'otwarte' | 'zamkniete'
  organization: Organization
  author: { id: number; name: string } | null
  created_at: string
}

export type MatchRole = 'uzytkownik' | 'partner' | 'inwestor'
export type MatchDecision = 'zainteresowanie' | 'kontakt' | 'odrzucone'

export type Match = {
  id: number
  innovation_id: number
  need: Need | null
  organization: Organization | null
  role: MatchRole
  score: number
  reason: string
  status: MatchDecision | 'proponowane'
  factors: {
    similarity: number | null
    domains: number
    offers: number | null
    stage: number
    shared_domains: string[]
    shared_offers: string[]
    innovation_stage: string | null
  }
}

type MatchList<T = Match> = { items: T[]; total: number }

export function matchStrength(score: number) {
  if (score >= 0.55) return 'Silne dopasowanie'
  if (score >= 0.45) return 'Dobre dopasowanie'
  return 'Możliwe dopasowanie'
}

export function useNeeds(offset: number) {
  return useQuery({
    queryKey: ['needs', offset],
    queryFn: () => api<Page<Need>>(`/needs${query({ offset })}`),
  })
}

export function useNeedMatches(id: number) {
  return useQuery({
    queryKey: ['matches', 'need', id],
    queryFn: () => api<MatchList<Match & { innovation: Innovation }>>(`/needs/${id}/matches`),
  })
}

export function useCreateNeed() {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: (input: NeedInput) => post<Need>('/needs', input),
    onSuccess: async () => {
      await Promise.all([
        cache.invalidateQueries({ queryKey: ['needs'] }),
        cache.invalidateQueries({ queryKey: ['matches'] }),
      ])
    },
  })
}

export function useInnovationMatches(id: number) {
  return useQuery({
    queryKey: ['matches', 'innovation', id],
    queryFn: () => api<MatchList>(`/innovations/${id}/matches`),
  })
}

export function useRefreshMatches(id: number) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: () => post<MatchList>(`/innovations/${id}/matches/refresh`, {}),
    onSuccess: (matches) => {
      cache.setQueryData(['matches', 'innovation', id], matches)
      return cache.invalidateQueries({ queryKey: ['matches', 'need'] })
    },
  })
}

export function useMatchDecision() {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: MatchDecision }) =>
      patch<Match>(`/matches/${id}`, { status }),
    onSuccess: async (match) => {
      await Promise.all([
        cache.invalidateQueries({ queryKey: ['matches'] }),
        cache.invalidateQueries({ queryKey: ['innovation', match.innovation_id] }),
        cache.invalidateQueries({ queryKey: ['innovations'] }),
        cache.invalidateQueries({ queryKey: ['feed'] }),
        cache.invalidateQueries({ queryKey: ['broker', 'board'] }),
        cache.invalidateQueries({ queryKey: ['broker', 'summary'] }),
      ])
    },
  })
}

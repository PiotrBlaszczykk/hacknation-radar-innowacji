import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, query } from './client.ts'
import type { Innovation, Page, User } from './types.ts'

export const MAX_ABOUT = 2000
export type FeedTab = 'dla_ciebie' | 'perelki' | 'popularne' | 'najnowsze' | 'obserwowani'
export type FeedFilters = Partial<Record<'kind' | 'stage' | 'domain' | 'origin', string>>
export type Engagement = { network_activity?: { type: 'podbicie' | 'komentarz' | 'serce'; name: string }; bumps: number; bumped: boolean; interest_count: number; comments_count: number; likes: number; liked: boolean; comments: {name: string; body: string}[]; repost_by: string | null; follows_author: boolean; follows_org: boolean }
export type FeedItem = Innovation & Engagement & { why: string }
type FeedPage = Page<FeedItem> & { message?: string; notice?: string }
type Explanation = { sections: { title: string; lines: string[] }[] }
type ProfileInput = Partial<Pick<User, 'about' | 'interests'>>

const PAGE_SIZE = 8

const personaHeaders = (id: number | null) => ({ 'X-User-Id': String(id ?? '') })

export function useFeed(personaId: number | null, tab: FeedTab, q: string, filters: FeedFilters) {
  return useInfiniteQuery({
    queryKey: ['feed', personaId, tab, q, filters],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => api<FeedPage>(
      `/feed${query({ tab, q, ...filters, offset: pageParam, limit: PAGE_SIZE })}`,
      { signal, headers: personaHeaders(personaId) },
    ),
    getNextPageParam: (lastPage) => {
      const next = lastPage.offset + lastPage.limit
      return next < lastPage.total ? next : undefined
    },
  })
}

export function useFeedExplain(enabled: boolean) {
  return useQuery({
    queryKey: ['feed-explain'],
    queryFn: () => api<Explanation>('/feed/explain'),
    enabled,
    staleTime: Infinity,
  })
}

export function useToggleBump(id: number, personaId: number | null) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api<Pick<Engagement, 'bumps' | 'bumped'>>(`/innovations/${id}/bump`, {
      method: 'POST',
      headers: personaHeaders(personaId),
    }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['feed'] }),
  })
}

export function useMe(personaId: number | null) {
  return useQuery({
    queryKey: ['me', personaId],
    queryFn: ({ signal }) => api<User>('/me', { signal, headers: personaHeaders(personaId) }),
    enabled: personaId !== null,
  })
}

export function useSaveProfile() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ personaId, input }: { personaId: number; input: ProfileInput }) => api<User>('/me', {
      method: 'PATCH',
      headers: personaHeaders(personaId),
      body: JSON.stringify(input),
    }),
    onSuccess: async (profile) => {
      client.setQueryData(['me', profile.id], profile)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['feed', profile.id] }),
        client.invalidateQueries({ queryKey: ['users'] }),
      ])
    },
  })
}

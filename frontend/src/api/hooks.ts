import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, post, query } from './client.ts'
import type { Innovation, InnovationFull, InnovationInput, Meta, Page, User } from './types.ts'

export function useMeta() {
  return useQuery({ queryKey: ['meta'], queryFn: () => api<Meta>('/meta'), staleTime: Infinity })
}

/** Zamienia klucz słownikowy na etykietę, np. label('stages', 'pilotaz') → „Pilotaż”. */
export function useLabel() {
  const { data } = useMeta()
  return (dict: keyof Meta, key: string | null | undefined): string => {
    if (!key) return ''
    return data?.[dict].find((option) => option.key === key)?.label ?? key
  }
}

export function useUsers() {
  return useQuery({ queryKey: ['users'], queryFn: () => api<{ items: User[] }>('/users'), staleTime: Infinity })
}

export type InnovationFilters = {
  q?: string
  kind?: string
  stage?: string
  status?: string
  origin?: string
  domain?: string
  limit?: number
  offset?: number
}

export function useInnovations(filters: InnovationFilters = {}) {
  return useQuery({
    queryKey: ['innovations', filters],
    queryFn: () => api<Page<Innovation>>(`/innovations${query(filters)}`),
  })
}

export function useInnovation(id: number, personaId: number | null) {
  return useQuery({
    queryKey: ['innovation', id, personaId],
    queryFn: () => api<InnovationFull>(`/innovations/${id}`, { headers: { 'X-User-Id': String(personaId ?? '') } }),
    enabled: Number.isFinite(id),
  })
}

export function useCreateInnovation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: InnovationInput) => post<InnovationFull>('/innovations', input),
    onSuccess: () => client.invalidateQueries({ queryKey: ['innovations'] }),
  })
}

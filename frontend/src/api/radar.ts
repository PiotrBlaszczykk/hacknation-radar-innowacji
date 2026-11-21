import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, post } from './client.ts'

type Counts = {
  fetched: number
  created: number
  skipped: number
  missing_embeddings: number
}

type RadarRun = Counts & {
  created_items: { id: number; title: string }[]
}

type LastRun = {
  finished_at: string
} & ({ status: 'success' } & Counts | { status: 'error'; error: string })

export type RadarSource = {
  name: string
  title: string
  description: string
  url: string | null
  terms: string
  terms_url: string | null
  status: 'aktywne' | 'planowane'
  count: number
  rules: string[]
  last_run: LastRun | null
}

const sourcesKey = ['radar', 'sources']

export function useRadarSources() {
  return useQuery({
    queryKey: sourcesKey,
    queryFn: () => api<{ items: RadarSource[] }>('/radar/sources'),
  })
}

export function useRunRadar(source: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => post<RadarRun>('/radar/run', { source, limit: 20 }),
    onSuccess: async (result) => {
      if (result.created) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ['innovations'] }),
          queryClient.invalidateQueries({ queryKey: ['feed'] }),
        ])
      }
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: sourcesKey }),
  })
}

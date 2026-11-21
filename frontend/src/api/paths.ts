import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, post } from './client.ts'

type Reason = {
  type: 'rule' | 'model' | 'broker'
  path: string
  message: string
  points?: number
  probabilities?: Record<string, number>
  engine?: string
}

type Step = {
  title: string
  description: string
  instrument: string | null
  url: string | null
  verified?: boolean
}

export type Recommendation = {
  id: number
  path: string
  rationale: string | null
  reasons: Reason[]
  alternative: { path: string; reason: string } | null
  steps: Step[]
  metrics: { name: string; target: string }[]
  approval: { actor_id: number | null; actor: string; created_at: string } | null
}

const recommendationUrl = (id: number) => `/innovations/${id}/recommendation`
const recommendationKey = (id: number) => ['recommendation', id]

export function useRecommendation(id: number) {
  return useQuery({
    queryKey: recommendationKey(id),
    queryFn: async () => {
      try {
        return await api<Recommendation>(recommendationUrl(id))
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
  })
}

export function usePathActions(id: number) {
  const client = useQueryClient()
  const onSuccess = (recommendation: Recommendation) => {
    client.setQueryData(recommendationKey(id), recommendation)
    void client.invalidateQueries({ queryKey: ['innovation', id] })
    void client.invalidateQueries({ queryKey: ['innovations'] })
    void client.invalidateQueries({ queryKey: ['broker'] })
  }
  const generate = useMutation({
    mutationFn: () => post<Recommendation>(`/innovations/${id}/recommend`, {}),
    onSuccess,
  })
  const accept = useMutation({
    mutationFn: (path: string) => post<Recommendation>(`${recommendationUrl(id)}/accept`, { path }),
    onSuccess,
  })
  return { generate, accept }
}

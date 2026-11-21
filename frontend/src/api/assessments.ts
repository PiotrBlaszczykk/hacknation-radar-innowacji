import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, post } from './client.ts'

type Criterion = {
  key: string
  label: string
  weight: number
  question: string
  checks: { key: string; text: string; points: number }[]
  missing_question: string
}

type Criteria = { version: string; min_rank_weight: number; criteria: Criterion[] }

export type AssessmentItem = {
  key: string
  label: string
  weight: number
  score: number
  confidence: number | null
  justification: string
  evidence: string | null
  probabilities: Record<string, number>
  missing: boolean
  question: string | null
  checks?: (Criterion["checks"][number] & { status: "confirmed" | "denied" | "unknown" })[]
  override?: { user_id: number; user_name: string; at: string }
}

type Assessment = {
  id: number
  criteria_version: string
  engine: string
  calibrated: boolean | null
  total: number
  confidence: number | null
  items: AssessmentItem[]
  review_threshold: number
  scored_weight: number
  has_score: boolean
  ranked: boolean
  needs_review: boolean
}

type Override = { key: string; score: number; justification: string }

export function useCriteria() {
  return useQuery({ queryKey: ['criteria'], queryFn: () => api<Criteria>('/criteria') })
}

export function useAssessment(id: number) {
  return useQuery({
    queryKey: ['assessment', id],
    queryFn: async () => {
      try {
        return await api<Assessment>(`/innovations/${id}/assessment`)
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
  })
}

export function useSaveAssessment(id: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (override?: Override) => override
      ? post<Assessment>(`/innovations/${id}/assessment/override`, override)
      : post<Assessment>(`/innovations/${id}/assess`, {}),
    onSuccess: (assessment) => {
      client.setQueryData<Assessment>(['assessment', id], (current) =>
        current && current.id > assessment.id ? current : assessment,
      )
      void client.invalidateQueries({ queryKey: ['assessment', id] })
      void client.invalidateQueries({ queryKey: ['innovation', id] })
      void client.invalidateQueries({ queryKey: ['innovations'] })
      void client.invalidateQueries({ queryKey: ['feed'] })
      void client.invalidateQueries({ queryKey: ['broker'] })
    },
  })
}

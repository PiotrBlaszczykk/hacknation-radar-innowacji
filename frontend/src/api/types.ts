// Typy odpowiadają `to_dict()` w backend/app/models.

export type Option = { key: string; label: string }

export type Meta = {
  innovation_kinds: Option[]
  stages: Option[]
  org_kinds: Option[]
  domains: Option[]
  support_needs: Option[]
  origins: Option[]
  statuses: Option[]
  paths: Option[]
  user_roles: Option[]
  match_statuses: Option[]
}

export type Organization = {
  id: number
  name: string
  kind: string
  region: string | null
  city: string | null
  description: string | null
  website: string | null
  interests: string[]
}

export type User = {
  id: number
  name: string
  role: string
  title: string | null
  about: string | null
  interests: string[]
  organization: Organization | null
}

export type InnovationEvent = {
  id: number
  type: string
  message: string | null
  payload: Record<string, unknown>
  actor: string
  created_at: string
}

export type Innovation = {
  id: number
  title: string
  summary: string | null
  kind: string | null
  stage: string | null
  domains: string[]
  support_needs: string[]
  keywords: string[]
  origin: string
  source_name: string | null
  source_url: string | null
  claimed: boolean
  status: string
  score: number | null
  path: string | null
  novelty: number | null
  organization: Organization | null
  author: { id: number; name: string; title: string | null } | null
  created_at: string
}

export type InnovationFull = Innovation & {
  description: string | null
  problem: string | null
  solution: string | null
  results: string | null
  structured_by: string | null
  events: InnovationEvent[]
}

export type InnovationInput = Partial<
  Pick<
    InnovationFull,
    'title' | 'summary' | 'description' | 'problem' | 'solution' | 'results' | 'kind' | 'stage' | 'domains' | 'support_needs' | 'keywords' | 'structured_by'
  >
>

export type Page<T> = { items: T[]; total: number; limit: number; offset: number }

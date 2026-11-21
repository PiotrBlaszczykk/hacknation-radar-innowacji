import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client.ts'
import type { Innovation, InnovationFull, Organization, User } from './types.ts'

type ToggleType = 'obserwuje' | 'zainteresowany'
type MessageType = 'komentarz' | 'kontakt'
type InteractionType = ToggleType | MessageType
type InteractionInput = { type: ToggleType } | { type: MessageType; body: string }

export type SocialMessage = {
  id: number
  type: MessageType
  body: string
  user: User
  created_at: string
}

type Interactions = {
  counts: Record<InteractionType, number>
  mine: InteractionType[]
  comments: SocialMessage[]
  contact_requests: SocialMessage[]
  can_read_contacts: boolean
}

type OrganizationNeed = {
  id: number
  title: string
  description: string | null
  status: string
  domains: string[]
  offers: string[]
}

type OrganizationProfile = Organization & {
  innovations: Innovation[]
  needs: OrganizationNeed[]
  people_count: number
  stats: {
    innovation_count: number
    assessed_count: number
    average_score: number | null
    in_contact_or_implementing_count: number
  }
}

export const maxSocialMessageLength = 1000

const personaHeaders = (personaId: number | null) => ({ 'X-User-Id': String(personaId ?? '') })
const interactionsPath = (id: number) => `/innovations/${id}/interactions`

export function useInteractions(id: number, personaId: number | null) {
  return useQuery({
    queryKey: ['interactions', id, personaId],
    queryFn: () => api<Interactions>(interactionsPath(id), { headers: personaHeaders(personaId) }),
  })
}

export function useCreateInteraction(id: number, personaId: number | null) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: InteractionInput) =>
      api<{ type: InteractionType; active: boolean }>(interactionsPath(id), {
        method: 'POST',
        headers: personaHeaders(personaId),
        body: JSON.stringify(input),
      }),
    onSuccess: async (_, input) => {
      const updates = [
        client.invalidateQueries({ queryKey: ['interactions', id] }),
        client.invalidateQueries({ queryKey: ['activity'] }),
      ]
      if (input.type === 'zainteresowany' || input.type === 'kontakt') {
        updates.push(client.invalidateQueries({ queryKey: ['innovation', id] }))
      }
      if (input.type === 'zainteresowany' || input.type === 'komentarz') {
        updates.push(client.invalidateQueries({ queryKey: ['feed'] }))
      }
      await Promise.all(updates)
    },
  })
}

export function useClaimInnovation(id: number, personaId: number | null) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api<InnovationFull>(`/innovations/${id}/claim`, { method: 'POST', headers: personaHeaders(personaId) }),
    onSuccess: async () => {
      await Promise.all(
        [['innovation', id], ['innovations'], ['organization'], ['feed'], ['activity']].map((queryKey) =>
          client.invalidateQueries({ queryKey }),
        ),
      )
    },
  })
}

export function useOrganization(id: number) {
  return useQuery({
    queryKey: ['organization', id],
    queryFn: () => api<OrganizationProfile>(`/organizations/${id}`),
    enabled: Number.isSafeInteger(id) && id > 0,
  })
}

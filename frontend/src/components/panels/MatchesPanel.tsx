import { Link } from 'react-router-dom'
import { useLabel } from '../../api/hooks.ts'
import { matchStrength, useInnovationMatches, useMatchDecision, useRefreshMatches } from '../../api/matching.ts'
import type { Match, MatchRole } from '../../api/matching.ts'
import type { InnovationFull } from '../../api/types.ts'
import { usePersona } from '../../lib/persona.tsx'
import { Badge, Button, Card, ErrorNote, Loading } from '../ui.tsx'

const roles: { key: MatchRole; label: string }[] = [
  { key: 'uzytkownik', label: 'Użytkownicy' },
  { key: 'partner', label: 'Partnerzy' },
  { key: 'inwestor', label: 'Inwestorzy' },
]

function MatchCard({ match }: { match: Match }) {
  const { persona } = usePersona()
  const label = useLabel()
  const decision = useMatchDecision()
  const { factors, organization } = match
  const broker = persona?.role === 'broker'
  const canExpressInterest = organization && persona?.organization?.id === organization.id
    && match.status === 'proponowane'
  const similarity = factors.similarity
  const similarityLabel = similarity === null ? 'Porównanie niedostępne'
    : similarity >= 0.35 ? 'Wyraźna zbieżność'
    : similarity >= 0.15 ? 'Częściowa zbieżność' : 'Mała zbieżność'
  const stageLabel = factors.stage >= 0.75 ? 'Sprzyja współpracy'
    : factors.stage > 0 ? 'Częściowo pasuje' : 'Brak dopasowania etapu'

  return (
    <li className="space-y-3 rounded-lg border border-slate-200 p-4">
      <div className="flex flex-wrap items-center gap-2">
        {organization ? (
          <Link to={`/organizacje/${organization.id}`} className="font-medium text-brand-700 hover:underline">
            {organization.name}
          </Link>
        ) : <span className="font-medium">Organizacja</span>}
        <Badge tone="brand">{matchStrength(match.score)}</Badge>
        <Badge tone={match.status === 'kontakt' ? 'green' : match.status === 'odrzucone' ? 'red' : 'slate'}>
          {label('match_statuses', match.status)}
        </Badge>
      </div>
      {match.need && <p className="text-sm text-slate-600">Zapotrzebowanie „{match.need.title}”</p>}
      <p className="text-sm text-slate-800">{match.reason}</p>
      <dl className="grid gap-x-4 gap-y-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-600 sm:grid-cols-2">
        {match.need && (
          <div>
            <dt className="font-semibold text-slate-700">Zgodność opisów</dt>
            <dd>{similarityLabel}</dd>
          </div>
        )}
        <div>
          <dt className="font-semibold text-slate-700">Wspólne obszary</dt>
          <dd>{factors.shared_domains.map((key) => label('domains', key)).join(', ') || 'Brak wspólnych obszarów'}</dd>
        </div>
        {match.need && (
          <div>
            <dt className="font-semibold text-slate-700">Wsparcie dla twórców</dt>
            <dd>{factors.shared_offers.map((key) => label('support_needs', key)).join(', ') || 'Brak wspólnych form wsparcia'}</dd>
          </div>
        )}
        <div>
          <dt className="font-semibold text-slate-700">Etap innowacji</dt>
          <dd>{factors.innovation_stage ? `${label('stages', factors.innovation_stage)} · ${stageLabel}` : 'Nie określono etapu'}</dd>
        </div>
      </dl>
      {(canExpressInterest || broker) && (
        <div className="flex flex-wrap gap-2">
          {canExpressInterest && (
            <Button disabled={decision.isPending} onClick={() => decision.mutate({ id: match.id, status: 'zainteresowanie' })}>
              Jestem zainteresowany
            </Button>
          )}
          {broker && match.status !== 'kontakt' && (
            <Button disabled={decision.isPending} onClick={() => decision.mutate({ id: match.id, status: 'kontakt' })}>
              Połącz strony
            </Button>
          )}
          {broker && match.status !== 'odrzucone' && (
            <Button variant="secondary" disabled={decision.isPending}
              onClick={() => decision.mutate({ id: match.id, status: 'odrzucone' })}>
              Nie pasuje
            </Button>
          )}
        </div>
      )}
      {decision.isError && <ErrorNote error={decision.error} />}
    </li>
  )
}

export default function MatchesPanel({ innovation }: { innovation: InnovationFull }) {
  const matches = useInnovationMatches(innovation.id)
  const refresh = useRefreshMatches(innovation.id)
  const items = matches.data?.items ?? []

  return (
    <Card className="space-y-4 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="technical-label">Dla kogo to może być</h2>
        <Button variant="secondary" disabled={matches.isPending || refresh.isPending} onClick={() => refresh.mutate()}>
          {refresh.isPending ? 'Przeliczanie…' : 'Przelicz dopasowania'}
        </Button>
      </div>
      {matches.isPending && <Loading />}
      {matches.isError && <ErrorNote error={matches.error} />}
      {refresh.isError && <ErrorNote error={refresh.error} />}
      {matches.isSuccess && !items.length && <p className="text-sm text-slate-600">Brak pasujących organizacji.</p>}
      {roles.map(({ key, label }) => {
        const group = items.filter((match) => match.role === key)
        return group.length > 0 && (
          <section key={key} className="space-y-2">
            <h3 className="text-sm font-semibold text-slate-800">{label}</h3>
            <ul className="space-y-2">{group.map((match) => <MatchCard key={match.id} match={match} />)}</ul>
          </section>
        )
      })}
    </Card>
  )
}

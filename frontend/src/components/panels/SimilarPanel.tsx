import { Link } from 'react-router-dom'
import { comparedLabel, labelForRelation, useSimilar } from '../../api/similar.ts'
import type { InnovationFull } from '../../api/types.ts'
import { Badge, Button, Card, ErrorNote, Loading } from '../ui.tsx'

export default function SimilarPanel({ innovation }: { innovation: InnovationFull }) {
  const similar = useSimilar(innovation.id)
  const result = similar.data

  return (
    <Card className="space-y-3 p-5">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Podobne rozwiązania</h2>
      {similar.isPending && <Loading label="Porównuję z radarem…" />}
      {similar.error && (
        <>
          <ErrorNote error={similar.error} />
          <Button type="button" variant="secondary" onClick={() => void similar.refetch()}>Spróbuj ponownie</Button>
        </>
      )}
      {result && (
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-x-2">
            <span className="text-sm font-medium text-slate-700">Świeżość w radarze</span>
            <span className="text-xl font-semibold tabular-nums text-brand-700">{result.novelty}<span className="text-sm">/100</span></span>
          </div>
          <p className="text-xs text-slate-500">{comparedLabel(result.compared)}</p>
          {result.engine.startsWith('embeddings:') && <p className="text-xs text-slate-500">{result.verdict}</p>}
          {result.nearest.length === 0 && <p className="text-sm text-slate-600">Brak podobnych rozwiązań w wynikach.</p>}
          {result.nearest.length > 0 && (
            <ul className="divide-y divide-slate-100">
              {result.nearest.map((item) => {
                const other = item.innovation
                const duplicate = item.relation === 'to_samo' && !item.same_organization
                  && Boolean(innovation.organization && other.organization)
                return (
                  <li key={other.id} className="space-y-1.5 py-3 last:pb-0">
                    <Link to={`/innowacje/${other.id}`} className="block text-sm font-semibold text-brand-700 hover:underline">
                      {other.title}
                    </Link>
                    {other.organization && <p className="text-xs text-slate-600">{other.organization.name}</p>}
                    <Badge tone={duplicate ? 'amber' : 'slate'}>{labelForRelation(item.relation)}</Badge>
                    {duplicate && (
                      <p className="rounded-lg bg-amber-50 p-2 text-xs font-medium text-amber-900">
                        Inna organizacja pracuje nad tym samym rozwiązaniem. Warto skontaktować się z zespołem.
                      </p>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </>
      )}
    </Card>
  )
}

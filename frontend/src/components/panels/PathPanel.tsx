import { ExternalLink } from 'lucide-react'
import type { FormEvent } from 'react'
import { useLabel, useMeta } from '../../api/hooks.ts'
import { usePathActions, useRecommendation } from '../../api/paths.ts'
import type { InnovationFull } from '../../api/types.ts'
import { usePersona } from '../../lib/persona.tsx'
import { Badge, Button, Card, ErrorNote, Field, inputClass, Loading } from '../ui.tsx'

const sectionTitle = 'technical-label'
const dateFormat = new Intl.DateTimeFormat('pl-PL', { dateStyle: 'long', timeStyle: 'short' })
const percentFormat = new Intl.NumberFormat('pl-PL', { style: 'percent', maximumFractionDigits: 1 })

function RecommendationPanel({ id }: { id: number }) {
  const { data, error, isPending } = useRecommendation(id)
  const { generate, accept } = usePathActions(id)
  const { persona } = usePersona()
  const { data: meta } = useMeta()
  const label = useLabel()

  function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const path = new FormData(event.currentTarget).get('path')
    if (typeof path === 'string') accept.mutate(path)
  }

  const actionError = generate.error ?? accept.error

  return (
    <Card className="space-y-4 p-6">
      <h2 className={sectionTitle}>Rekomendowana ścieżka</h2>
      {isPending && <Loading label="Wczytywanie rekomendacji…" />}
      {error && <ErrorNote error={error} />}
      {data === null && (
        <Button type="button" disabled={generate.isPending} onClick={() => generate.mutate()}>
          {generate.isPending ? 'Wyznaczanie ścieżki…' : 'Wskaż ścieżkę'}
        </Button>
      )}
      {data && (
        <>
          <div className="space-y-1">
            <h3 className="text-xl font-semibold text-slate-900">{label('paths', data.path)}</h3>
            {data.rationale && <p className="text-sm leading-relaxed text-slate-700">{data.rationale}</p>}
          </div>
          {data.reasons.length > 0 && (
            <details className="rounded-lg border border-slate-200 px-4 py-3" open>
              <summary className="cursor-pointer text-sm font-medium text-slate-900">Powody wyboru</summary>
              <ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-relaxed text-slate-700">
                {data.reasons.map((reason, index) => (
                  <li key={index}>
                    {reason.message}
                    {reason.points !== undefined && reason.points > 0 && (
                      <span className="text-slate-500"> {label('paths', reason.path)} (+{reason.points} pkt)</span>
                    )}
                    {reason.probabilities && (
                      <ul className="mt-1 space-y-0.5 text-slate-600">
                        {Object.entries(reason.probabilities).map(([path, probability]) => (
                          <li key={path}>{label('paths', path)} · {percentFormat.format(probability)}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <section>
            <h4 className={sectionTitle}>Kolejne kroki</h4>
            <ol className="mt-2 list-decimal space-y-3 pl-5 text-sm text-slate-700 marker:font-semibold">
              {data.steps.map((step) => (
                <li key={step.title} className="pl-1">
                  <p className="font-medium text-slate-900">{step.title}</p>
                  <p className="leading-relaxed">{step.description}</p>
                  {step.url && step.instrument && (
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <a
                        href={step.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 font-medium text-brand-700 hover:underline"
                      >
                        {step.instrument} <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
                      </a>
                      {step.verified === false && <Badge tone="amber">Niepotwierdzone</Badge>}
                    </div>
                  )}
                </li>
              ))}
            </ol>
          </section>
          <section>
            <h4 className={sectionTitle}>Mierniki skuteczności</h4>
            <dl className="mt-2 space-y-2 text-sm text-slate-700">
              {data.metrics.map((metric) => (
                <div key={metric.name} className="rounded-lg bg-slate-50 px-3 py-2">
                  <dt className="font-medium text-slate-900">{metric.name}</dt>
                  <dd className="mt-0.5">{metric.target}</dd>
                </div>
              ))}
            </dl>
          </section>
          {data.alternative && (
            <div>
              <h4 className={sectionTitle}>Druga możliwa ścieżka</h4>
              <p className="mt-1 text-sm font-medium text-slate-900">{label('paths', data.alternative.path)}</p>
              <p className="mt-0.5 text-sm text-slate-600">{data.alternative.reason}</p>
            </div>
          )}
          {data.approval && (
            <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 pt-4">
              <Badge tone="green">Zatwierdzona</Badge>
              <p className="text-sm text-slate-700">
                {data.approval.actor} · <time dateTime={data.approval.created_at}>
                  {dateFormat.format(new Date(data.approval.created_at))}
                </time>
              </p>
            </div>
          )}
          {!data.approval && persona?.role === 'broker' && meta && (
            <form
              key={data.id}
              onSubmit={approve}
              className="flex flex-wrap items-end gap-3 border-t border-slate-200 pt-4"
            >
              <Field label="Ścieżka do zatwierdzenia">
                <select name="path" defaultValue={data.path} className={inputClass} disabled={accept.isPending}>
                  {meta.paths.map((path) => <option key={path.key} value={path.key}>{path.label}</option>)}
                </select>
              </Field>
              <Button type="submit" disabled={accept.isPending}>
                {accept.isPending ? 'Zatwierdzanie…' : 'Zatwierdź ścieżkę'}
              </Button>
            </form>
          )}
        </>
      )}
      {actionError && <ErrorNote error={actionError} />}
    </Card>
  )
}

export default function PathPanel({ innovation }: { innovation: InnovationFull }) {
  return <RecommendationPanel key={innovation.id} id={innovation.id} />
}

import { ExternalLink, Radio, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { type RadarSource, useRadarSources, useRunRadar } from '../api/radar.ts'
import { Badge, Button, Card, ErrorNote, Loading } from '../components/ui.tsx'

const dateFormat = new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' })
const countFormat = new Intl.NumberFormat('pl-PL')

function SourceCard({ source }: { source: RadarSource }) {
  const run = useRunRadar(source.name)
  const last = source.last_run
  const active = source.status === 'aktywne'

  return (
    <Card className="space-y-5 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold text-slate-900">{source.title}</h2>
            <Badge tone={active ? 'green' : 'slate'}>{active ? 'Aktywne' : 'Planowane'}</Badge>
          </div>
          <p className="text-sm text-slate-600">{source.description}</p>
        </div>
        {active && (
          <Button onClick={() => run.mutate()} disabled={run.isPending} type="button">
            <RefreshCw aria-hidden="true" className={`size-4 ${run.isPending ? 'animate-spin' : ''}`} />
            {run.isPending ? 'Sprawdzanie…' : 'Sprawdź teraz'}
          </Button>
        )}
      </div>

      <dl className="grid gap-4 rounded-lg bg-slate-50 p-4 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-slate-600">Wykryte innowacje</dt>
          <dd className="text-xl font-semibold tabular-nums text-slate-900">{countFormat.format(source.count)}</dd>
        </div>
        {active && (
          <div>
            <dt className="text-slate-600">Ostatnie sprawdzenie</dt>
            <dd className="mt-1 font-medium text-slate-900">
              {last ? <time dateTime={last.finished_at}>{dateFormat.format(new Date(last.finished_at))}</time> : 'Jeszcze nie uruchomiono'}
            </dd>
            {last?.status === 'success' && (
              <dd className="text-slate-600">Wybrano {last.fetched} · Dodano {last.created} · Pominięto {last.skipped}</dd>
            )}
            {last?.status === 'error' && <dd className="text-rose-700">{last.error}</dd>}
          </div>
        )}
      </dl>

      {run.isError && <ErrorNote error={run.error} />}
      {run.data && (
        <section aria-live="polite" className="space-y-2 rounded-lg border border-brand-100 bg-brand-50 p-4 text-sm">
          <h3 className="font-semibold text-slate-900">
            {run.data.created ? `Nowo wykryte innowacje (${run.data.created})` : 'Brak nowych innowacji'}
          </h3>
          <p className="text-slate-700">Wybrano {run.data.fetched} · Dodano {run.data.created} · Pominięto {run.data.skipped}</p>
          {run.data.created_items.length > 0 && (
            <ul className="list-disc space-y-1.5 pl-5">
              {run.data.created_items.map((item) => (
                <li key={item.id}>
                  <Link to={`/innowacje/${item.id}`} className="font-medium text-brand-700 hover:underline">
                    {item.title}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {source.rules.length > 0 && (
        <section className="space-y-2 text-sm">
          <h3 className="font-semibold text-slate-900">Reguły wyboru</h3>
          <ul className="list-disc space-y-1.5 pl-5 text-slate-700">
            {source.rules.map((rule) => <li key={rule}>{rule}</li>)}
          </ul>
        </section>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-100 pt-4 text-sm">
        {source.url && (
          <a href={source.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-brand-700 hover:underline">
            Otwórz źródło <ExternalLink aria-hidden="true" className="size-3.5" />
          </a>
        )}
        {source.terms_url ? (
          <a href={source.terms_url} target="_blank" rel="noreferrer" className="text-slate-600 underline underline-offset-2">
            {source.terms}
          </a>
        ) : <span className="text-slate-600">{source.terms}</span>}
      </div>
    </Card>
  )
}

export default function Sources() {
  const { data, isPending, error } = useRadarSources()
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <header className="space-y-3 py-2">
        <h1 className="flex items-center gap-3 text-2xl font-bold text-slate-900 sm:text-3xl">
          <Radio aria-hidden="true" className="size-7 text-brand-600" />
          Źródła radaru
        </h1>
        <p className="max-w-2xl text-sm leading-relaxed text-slate-600 sm:text-base">
          Radar przegląda otwarte rejestry i szuka projektów, które mogą mieć zastosowanie w praktyce.
          {' '}Dla wykrytych projektów zakłada karty, które ich twórcy mogą później potwierdzić.
        </p>
      </header>
      {isPending && <Loading label="Ładowanie źródeł…" />}
      {error && <ErrorNote error={error} />}
      {data?.items.map((source) => <SourceCard key={source.name} source={source} />)}
    </div>
  )
}

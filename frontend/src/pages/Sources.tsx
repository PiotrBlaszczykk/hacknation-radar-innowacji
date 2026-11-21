import { ExternalLink, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { type RadarSource, useRadarSources, useRunRadar } from '../api/radar.ts'
import { Badge, Button, Card, ErrorNote, Loading } from '../components/ui.tsx'

const dateFormat = new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' })
const countFormat = new Intl.NumberFormat('pl-PL')

function SourceCard({ source }: { source: RadarSource }) {
  const run = useRunRadar(source.name)
  const last = source.last_run
  const active = source.status === 'aktywne'
  const statistics = source.statistics

  return (
    <Card className="space-y-5 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="wrap-anywhere font-display text-3xl leading-none font-semibold text-slate-900">{source.title}</h2>
            <Badge tone={active ? 'green' : 'slate'}>{active ? 'Aktywne' : 'Planowane'}</Badge>
          </div>
          <p className="max-w-[70ch] text-base text-slate-600">{source.description}</p>
        </div>
        {active && (
          <Button onClick={() => run.mutate()} disabled={run.isPending} type="button">
            <RefreshCw aria-hidden="true" className={`size-4 ${run.isPending ? 'animate-spin' : ''}`} />
            {run.isPending ? 'Sprawdzanie…' : 'Sprawdź teraz'}
          </Button>
        )}
      </div>

      <dl className="grid gap-4 border-y border-slate-200 py-4 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-slate-600">{source.name === 'crossref' ? 'Karty z powiązaną publikacją' : statistics ? 'Wybrane karty' : 'Wykryte innowacje'}</dt>
          <dd className="font-display text-3xl leading-tight font-semibold tabular-nums text-slate-900">{countFormat.format(source.count)}</dd>
        </div>
        {statistics && (
          <>
            <div>
              <dt className="text-slate-600">Przejrzane projekty</dt>
              <dd className="font-display text-3xl leading-tight font-semibold tabular-nums text-slate-900">
                {statistics.scanned === null ? 'Brak danych o skanie' : countFormat.format(statistics.scanned)}
              </dd>
              {statistics.complete_scan === false && <dd className="text-slate-600">Skan częściowy</dd>}
            </div>
            <div>
              <dt className="text-slate-600">Karty odrzucone przez model</dt>
              <dd className="font-display text-3xl leading-tight font-semibold tabular-nums text-slate-900">{countFormat.format(statistics.rejected)}</dd>
              <dd className="text-slate-600">
                {statistics.reviewed === 0
                  ? 'Przegląd kart jeszcze się nie rozpoczął'
                  : `Rozpatrzono ${countFormat.format(statistics.reviewed)} z ${countFormat.format(source.count)} kart`}
              </dd>
            </div>
          </>
        )}
        {active && (
          <div>
            <dt className="text-slate-600">Ostatnie sprawdzenie</dt>
            <dd className="mt-1 font-medium text-slate-900">
              {last ? <time dateTime={last.finished_at}>{dateFormat.format(new Date(last.finished_at))}</time> : 'Jeszcze nie uruchomiono'}
            </dd>
            {last?.status === 'success' && (
              <dd className="text-slate-600">Wybrano {last.fetched} · Dodano {last.created} · Pominięto {last.skipped}{last.updated ? ` · Uzupełniono ${last.updated}` : ''}</dd>
            )}
            {last?.status === 'error' && <dd className="text-rose-700">{last.error}</dd>}
          </div>
        )}
      </dl>

      {run.isError && <ErrorNote error={run.error} />}
      {run.data && (
        <section aria-live="polite" className="space-y-2 rounded-lg border border-brand-100 bg-brand-50 p-4 text-sm">
          <h3 className="font-semibold text-slate-900">
            {run.data.created || run.data.updated ? 'Wynik sprawdzenia' : 'Brak nowych i uzupełnionych kart'}
          </h3>
          <p className="text-slate-700">Wybrano {run.data.fetched} · Dodano {run.data.created} · Pominięto {run.data.skipped}{run.data.updated ? ` · Uzupełniono ${run.data.updated}` : ''}</p>
          {!!run.data.selection?.unavailable?.length && (
            <p className="text-amber-800">Nie udało się sprawdzić wszystkich adresów ({run.data.selection.unavailable.length}).</p>
          )}
          {[
            { title: 'Nowe karty', items: run.data.created_items },
            { title: 'Karty z uzupełnionymi danymi', items: run.data.updated_items ?? [] },
          ].filter(({ items }) => items.length > 0).map(({ title, items }) => (
            <div key={title}>
              <h4 className="technical-label">{title}</h4>
              <ul className="mt-1 list-disc space-y-1.5 pl-5">
                {items.map((item) => (
                  <li key={item.id}>
                    <Link to={`/innowacje/${item.id}`} className="wrap-anywhere font-medium text-brand-700 hover:underline">
                      {item.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
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
    <div className="mx-auto max-w-4xl space-y-5">
      <header className="space-y-3 border-b border-slate-200 pb-4">
        <h1 className="page-title">Źródła radaru</h1>
        <p className="max-w-2xl text-sm leading-relaxed text-slate-600 sm:text-base">
          Sprawdź, skąd pochodzą karty i kiedy radar ostatnio odwiedził dane źródło.
        </p>
      </header>
      {isPending && <Loading label="Ładowanie źródeł…" />}
      {error && <ErrorNote error={error} />}
      {data?.items.length === 0 && <p className="text-slate-600">Brak źródeł w rejestrze radaru.</p>}
      {data?.items.map((source) => <SourceCard key={source.name} source={source} />)}
    </div>
  )
}

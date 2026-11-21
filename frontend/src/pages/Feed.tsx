import { ArrowLeft, ArrowUpRight, ChevronDown, CircleHelp, Search, SlidersHorizontal } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPersonaId } from '../api/client.ts'
import { MAX_ABOUT, useFeed, useFeedExplain, useSaveProfile, type FeedFilters, type FeedTab } from '../api/feed.ts'
import { useInnovation, useMeta } from '../api/hooks.ts'
import type { Meta } from '../api/types.ts'
import InnovationCard, { sourceLabel } from '../components/InnovationCard.tsx'
import { Button, Card, ErrorNote, Loading, cx, inputClass } from '../components/ui.tsx'
import { usePersona } from '../lib/persona.tsx'

const tabs = [
  { id: 'dla_ciebie', label: 'Dla Ciebie' },
  { id: 'perelki', label: 'Ukryte perełki' },
  { id: 'popularne', label: 'Popularne' },
  { id: 'najnowsze', label: 'Najnowsze' },
] as const

const filterFields: { key: keyof FeedFilters; label: string; dictionary: keyof Meta }[] = [
  { key: 'kind', label: 'Rodzaj', dictionary: 'innovation_kinds' },
  { key: 'stage', label: 'Etap', dictionary: 'stages' },
  { key: 'domain', label: 'Obszar', dictionary: 'domains' },
  { key: 'origin', label: 'Pochodzenie', dictionary: 'origins' },
]

const emptyMessages: Record<FeedTab, string> = {
  dla_ciebie: 'Brak innowacji pasujących do wybranych filtrów.',
  perelki: 'Brak innowacji spełniających kryteria ukrytej perełki w tym zestawie.',
  popularne: 'Brak aktywności z ostatnich 14 dni w tym zestawie.',
  najnowsze: 'Brak innowacji pasujących do wybranych filtrów.',
}

const featuredInnovationId = 514
const resultCount = new Intl.NumberFormat('pl-PL')

function FeaturedInnovation({ personaId }: { personaId: number | null }) {
  const { data: innovation } = useInnovation(featuredInnovationId, personaId)
  if (!innovation?.source_url || !innovation.problem || innovation.status === 'archiwum') return null

  const visitCount = innovation.results?.match(/pierwszym półroczu 2026 r\. urzędnik odwiedził (\d+) mieszkańców/i)?.[1]

  return (
    <article className="grid min-w-0 border-y border-slate-200 bg-shell lg:self-center">
      <div className={cx('grid min-w-0', visitCount && 'min-[360px]:grid-cols-[minmax(0,1fr)_6rem] md:grid-cols-[minmax(0,1fr)_10rem] xl:grid-cols-[minmax(0,1fr)_11rem]')}>
        <div className="min-w-0 px-3 py-3.5 sm:px-5 sm:py-6 xl:px-6">
          <h2 className="wrap-anywhere font-display text-[1.75rem] leading-[.98] font-semibold text-slate-900 md:text-[2.625rem]">{innovation.title}</h2>
          <p className="mt-2 max-w-[42ch] text-sm leading-snug text-slate-600 md:mt-3 md:text-base">{innovation.problem}</p>
        </div>
        {visitCount && (
          <dl className="flex flex-row items-center gap-2 border-t border-slate-200 px-3 py-2 min-[360px]:flex-col min-[360px]:items-start min-[360px]:gap-0 min-[360px]:border-t-0 min-[360px]:border-l min-[360px]:py-3.5 md:justify-center md:px-5">
            <dt className="order-2 text-xs leading-snug text-slate-700 md:text-sm">
              odwiedzonych mieszkańców
              <span className="mt-1 block whitespace-nowrap text-[.6875rem] font-semibold text-slate-500 md:text-xs">I półrocze 2026</span>
            </dt>
            <dd className="font-display text-5xl leading-none font-semibold tabular-nums text-brand-600 md:text-8xl md:leading-[.87]">{visitCount}</dd>
          </dl>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-3 border-t border-slate-200 px-3 sm:px-5 xl:px-6">
        <a href={innovation.source_url} target="_blank" rel="noreferrer"
          className="inline-flex min-h-10 items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 hover:underline">
          {innovation.organization?.name ?? sourceLabel(innovation.source_name) ?? 'Źródło'}
          <ArrowUpRight className="size-3.5 shrink-0" aria-hidden="true" />
        </a>
        <Link to={`/innowacje/${innovation.id}`}
          className="inline-flex min-h-10 items-center gap-1.5 text-sm font-semibold text-brand-700 hover:underline">
          Otwórz kartę <ArrowUpRight className="size-4" aria-hidden="true" />
        </Link>
      </div>
    </article>
  )
}

export default function Feed() {
  const { persona } = usePersona()
  const personaId = persona?.id ?? getPersonaId()
  const resultsHeading = useRef<HTMLHeadingElement>(null)
  const [tab, setTab] = useState<FeedTab>('dla_ciebie')
  const [description, setDescription] = useState('')
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<FeedFilters>({})
  const [explaining, setExplaining] = useState(false)
  const { data: meta } = useMeta()
  const feed = useFeed(personaId, search ? 'dla_ciebie' : tab, search, filters)
  const explanation = useFeedExplain(explaining)
  const save = useSaveProfile()
  const firstPage = feed.data?.pages[0]
  const savedForSearch = save.variables?.personaId === personaId && save.variables?.input.about === search
  const activeFilters = Object.values(filters).filter(Boolean).length

  return (
    <div className="min-w-0">
      <div className="grid items-stretch gap-5 sm:gap-7 lg:has-[>article]:grid-cols-[minmax(0,.96fr)_minmax(0,1fr)] lg:gap-12 xl:gap-16">
        <form
          className="min-w-0 py-1 sm:py-3 lg:py-5"
          onSubmit={(event) => {
            event.preventDefault()
            const query = description.trim()
            if (!query) return
            save.reset()
            setSearch(query)
            requestAnimationFrame(() => resultsHeading.current?.focus())
          }}
        >
          <h1 className="font-display text-[2.75rem] leading-[.87] font-bold tracking-tight text-slate-900 uppercase sm:text-6xl lg:text-[5.125rem] xl:text-[5.75rem]">
            Znajdź <span className="lg:block">innowację</span>
          </h1>
          <label htmlFor="feed-description" className="mt-3 block text-sm font-semibold text-slate-700 lg:mt-5">Opisz, czego szukasz</label>
          <div className="mt-1.5 flex items-stretch">
            <input
              id="feed-description"
              className={cx(inputClass, 'min-w-0 flex-1 rounded-r-none sm:min-h-[3.25rem]')}
              type="search"
              required
              placeholder="Np. mniej smogu w gminie"
              value={description}
              maxLength={MAX_ABOUT}
              onChange={(event) => setDescription(event.target.value)}
            />
            <Button type="submit" aria-label="Szukaj innowacji"
              className="min-h-11 shrink-0 rounded-l-none px-3 sm:px-5">
              <Search className="size-[1.125rem]" aria-hidden="true" /> Szukaj
            </Button>
          </div>
        </form>
        <FeaturedInnovation personaId={personaId} />
      </div>

      <div className="mt-5 sm:mt-8">
        {search ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Button type="button" variant="ghost" onClick={() => { setSearch(''); save.reset() }}>
                <ArrowLeft className="size-4" aria-hidden="true" /> Wróć do feedu
              </Button>
              {personaId !== null && (
                <Button
                  type="button"
                  variant="secondary"
                  disabled={save.isPending || (savedForSearch && save.isSuccess)}
                  onClick={() => save.mutate({ personaId, input: { about: search } })}
                >
                  {save.isPending ? 'Zapisywanie…' : 'Zapisz jako moje zainteresowania'}
                </Button>
              )}
            </div>
            {savedForSearch && save.isSuccess && <p role="status" className="text-sm text-emerald-700">Opis zapisany w profilu.</p>}
            {savedForSearch && save.error && <ErrorNote error={save.error} />}
          </div>
        ) : (
          <nav aria-label="Widoki feedu" className="flex flex-wrap gap-x-3 border-b border-slate-200 max-[359px]:gap-x-2 sm:gap-x-6">
            {tabs.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                aria-current={tab === id ? 'true' : undefined}
                onClick={() => setTab(id)}
                className={cx(
                  'flex min-h-11 items-center gap-1.5 border-b-2 px-0.5 py-2 text-sm font-semibold sm:px-1',
                  tab === id ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-600 hover:text-slate-900',
                )}
              >
                {label}
              </button>
            ))}
          </nav>
        )}

        <div className="my-2 flex flex-wrap items-start justify-between gap-x-4 gap-y-2 sm:my-3">
          <details className="group grow">
            <summary className="flex min-h-10 w-fit cursor-pointer list-none items-center gap-1.5 rounded-sm py-1 text-sm font-medium text-slate-700">
              <SlidersHorizontal className="size-4" aria-hidden="true" />
              Filtry{activeFilters > 0 && ` (${activeFilters})`}
              <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" aria-hidden="true" />
            </summary>
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {filterFields.map(({ key, label, dictionary }) => (
                <label key={key} className="min-w-0 text-xs font-medium text-slate-600">
                  {label}
                  <select
                    className={cx(inputClass, 'mt-1')}
                    value={filters[key] ?? ''}
                    onChange={(event) => setFilters({ ...filters, [key]: event.target.value || undefined })}
                  >
                    <option value="">Wszystkie</option>
                    {meta?.[dictionary].map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}
                  </select>
                </label>
              ))}
            </div>
            {activeFilters > 0 && (
              <Button variant="ghost" type="button" className="mt-2 px-2" onClick={() => setFilters({})}>Wyczyść filtry</Button>
            )}
          </details>
          <button
            type="button"
            aria-expanded={explaining}
            aria-controls="feed-explanation"
            className="flex min-h-10 items-center gap-1.5 rounded-sm py-1 text-sm font-medium text-brand-700 hover:underline"
            onClick={() => setExplaining(!explaining)}
          >
            <CircleHelp className="size-4" aria-hidden="true" /> Jak dobieramy innowacje?
          </button>
        </div>

        <div id="feed-explanation" hidden={!explaining}>
          <Card className="mb-4 space-y-4 p-5">
            {explanation.isPending && <Loading />}
            {explanation.error && <ErrorNote error={explanation.error} />}
            {explanation.data?.sections.map(({ title, lines }) => (
              <section key={title}>
                <h2 className="font-semibold text-slate-900">{title}</h2>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-slate-600">
                  {lines.map((line) => <li key={line}>{line}</li>)}
                </ul>
              </section>
            ))}
          </Card>
        </div>

        <section aria-labelledby="feed-results" className="border-t border-slate-200">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3 sm:py-4">
            <h2 id="feed-results" ref={resultsHeading} tabIndex={-1}
              className="section-title scroll-mt-4 wrap-anywhere lg:scroll-mt-32">
              {search ? `Wyniki dla „${search}”` : 'Innowacje'}
            </h2>
            {firstPage && <p className="technical-label tabular-nums">Liczba wyników: {resultCount.format(firstPage.total)}</p>}
          </div>
          {feed.isPending && <Loading label="Dobieramy innowacje…" />}
          {firstPage?.notice && <p role="status" className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800">{firstPage.notice}</p>}
          <div className="grid border-b border-slate-200 lg:grid-cols-2" aria-busy={feed.isFetching}>
            {feed.data?.pages.flatMap((page) => page.items).map((innovation) => (
              <InnovationCard key={innovation.id} innovation={innovation} />
            ))}
          </div>
          {firstPage?.total === 0 && (
            <Card className="space-y-1 p-5 text-slate-600">
              <p className="font-semibold text-slate-900">{firstPage.message ?? (search ? 'Brak innowacji pasujących do tego opisu.' : emptyMessages[tab])}</p>
              {search && <p>Spróbuj krótszego opisu lub usuń część filtrów.</p>}
              {activeFilters > 0 && <Button type="button" variant="secondary" className="mt-2" onClick={() => setFilters({})}>Wyczyść filtry</Button>}
            </Card>
          )}
          {feed.error && (
            <div className="space-y-2">
              <ErrorNote error={feed.error} />
              <Button type="button" variant="secondary" onClick={() => void feed.refetch()}>Spróbuj ponownie</Button>
            </div>
          )}
          {feed.hasNextPage && (
            <Button
              type="button"
              variant="secondary"
              className="mt-4 w-full"
              disabled={feed.isFetching}
              onClick={() => void feed.fetchNextPage()}
            >
              {feed.isFetchingNextPage ? 'Ładowanie…' : 'Pokaż więcej'}
            </Button>
          )}
        </section>
      </div>
    </div>
  )
}

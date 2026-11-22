import RelatedProjects from '../components/RelatedProjects.tsx'
import { ArrowLeft, ArrowRight, ArrowUpRight, ChevronDown, CircleHelp, Compass, Search, SlidersHorizontal } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getPersonaId } from '../api/client.ts'
import { MAX_ABOUT, useFeed, useFeedExplain, useSaveProfile, type FeedFilters, type FeedTab } from '../api/feed.ts'
import { useInnovation, useMeta } from '../api/hooks.ts'
import type { Meta } from '../api/types.ts'
import InnovationCard, { sourceLabel } from '../components/InnovationCard.tsx'
import { Button, Card, ErrorNote, Loading, cx, inputClass } from '../components/ui.tsx'
import { usePersona } from '../lib/persona.tsx'

const gemsLabel = 'Ukryte perełki'
const tabs = [
  { id: 'dla_ciebie', label: 'Dla Ciebie' },
  { id: 'obserwowani', label: 'Obserwowani' },
  { id: 'perelki', label: gemsLabel },
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
  perelki: 'Brak mało zauważonych wdrożeń i prób spełniających kryteria.',
  popularne: 'Brak aktywności z ostatnich 14 dni w tym zestawie.',
  obserwowani: 'Tutaj zobaczysz wpisy, komentarze i reposty osób oraz organizacji, które obserwujesz.',
  najnowsze: 'Brak innowacji pasujących do wybranych filtrów.',
}

const featuredInnovationId = 514
const resultCount = new Intl.NumberFormat('pl-PL')

function FeaturedInnovation({ personaId }: { personaId: number | null }) {
  const { data: innovation } = useInnovation(featuredInnovationId, personaId)
  if (!innovation?.source_url || innovation.status === 'archiwum') return null

  const visitCount = innovation.results?.match(/pierwszym półroczu 2026 r\. urzędnik odwiedził (\d+) mieszkańców/i)?.[1]

  return (
    <article className="min-w-0 overflow-hidden rounded-b-xl border-t border-slate-200 bg-surface">
      <div className="px-4 py-4 sm:px-5 sm:py-5">
        <h2 className="wrap-anywhere font-display text-[1.85rem] leading-[.98] font-bold text-slate-900 max-[359px]:text-[1.4rem] sm:text-[2rem]">{innovation.title}</h2>
        <p className="mt-2 max-w-[50ch] text-sm leading-snug text-slate-600">{innovation.summary || innovation.problem}</p>
        {visitCount && (
          <dl className="mt-4 flex items-center gap-3 border-t border-slate-200 pt-3">
            <dt className="order-2 text-sm font-semibold leading-tight text-slate-800">
              odwiedzonych mieszkańców
              <span className="mt-0.5 block text-xs font-normal text-slate-500">I półrocze 2026</span>
            </dt>
            <dd className="font-display text-[2.75rem] leading-[.85] font-bold tabular-nums text-brand-700">{visitCount}</dd>
          </dl>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-3 border-t border-slate-200 bg-slate-50 px-4 sm:px-5">
        <a href={innovation.source_url} target="_blank" rel="noreferrer"
          className="inline-flex min-h-11 items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 hover:underline">
          Źródło danych · {innovation.organization?.name ?? sourceLabel(innovation.source_name) ?? 'Publikacja źródłowa'}
          <ArrowUpRight className="size-3.5 shrink-0" aria-hidden="true" />
        </a>
        <Link to={`/innowacje/${innovation.id}`}
          className="inline-flex min-h-11 items-center gap-1.5 text-sm font-semibold text-brand-700 hover:underline">
          <span className="not-sr-only max-[359px]:sr-only">Otwórz kartę</span><span className="min-[360px]:hidden" aria-hidden="true">Karta</span>
          <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
      </div>
    </article>
  )
}

export default function Feed() {
  const { persona } = usePersona()
  const personaId = persona?.id ?? getPersonaId()
  const resultsHeading = useRef<HTMLHeadingElement>(null)
  const [pageParams, setPageParams] = useSearchParams()
  const tab = tabs.find(({ id }) => id === pageParams.get('tab'))?.id ?? (persona?.name === 'Lena Wrona · demo' ? 'obserwowani' : 'dla_ciebie')
  const [description, setDescription] = useState('')
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<FeedFilters>({})
  const [explaining, setExplaining] = useState(false)
  const { data: meta } = useMeta()
  const feed = useFeed(personaId, search ? 'dla_ciebie' : tab, search, filters)
  const explanation = useFeedExplain(explaining)
  const save = useSaveProfile()
  const showingGems = !search && tab === 'perelki'
  const explanationSections = explanation.data?.sections.filter(
    ({ title }) => !showingGems || title === gemsLabel,
  )
  const firstPage = feed.data?.pages[0]
  const savedForSearch = save.variables?.personaId === personaId && save.variables?.input.about === search
  const activeFilters = Object.values(filters).filter(Boolean).length

  return (
    <div className="grid min-w-0 gap-y-4 sm:gap-y-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-x-10 xl:grid-cols-[minmax(0,1fr)_22rem] xl:gap-x-14">
      <form
        className="min-w-0 lg:col-start-1"
        onSubmit={(event) => {
          event.preventDefault()
          const query = description.trim()
          if (!query) return
          save.reset()
          setSearch(query)
          requestAnimationFrame(() => resultsHeading.current?.focus())
        }}
      >
        <h1 className="font-display text-[2.85rem] leading-[.93] font-bold tracking-tight text-slate-900 max-[359px]:text-[2.4rem] sm:text-[4.125rem] xl:text-[4.75rem]">
          Odkrywaj <span className="text-brand-700">innowacje.</span>
        </h1>
        <label htmlFor="feed-description" className="mt-4 block text-sm font-semibold text-slate-800">Opisz, czego szukasz</label>
        <div className="mt-1.5 flex max-w-[39rem] items-stretch">
          <input
            id="feed-description"
            className={cx(inputClass, 'min-w-0 flex-1 rounded-r-none bg-surface sm:min-h-12')}
            type="search"
            required
            placeholder="Np. smog w gminie"
            value={description}
            maxLength={MAX_ABOUT}
            onChange={(event) => setDescription(event.target.value)}
          />
          <Button type="submit" aria-label="Szukaj innowacji"
            className="min-h-11 shrink-0 rounded-l-none px-3.5 sm:px-5">
            <Search className="size-[1.125rem]" aria-hidden="true" /> Szukaj
          </Button>
        </div>
      </form>
      <aside
        className={cx('min-w-0 space-y-1 sm:space-y-3 lg:sticky lg:top-36 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:self-start')}
        aria-label="Porównania i zapotrzebowania"
      >
        {!search && !activeFilters && <RelatedProjects preview />}
        {tab === 'dla_ciebie' && !search && !activeFilters && (
          <details className="rounded-xl border border-slate-200 bg-surface">
            <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-brand-700">
              Zobacz przykład wdrożenia znalezionego przez radar
            </summary>
            <FeaturedInnovation personaId={personaId} />
          </details>
        )}
        <Link to="/zapotrzebowania"
          className="hidden min-h-11 items-center gap-2.5 rounded-sm px-1 text-sm font-semibold text-slate-700 hover:text-brand-700 hover:underline min-[360px]:flex">
          <Compass className="size-4 text-brand-700" aria-hidden="true" />
          Zobacz zapotrzebowania organizacji
          <ArrowRight className="ml-auto size-4 shrink-0" aria-hidden="true" />
        </Link>
      </aside>

      <div className="min-w-0 lg:col-start-1">
        {search ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Button type="button" variant="ghost" onClick={() => { setSearch(''); save.reset() }}>
                <ArrowLeft className="size-4" aria-hidden="true" /> Wróć do feedu
              </Button>
              <Link
                to="/zapotrzebowania?dodaj=1#dodaj-potrzebe"
                state={{ description: search }}
                className="inline-flex min-h-10 items-center gap-2 rounded-sm border border-brand-700 px-3 text-sm font-semibold text-brand-700 hover:bg-brand-50"
              >
                Zgłoś potrzebę <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
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
          <nav aria-label="Widoki feedu" className="flex flex-wrap gap-x-3 border-y border-slate-200 max-[359px]:justify-between max-[359px]:gap-x-1 sm:gap-x-6">
            {tabs.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                aria-current={tab === id ? 'true' : undefined}
                onClick={() => setPageParams((previous) => {
                  const params = new URLSearchParams(previous)
                  params.set('tab', id)
                  return params
                }, { replace: true })}
                className={cx(
                  'flex min-h-11 items-center border-b-2 px-0.5 py-2 text-sm font-bold transition-colors max-[359px]:text-[.8rem] sm:px-1',
                  tab === id ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-600 hover:text-brand-700',
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
            <CircleHelp className="size-4" aria-hidden="true" />
            {showingGems ? 'Jak wybieramy perełki?' : 'Jak dobieramy innowacje?'}
          </button>
        </div>

        <div id="feed-explanation" hidden={!explaining}>
          <Card className="mb-4 space-y-4 p-5">
            {explanation.isPending && <Loading />}
            {explanation.error && <ErrorNote error={explanation.error} />}
            {explanationSections?.map(({ title, lines }) => (
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
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5">
            <h2 id="feed-results" ref={resultsHeading} tabIndex={-1}
              className={cx('scroll-mt-4 wrap-anywhere lg:scroll-mt-32', search ? 'section-title' : 'text-sm font-bold')}>
              {search ? `Wyniki dla „${search}”` : showingGems ? 'Mało zauważone wdrożenia i próby' : 'Wpisy'}
            </h2>
            {firstPage && <p className="text-sm tabular-nums text-slate-500">Wyniki · {resultCount.format(firstPage.total)}</p>}
          </div>
          {feed.isPending && <Loading label="Dobieramy innowacje…" />}
          {firstPage?.notice && <p role="status" className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800">{firstPage.notice}</p>}
          <div className="grid divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 bg-surface" aria-busy={feed.isFetching}>
            {feed.data?.pages.flatMap((page) => page.items).map((innovation) => (
              <InnovationCard key={innovation.id} innovation={innovation} showReason={showingGems} />
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

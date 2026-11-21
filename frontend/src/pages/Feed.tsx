import { ArrowLeft, ChevronDown, CircleHelp, Clock3, Flame, Search, SlidersHorizontal, Sparkles, UserRound } from 'lucide-react'
import { useState } from 'react'
import { getPersonaId } from '../api/client.ts'
import { MAX_ABOUT, useFeed, useFeedExplain, useSaveProfile, type FeedFilters, type FeedTab } from '../api/feed.ts'
import { useMeta } from '../api/hooks.ts'
import type { Meta } from '../api/types.ts'
import InnovationCard from '../components/InnovationCard.tsx'
import { Button, Card, ErrorNote, Loading, cx, inputClass } from '../components/ui.tsx'
import { usePersona } from '../lib/persona.tsx'

const tabs = [
  { id: 'dla_ciebie', label: 'Dla Ciebie', icon: UserRound },
  { id: 'perelki', label: 'Ukryte perełki', icon: Sparkles },
  { id: 'popularne', label: 'Popularne', icon: Flame },
  { id: 'najnowsze', label: 'Najnowsze', icon: Clock3 },
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

export default function Feed() {
  const { persona } = usePersona()
  const personaId = persona?.id ?? getPersonaId()
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
    <div className="mx-auto max-w-3xl space-y-5">
      <Card className="border-brand-100 bg-gradient-to-br from-brand-50 to-white p-5 sm:p-7">
        <form
          onSubmit={(event) => {
            event.preventDefault()
            save.reset()
            setSearch(description.trim())
          }}
        >
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            <label htmlFor="feed-description">Opisz, czego szukasz</label>
          </h1>
          <p id="feed-example" className="mt-1 text-sm text-slate-600">Np. sposób na opiekę nad seniorami w małej gminie.</p>
          <div className="mt-4 flex flex-col gap-2 sm:flex-row">
            <input
              id="feed-description"
              aria-describedby="feed-example"
              className={inputClass}
              type="search"
              value={description}
              maxLength={MAX_ABOUT}
              onChange={(event) => setDescription(event.target.value)}
            />
            <Button type="submit" className="shrink-0" disabled={!description.trim()}>
              <Search className="size-4" aria-hidden="true" /> Szukaj innowacji
            </Button>
          </div>
        </form>
      </Card>

      <div>
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
            <h2 className="break-words text-base font-semibold text-slate-900">Wyniki dla „{search}”</h2>
            {savedForSearch && save.isSuccess && <p role="status" className="text-sm text-emerald-700">Opis zapisany w profilu.</p>}
            {savedForSearch && save.error && <ErrorNote error={save.error} />}
          </div>
        ) : (
          <nav aria-label="Widoki feedu" className="flex flex-wrap gap-1 border-b border-slate-200">
            {tabs.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                aria-current={tab === id ? 'true' : undefined}
                onClick={() => setTab(id)}
                className={cx(
                  'flex items-center gap-1.5 border-b-2 px-2.5 py-2.5 text-sm font-medium sm:px-3.5',
                  tab === id ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-600 hover:text-slate-900',
                )}
              >
                <Icon className="size-4" aria-hidden="true" /> {label}
              </button>
            ))}
          </nav>
        )}

        <div className="my-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <details className="group grow">
            <summary className="flex w-fit cursor-pointer list-none items-center gap-1.5 py-1 text-sm font-medium text-slate-700">
              <SlidersHorizontal className="size-4" aria-hidden="true" />
              Filtry{activeFilters > 0 && ` (${activeFilters})`}
              <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" aria-hidden="true" />
            </summary>
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {filterFields.map(({ key, label, dictionary }) => (
                <label key={key} className="text-xs font-medium text-slate-600">
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
            className="flex items-center gap-1.5 py-1 text-sm font-medium text-brand-700 hover:underline"
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

        {!search && tab === 'dla_ciebie' && persona && (
          <p className="mb-3 text-sm text-slate-500">Dopasowania dla persony <span className="font-medium">{persona.name}</span></p>
        )}
        <section aria-label="Wpisy radaru" className="space-y-3" aria-busy={feed.isFetching}>
          {feed.isPending && <Loading label="Dobieramy innowacje…" />}
          {firstPage?.notice && <p role="status" className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800">{firstPage.notice}</p>}
          {feed.data?.pages.flatMap((page) => page.items).map((innovation) => (
            <InnovationCard key={innovation.id} innovation={innovation} />
          ))}
          {firstPage?.total === 0 && (
            <Card className="p-8 text-center text-sm text-slate-600">
              {firstPage.message ?? (search ? 'Brak innowacji pasujących do tego opisu.' : emptyMessages[tab])}
            </Card>
          )}
          {feed.error && <ErrorNote error={feed.error} />}
          {feed.hasNextPage && (
            <Button
              type="button"
              variant="secondary"
              className="w-full"
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

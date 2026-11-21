import { useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { useLabel, useMeta } from '../api/hooks.ts'
import { matchStrength, useCloseNeed, useCreateNeed, useNeed, useNeedMatches, useNeeds } from '../api/matching.ts'
import type { Need, NeedInput } from '../api/matching.ts'
import { useOpportunities, type CoverageStatus, type Opportunity } from '../api/opportunities.ts'
import { Badge, Button, Card, ChipSelect, ErrorNote, Field, inputClass, Loading, type Tone } from '../components/ui.tsx'
import { usePersona } from '../lib/persona.tsx'

const emptyInput: NeedInput = { title: '', description: '', domains: [], offers: [] }

function NeedForm({ onCreated, description, focused }: {
  onCreated: (id: number) => void
  description: string
  focused: boolean
}) {
  const { persona } = usePersona()
  const meta = useMeta()
  const create = useCreateNeed()
  const [input, setInput] = useState({ ...emptyInput, description })
  const [conditions, setConditions] = useState('')
  const requirements = conditions.split('\n').map((line) => line.trim()).filter(Boolean)
  const organization = persona?.organization

  function publish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!organization || !input.title.trim() || !input.description.trim() || requirements.length > 6) return
    const conditionList = requirements.length ? `\n\nWarunki:\n${requirements.map((line) => `- ${line}`).join('\n')}` : ''
    create.mutate({ ...input, description: input.description.trim() + conditionList }, {
      onSuccess: (need) => {
        setInput(emptyInput)
        setConditions('')
        onCreated(need.id)
      },
    })
  }

  return (
    <Card id="dodaj-potrzebe" className="scroll-mt-28 p-5">
      <h2 className="section-title">Dodaj zapotrzebowanie</h2>
      {organization ? (
        <p className="mt-1 text-sm text-slate-600">Publikujesz w imieniu organizacji {organization.name}.</p>
      ) : (
        <p className="mt-1 text-sm text-slate-600">Wybierz w nagłówku osobę przypisaną do organizacji.</p>
      )}
      {description && !create.isSuccess && <p className="mt-2 text-sm text-slate-700">Przenieśliśmy opis z wyszukiwarki. Możesz go poprawić przed publikacją.</p>}
      <form onSubmit={publish} className="mt-4 space-y-4">
        <Field label="Tytuł">
          <input
            className={inputClass}
            autoFocus={focused}
            value={input.title}
            onChange={(event) => setInput({ ...input, title: event.target.value })}
            maxLength={400}
            required
          />
        </Field>
        <Field label="Opis">
          <textarea
            aria-label="Opis"
            className={inputClass}
            value={input.description}
            onChange={(event) => setInput({ ...input, description: event.target.value })}
            rows={3}
            required
          />
        </Field>
        <Field label="Warunki (opcjonalnie)" hint="Wpisz do sześciu warunków, po jednym w wierszu.">
          <textarea
            className={inputClass}
            value={conditions}
            onChange={(event) => setConditions(event.target.value)}
            rows={2}
            maxLength={800}
            aria-invalid={requirements.length > 6}
          />
        </Field>
        {requirements.length > 6 && <p role="alert" className="text-sm text-rose-700">Zostaw najwyżej sześć warunków.</p>}
        {meta.isPending && <Loading label="Wczytywanie obszarów i ofert…" />}
        {meta.isError && <ErrorNote error={meta.error} />}
        {meta.data && (
          <>
            <fieldset>
              <legend className="mb-2 text-sm font-medium text-slate-800">Obszary</legend>
              <ChipSelect
                options={meta.data.domains}
                value={input.domains}
                onChange={(domains) => setInput({ ...input, domains })}
              />
            </fieldset>
            <fieldset>
              <legend className="mb-2 text-sm font-medium text-slate-800">Co mogę zaoferować</legend>
              <ChipSelect
                options={meta.data.support_needs}
                value={input.offers}
                onChange={(offers) => setInput({ ...input, offers })}
              />
            </fieldset>
          </>
        )}
        {create.isError && <ErrorNote error={create.error} />}
        <Button type="submit" disabled={create.isPending || !organization || !meta.data || requirements.length > 6}>
          {create.isPending ? 'Publikowanie i szukanie dopasowań…' : 'Opublikuj zapotrzebowanie'}
        </Button>
        {create.isSuccess && <p role="status" className="text-sm text-emerald-700">Zapotrzebowanie opublikowane.</p>}
      </form>
    </Card>
  )
}

const decisionLabels = {
  zainteresowanie: 'Zgłoszono zainteresowanie',
  kontakt: 'Połączono strony',
  odrzucone: 'Odrzucone',
}

function NeedMatches({ id, closed }: { id: number; closed: boolean }) {
  const matches = useNeedMatches(id)
  if (matches.isPending) return <Loading label="Wczytywanie dopasowań…" />
  if (matches.isError) return <ErrorNote error={matches.error} />

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-slate-900">{closed ? 'Zapisane decyzje o dopasowaniach' : 'Dopasowane innowacje'}</h3>
      {matches.data.items.length ? (
        <ol className="divide-y divide-slate-200">
          {matches.data.items.map((match) => (
            <li key={match.id} className="space-y-1 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <Link to={`/innowacje/${match.innovation.id}`} className="font-medium text-brand-700 hover:underline">
                  {match.innovation.title}
                </Link>
                {!closed && <Badge tone="brand">{matchStrength(match.score)}</Badge>}
                {match.status !== 'proponowane' && <Badge>{decisionLabels[match.status]}</Badge>}
              </div>
              <p className="text-sm text-slate-700">{match.reason}</p>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-slate-600">{closed ? 'Brak zapisanych decyzji.' : 'Radar nie znalazł jeszcze dopasowanych innowacji.'}</p>
      )}
    </div>
  )
}

function NeedCard({ need, expanded, toggle, detail = false }: {
  need: Need
  expanded: boolean
  toggle: () => void
  detail?: boolean
}) {
  const label = useLabel()
  const { persona } = usePersona()
  const close = useCloseNeed()
  const [confirming, setConfirming] = useState(false)
  const closed = need.status === 'zamkniete'
  const canClose = persona?.role === 'broker' || persona?.organization?.id === need.organization.id

  return (
    <Card className="space-y-3 p-5">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Link to={`/organizacje/${need.organization.id}`} className="text-slate-600 hover:underline">
          {need.organization.name}
        </Link>
        {closed && <Badge>Zamknięte</Badge>}
      </div>
      <h2 className="text-lg font-semibold text-slate-900">
        {detail ? need.title : <Link className="underline-offset-4 hover:underline" to={needPath(need.id)}>{need.title}</Link>}
      </h2>
      {need.description && <p className="whitespace-pre-line wrap-anywhere text-sm text-slate-700">{need.description}</p>}
      {need.domains.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {need.domains.map((key) => <Badge key={key}>{label('domains', key)}</Badge>)}
        </div>
      )}
      {need.offers.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm text-slate-600">Organizacja oferuje</span>
          {need.offers.map((key) => <Badge key={key} tone="green">{label('support_needs', key)}</Badge>)}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" type="button" aria-expanded={expanded} onClick={toggle}>
          {closed ? (expanded ? 'Ukryj decyzje' : 'Pokaż decyzje') : (expanded ? 'Ukryj dopasowania' : 'Pokaż dopasowania')}
        </Button>
        {detail && !closed && <ProposeLink needId={need.id} />}
        {detail && !closed && canClose && !confirming && (
          <Button variant="ghost" onClick={() => setConfirming(true)}>Zamknij zapotrzebowanie</Button>
        )}
      </div>
      {!closed && confirming && canClose && (
        <div className="space-y-2 border-t border-slate-200 pt-3">
          <p className="text-sm">Zamknięte zgłoszenie zniknie z analizy otwartych potrzeb. Nadal będzie dostępne w zgłoszeniach.</p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => close.mutate(need.id, { onSuccess: () => setConfirming(false) })} disabled={close.isPending}>
              Potwierdź zamknięcie
            </Button>
            <Button variant="secondary" onClick={() => setConfirming(false)} disabled={close.isPending}>Anuluj</Button>
          </div>
          {close.isError && <ErrorNote error={close.error} />}
        </div>
      )}
      {expanded && <NeedMatches id={need.id} closed={closed} />}
    </Card>
  )
}


const openView = '/zapotrzebowania?widok=potrzeby'
const coveredView = '/zapotrzebowania?widok=rozwiazania'
const needPath = (id: number) => `/zapotrzebowania?potrzeba=${id}`
const textLink = 'font-semibold text-brand-700 underline-offset-4 hover:underline'
const statusLabels: Record<CoverageStatus, { label: string; tone: Tone }> = {
  fits: { label: 'Rozwiązanie pasuje', tone: 'green' },
  partial: { label: 'Pasuje częściowo', tone: 'amber' },
  no_solution: { label: 'Brak potwierdzonego rozwiązania w katalogu', tone: 'slate' },
  insufficient_data: { label: 'Za mało danych do oceny', tone: 'amber' },
}
const reviewReasons: Record<string, string> = {
  missing_description: 'W zgłoszeniu lub karcie brakuje opisu potrzebnego do oceny.',
  incomplete_review: 'Porównanie pełnych opisów jest niedostępne.',
  different_problem: 'Karta dotyczy innej czynności lub innego celu opisanego w zgłoszeniu.',
  unconfirmed_coverage: 'Funkcje lub warunki zgłoszenia są do sprawdzenia w dokumentacji rozwiązania.',
  idea_stage: 'Karta przedstawia pomysł. Działanie funkcji jest do sprawdzenia.',
  partial_functionality: 'Karta dokumentuje tylko część funkcji opisanej w zgłoszeniu. Zakres pokrycia jest do sprawdzenia.',
  conditions: 'Karta pozostawia otwarte warunki zgłoszenia.',
  described_coverage: 'Opis karty wskazuje pokrycie funkcji i warunków zgłoszenia.',
}
const conditionLabels = {
  supported: 'opis karty potwierdza',
  missing: 'karta nie spełnia warunku',
  unverified: 'do sprawdzenia',
}

function CoverageBadge({ status }: { status: CoverageStatus }) {
  const { tone, label } = statusLabels[status]
  return <Badge tone={tone}>{label}</Badge>
}

function ProposeLink({ needId }: { needId: number }) {
  return (
    <Link className="inline-flex min-h-10 items-center gap-2 rounded-sm bg-brand-700 px-4 py-2 text-sm font-semibold text-ink hover:bg-brand-800"
      to={`/zglos?potrzeba=${needId}`}>
      Zaproponuj rozwiązanie <ArrowRight className="size-4" aria-hidden="true" />
    </Link>
  )
}

function OpportunityEntry({ item }: { item: Opportunity }) {
  const organizations = [...new Map(item.sources.map((need) => [need.organization.id, need.organization])).values()]
  const pilotSources = [...new Map(item.sources.filter((need) => need.offers.includes('pierwszy_uzytkownik'))
    .map((need) => [need.organization.id, need])).values()]
  const plural = new Intl.PluralRules('pl')
  return (
    <Card className="min-w-0 px-4 py-5 sm:px-6">
      <article aria-labelledby={`opportunity-${item.id}`} className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <CoverageBadge status={item.status} />
              {item.incomplete && <Badge>Analiza niepełna</Badge>}
            </div>
            <h3 id={`opportunity-${item.id}`} className="section-title mt-2 wrap-anywhere">{item.title}</h3>
            <p className="mt-1 text-sm font-semibold text-slate-800">
              {item.organization_count === 1 ? '1 organizacja · pojedynczy sygnał' :
                `${item.organization_count} ${plural.select(item.organization_count) === 'few' ? 'organizacje' : 'organizacji'}`}
              {' · '}{item.sources.length === 1 ? '1 zgłoszenie' :
                `${item.sources.length} ${plural.select(item.sources.length) === 'few' ? 'zgłoszenia' : 'zgłoszeń'}`}
            </p>
          </div>
          {item.status !== 'fits' && <ProposeLink needId={item.id} />}
        </div>
        {item.description && <p className="max-w-[72ch] whitespace-pre-line wrap-anywhere text-slate-800">{item.description}</p>}
        <div className="grid gap-5 border-t border-slate-200 pt-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div className="min-w-0 space-y-3">
            <h4 className="font-semibold text-slate-900">Zainteresowane organizacje</h4>
            <ul className="space-y-1 text-sm text-slate-700">
              {organizations.map((org) => (
                <li key={org.id} className="wrap-anywhere">
                  <Link className="hover:underline" to={`/organizacje/${org.id}`}>{org.name}</Link>
                </li>
              ))}
            </ul>
            {pilotSources.length > 0 && (
              <p className="text-sm text-slate-700">
                Udział jako pierwszy użytkownik oferuje{' '}
                {pilotSources.map((need, i) => (
                    <span key={need.id}>{i > 0 && ', '}<Link className={textLink} to={needPath(need.id)}>{need.organization.name}</Link></span>
                  ))}
              </p>
            )}
            {item.sources.length === 1 ? (
              <Link className={`inline-flex min-h-10 items-center ${textLink}`} to={needPath(item.sources[0].id)}>Otwórz zgłoszenie</Link>
            ) : (
              <details className="text-sm">
                <summary className="cursor-pointer py-2 font-semibold text-slate-900">Zgłoszenia źródłowe ({item.sources.length})</summary>
                <ul className="space-y-2 py-1">
                  {item.sources.map((need) => (
                    <li key={need.id} className="wrap-anywhere">
                      <Link className={textLink} to={needPath(need.id)}>{need.title}</Link>
                      <p className="text-slate-600">{need.organization.name}</p>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
          <div className="min-w-0">
            <h4 className="font-semibold text-slate-900">Najbliższe alternatywy</h4>
            {item.alternatives.length === 0 && (
              <p className="mt-2 text-sm text-slate-600">{item.incomplete ? 'Brak danych do wskazania alternatyw.' :
                'W sprawdzonym katalogu brakuje dostatecznie podobnych kart.'}</p>
            )}
            <ul className="mt-1 divide-y divide-slate-200">
              {item.alternatives.map((card) => {
                const reviews = card.reviews.filter((review) => review.status !== 'fits')
                const visible = reviews.length ? reviews : card.reviews.slice(0, 1)
                const first = visible[0]
                const check = first.conditions.find(({ status }) => status !== 'supported') ?? first.conditions[0]
                const engines = [...new Set(card.reviews.flatMap((review) => Object.values(review.decisions).map(({ engine }) => engine)))]
                return (
                  <li key={card.id} className="space-y-1.5 py-2 text-sm">
                    <Link className={`block wrap-anywhere ${textLink}`} to={`/innowacje/${card.id}`}>{card.title}</Link>
                    <CoverageBadge status={card.status} />
                    <p className="text-slate-700">{reviewReasons[first.reason]}</p>
                    {check && (
                      <p className="wrap-anywhere text-slate-700">{check.requirement} · <strong>{conditionLabels[check.status]}</strong></p>
                    )}
                    {card.excerpt && (check || card.status === 'fits') && (
                      <p className="wrap-anywhere text-slate-600">Z karty: „{card.excerpt}”</p>
                    )}
                    <details>
                      <summary className="cursor-pointer py-1 font-semibold text-slate-700">Ocena zgłoszeń</summary>
                      <ul className="space-y-2 pt-1">
                        {card.reviews.map((review) => {
                          const source = item.sources.find((need) => need.id === review.need_id)
                          return (
                            <li key={review.need_id} className="wrap-anywhere">
                              <Link className={textLink} to={needPath(review.need_id)}>{source?.title}</Link>
                              <p className="text-slate-700">{reviewReasons[review.reason]}</p>
                              {review.conditions.map((check, index) => (
                                <p key={index} className="text-slate-700">{check.requirement} · {conditionLabels[check.status]}</p>
                              ))}
                            </li>
                          )
                        })}
                      </ul>
                      {engines.length > 0 && <p className="mt-2 text-xs text-slate-600">Propozycja modelu · {engines.join(', ')}</p>}
                      {card.source_url && <a className={textLink} href={card.source_url}>Źródło karty</a>}
                    </details>
                  </li>
                )
              })}
            </ul>
          </div>
        </div>
      </article>
    </Card>
  )
}

function Opportunities({ covered }: { covered: boolean }) {
  const data = useOpportunities()
  const items = data.data?.items.filter((item) => (item.status === 'fits') === covered) ?? []
  return (
    <section aria-labelledby="results" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <h2 id="results" className="section-title">{covered ? 'Potrzeby z rozwiązaniem' : 'Potrzeby bez rozwiązania'}</h2>
        <Button variant="secondary" disabled={data.isFetching} onClick={() => void data.refetch()}>Odśwież analizę</Button>
      </div>
      <p className="max-w-[72ch] text-sm text-slate-700">
        {covered ? 'Według analizy opisów karty pokrywają wszystkie zgłoszenia w danej grupie.' :
          'Przejrzyj otwarte problemy instytucji, warunki zgłoszeń i dostępne alternatywy.'}
      </p>
      {data.isFetching && <Loading label={data.data ? 'Odświeżanie analizy…' : 'Porównywanie zgłoszeń z katalogiem…'} />}
      {data.isError && <ErrorNote error={data.error} />}
      {data.data?.incomplete && (
        <p role="status" className="rounded-sm border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Analiza niepełna. Brakuje danych lub niektórych porównań.
          {data.data.missing_need_embeddings > 0 && ` Zgłoszenia bez embeddingu: ${data.data.missing_need_embeddings}.`}
          {data.data.missing_card_embeddings > 0 && ` Aktywne karty bez embeddingu: ${data.data.missing_card_embeddings}.`}
        </p>
      )}
      {data.data && items.length === 0 && (
        <p className="border-t border-slate-200 py-4 text-slate-700">
          {covered ? 'Brak otwartych potrzeb z potwierdzonym pokryciem w katalogu.' : 'Brak otwartych potrzeb w tym widoku.'}
        </p>
      )}
      {items.map((item) => <OpportunityEntry key={item.id} item={item} />)}
    </section>
  )
}

function NeedDetail({ id }: { id: number }) {
  const need = useNeed(id)
  const [expanded, setExpanded] = useState(false)
  if (need.isPending) return <Loading label="Wczytywanie zgłoszenia…" />
  if (need.isError) return <ErrorNote error={need.error} />
  return (
    <div className="max-w-3xl">
      <NeedCard need={need.data} expanded={expanded} toggle={() => setExpanded(!expanded)} detail />
    </div>
  )
}

function PublishedNeeds({ description, adding }: { description: string; adding: boolean }) {
  const [offset, setOffset] = useState(0)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const needs = useNeeds(offset)
  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className={adding ? 'lg:col-start-2 lg:row-start-1' : 'order-2'}>
        <NeedForm description={description} focused={adding} onCreated={(id) => {
          setOffset(0)
          setExpandedId(id)
        }} />
      </div>
      <div className="min-w-0 space-y-4">
        {needs.isPending && <Loading />}
        {needs.isError && <ErrorNote error={needs.error} />}
        {needs.data?.items.map((need) => (
          <NeedCard key={need.id} need={need} expanded={need.id === expandedId}
            toggle={() => setExpandedId(need.id === expandedId ? null : need.id)} />
        ))}
        {needs.data?.total === 0 && <Card className="p-5 text-sm text-slate-600">Brak zapotrzebowań.</Card>}
        {needs.data && needs.data.total > needs.data.limit && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" disabled={!offset} onClick={() => setOffset(offset - needs.data.limit)}>
              Poprzednia strona
            </Button>
            <Button variant="secondary" disabled={offset + needs.data.limit >= needs.data.total}
              onClick={() => setOffset(offset + needs.data.limit)}>
              Następna strona
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Needs() {
  const location = useLocation()
  const [params] = useSearchParams()
  const view = params.get('widok')
  const needId = Number(params.get('potrzeba'))
  const detail = Number.isSafeInteger(needId) && needId > 0
  const adding = params.get('dodaj') === '1'
  const description = adding && typeof location.state?.description === 'string' ? location.state.description : ''
  const tabs = [
    { key: null, label: 'Wszystkie zgłoszenia', path: '/zapotrzebowania' },
    { key: 'potrzeby', label: 'Potrzeby bez rozwiązania', path: openView },
    { key: 'rozwiazania', label: 'Potrzeby z rozwiązaniem', path: coveredView },
  ]
  return (
    <div className="space-y-5">
      <header>
        <h1 className="page-title">Zapotrzebowania</h1>
        <p className="mt-2 text-slate-600">Znajdź problem do rozwiązania lub opublikuj potrzebę swojej organizacji.</p>
      </header>
      <nav aria-label="Widoki zapotrzebowań" className="flex flex-wrap gap-x-2 border-y border-slate-200 sm:gap-x-5">
        {tabs.map(({ key, label, path }) => (
          <Link key={path} to={path} aria-current={view === key && !detail ? 'page' : undefined}
            className="inline-flex min-h-11 items-center border-b-2 border-transparent py-2 text-sm font-semibold text-slate-700 hover:text-brand-700 aria-[current=page]:border-brand-700 aria-[current=page]:text-brand-700">
            {label}
          </Link>
        ))}
      </nav>
      {detail ? <NeedDetail key={needId} id={needId} /> :
        view === 'potrzeby' || view === 'rozwiazania' ? <Opportunities covered={view === 'rozwiazania'} /> :
          <PublishedNeeds key={location.key} description={description} adding={adding} />}
    </div>
  )
}

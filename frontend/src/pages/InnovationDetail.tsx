import { ArrowLeft, ArrowUpRight } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useMoveInnovation } from '../api/broker.ts'
import { useInnovation, useLabel, useMeta } from '../api/hooks.ts'
import { OriginBadges, sourceLabel } from '../components/InnovationCard.tsx'
import AssessmentPanel from '../components/panels/AssessmentPanel.tsx'
import MatchesPanel from '../components/panels/MatchesPanel.tsx'
import PathPanel from '../components/panels/PathPanel.tsx'
import SimilarPanel from '../components/panels/SimilarPanel.tsx'
import SocialPanel from '../components/panels/SocialPanel.tsx'
import { Badge, Button, Card, ErrorNote, Loading, inputClass } from '../components/ui.tsx'
import { usePersona } from '../lib/persona.tsx'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-slate-200 pt-4">
      <h3 className="technical-label">{title}</h3>
      <div className="mt-2 max-w-[70ch] wrap-anywhere whitespace-pre-line leading-relaxed text-slate-800">{children}</div>
    </section>
  )
}

const formatDate = (iso: string) =>
  new Date(iso).toLocaleString('pl-PL', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })

function StatusEditor({ id, current }: { id: number; current: string }) {
  const [draft, setDraft] = useState<string | null>(null)
  const status = draft ?? current
  const { data: meta } = useMeta()
  const move = useMoveInnovation()
  if (!meta) return null

  return (
    <form
      className="space-y-2 rounded-sm border border-slate-200 bg-shell p-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (status === current || move.isPending) return
        move.mutate({ id, status }, { onSuccess: () => setDraft(null) })
      }}
    >
      <label htmlFor="innovation-status" className="block text-sm font-medium text-slate-700">Zmień status</label>
      <div className="flex flex-wrap gap-2">
        <select
          id="innovation-status"
          value={status}
          onChange={(event) => setDraft(event.target.value)}
          disabled={move.isPending}
          className={`${inputClass} min-h-11 min-w-0 sm:w-auto`}
        >
          {meta.statuses.map(({ key, label }) => <option key={key} value={key}>{label}</option>)}
        </select>
        <Button type="submit" disabled={status === current || move.isPending}>
          {move.isPending ? 'Zapisywanie…' : 'Zapisz status'}
        </Button>
      </div>
      {move.error && <ErrorNote error={move.error} />}
      {move.isSuccess && draft === null && <p role="status" className="text-sm text-emerald-700">Status zapisany.</p>}
    </form>
  )
}

export default function InnovationDetail() {
  const id = Number(useParams().id)
  const { persona } = usePersona()
  const { data: innovation, isPending, error, refetch } = useInnovation(id, persona?.id ?? null)
  const label = useLabel()
  const { hash } = useLocation()
  const detailReady = Boolean(innovation) && !error
  const detail = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!detailReady || !hash || !detail.current) return
    const section = document.getElementById(hash.slice(1))
    if (!section) return

    section.focus({ preventScroll: true })
    section.scrollIntoView()

    // Asynchronous panels above the destination can shift it after navigation.
    const observer = new ResizeObserver(() => section.scrollIntoView())
    observer.observe(detail.current)
    const events = new AbortController()
    const stop = () => {
      observer.disconnect()
      events.abort()
    }
    for (const event of ['wheel', 'touchstart', 'pointerdown', 'keydown']) {
      window.addEventListener(event, stop, { passive: true, signal: events.signal })
    }
    return stop
  }, [id, hash, detailReady])

  if (error) return (
    <div className="space-y-2">
      <ErrorNote error={error} />
      <Button type="button" variant="secondary" onClick={() => void refetch()}>Spróbuj ponownie</Button>
    </div>
  )
  if (isPending || !innovation) return <Loading />
  const org = innovation.organization

  return (
    <div ref={detail} className="min-w-0 space-y-4 sm:space-y-7">
      <Link to="/" className="inline-flex min-h-9 items-center gap-2 text-sm font-semibold text-slate-600 hover:text-brand-700">
        <ArrowLeft className="size-4" aria-hidden="true" /> Radar
      </Link>
      <header className="grid border-y border-slate-200 lg:grid-cols-[minmax(0,1fr)_minmax(17rem,23rem)]">
        <div className="min-w-0 py-5 sm:py-7 lg:pr-10">
          <div className="flex flex-wrap gap-1.5">
            <OriginBadges innovation={innovation} />
            <Badge tone="amber">{label('statuses', innovation.status)}</Badge>
            {innovation.kind && <Badge tone="brand">{label('innovation_kinds', innovation.kind)}</Badge>}
            {innovation.stage && <Badge tone="green">{label('stages', innovation.stage)}</Badge>}
          </div>
          <h1 className="page-title mt-3 max-sm:text-[2.625rem] sm:mt-4">{innovation.title}</h1>
          {innovation.summary && <p className="mt-3 max-w-[68ch] wrap-anywhere text-base leading-relaxed text-slate-600 sm:text-lg">{innovation.summary}</p>}
        </div>
        <dl className="grid content-center gap-3 border-t border-slate-200 bg-surface px-4 py-4 min-[360px]:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] sm:px-6 lg:grid-cols-1 lg:gap-4 lg:border-t-0 lg:border-l">
          <div>
            <dt className="technical-label">Pochodzenie</dt>
            {innovation.source_url ? (
              <dd className="mt-1">
                <a
                  href={innovation.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex min-h-9 items-center gap-1.5 text-sm font-semibold text-brand-700 underline-offset-4 hover:underline"
                >
                  {sourceLabel(innovation.source_name) ?? 'Źródło'} <ArrowUpRight className="size-4 shrink-0" aria-hidden="true" />
                </a>
                {org && <p className="wrap-anywhere text-sm text-slate-600">{org.name}</p>}
              </dd>
            ) : <dd className="mt-1 text-sm text-slate-700">{org?.name ?? 'Organizacja nieznana'}</dd>}
          </div>
          <div className="border-t border-slate-200 pt-3 min-[360px]:border-t-0 min-[360px]:border-l min-[360px]:pt-0 min-[360px]:pl-3 lg:border-t lg:border-l-0 lg:pt-3 lg:pl-0">
            <dt className="technical-label">Ocena potencjału</dt>
            <dd className="mt-1">
              <a href="#ocena" className="inline-flex min-h-8 items-baseline gap-1 rounded-sm text-sm text-slate-700 hover:text-brand-700 hover:underline">
                {innovation.score == null ? 'Brak oceny' : (
                  <><span className="font-display text-4xl leading-none font-semibold tabular-nums text-brand-700">{Math.round(innovation.score)}</span><span>/100</span></>
                )}
              </a>
              <p className="mt-1 text-xs leading-snug text-slate-600">Ważony wynik udokumentowanych kryteriów. <a className="underline" href="#ocena">Zobacz przesłanki</a></p>
            </dd>
          </div>
        </dl>
      </header>

      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(17rem,23rem)] lg:gap-8">
        <div className="min-w-0 space-y-5">
          {persona?.role === 'broker' && (
            <StatusEditor key={id} id={id} current={innovation.status} />
          )}
          <section className="space-y-4">
            <h2 className="section-title">Opis innowacji</h2>
            {innovation.problem && <Section title="Problem">{innovation.problem}</Section>}
            {innovation.solution && <Section title="Rozwiązanie">{innovation.solution}</Section>}
            {innovation.results && <Section title="Efekty i dowody">{innovation.results}</Section>}
            {innovation.description && <Section title="Opis">{innovation.description}</Section>}
            {innovation.support_needs.length > 0 && (
              <Section title="Czego potrzebują twórcy">
                <div className="flex flex-wrap gap-2">
                  {innovation.support_needs.map((key) => (
                    <Badge key={key} tone="amber">
                      {label('support_needs', key)}
                    </Badge>
                  ))}
                </div>
              </Section>
            )}
          </section>
          <div id="ocena" tabIndex={-1} className="scroll-mt-4 lg:scroll-mt-28">
            <AssessmentPanel innovation={innovation} />
          </div>
          <div id="sciezka" tabIndex={-1} className="scroll-mt-4 lg:scroll-mt-28">
            <PathPanel innovation={innovation} />
          </div>
          <div id="dopasowania" tabIndex={-1} className="scroll-mt-4 lg:scroll-mt-28">
            <MatchesPanel innovation={innovation} />
          </div>
        </div>

        <aside className="min-w-0 space-y-6">
          <Card className="p-5">
            <h2 className="technical-label">Twórcy</h2>
            {org ? (
              <Link to={`/organizacje/${org.id}`} className="mt-2 block font-medium text-slate-900 hover:text-brand-700">
                {org.name}
              </Link>
            ) : (
              <p className="mt-2 font-medium text-slate-900">Organizacja nieznana</p>
            )}
            <p className="text-sm text-slate-500">
              {[org && label('org_kinds', org.kind), org?.city, org?.region].filter(Boolean).join(' · ')}
            </p>
            {innovation.author && (
              <p className="mt-3 text-sm text-slate-700">
                {innovation.author.name}
                {innovation.author.title && <span className="block text-xs text-slate-500">{innovation.author.title}</span>}
              </p>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              {innovation.domains.map((key) => (
                <Badge key={key}>{label('domains', key)}</Badge>
              ))}
            </div>
          </Card>

          <div id="potwierdzenie-profilu" tabIndex={-1} className="scroll-mt-4 lg:scroll-mt-28">
            <SocialPanel innovation={innovation} />
          </div>
          <SimilarPanel innovation={innovation} />

          <Card className="p-5">
            <h2 className="technical-label">Historia</h2>
            <ol className="mt-3 space-y-3">
              {innovation.events.map((event) => (
                <li key={event.id} className="border-t border-slate-200 pt-2">
                  <p className="text-sm text-slate-800">{event.message ?? event.type}</p>
                  <p className="text-xs text-slate-500">
                    {event.actor} · {formatDate(event.created_at)}
                  </p>
                </li>
              ))}
            </ol>
          </Card>
        </aside>
      </div>
    </div>
  )
}

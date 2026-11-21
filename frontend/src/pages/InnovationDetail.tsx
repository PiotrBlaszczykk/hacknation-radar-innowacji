import { ExternalLink } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useInnovation, useLabel } from '../api/hooks.ts'
import { OriginBadge } from '../components/InnovationCard.tsx'
import AssessmentPanel from '../components/panels/AssessmentPanel.tsx'
import MatchesPanel from '../components/panels/MatchesPanel.tsx'
import PathPanel from '../components/panels/PathPanel.tsx'
import SimilarPanel from '../components/panels/SimilarPanel.tsx'
import SocialPanel from '../components/panels/SocialPanel.tsx'
import { Badge, Card, ErrorNote, Loading } from '../components/ui.tsx'
import { usePersona } from '../lib/persona.tsx'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <div className="mt-1.5 text-sm leading-relaxed text-slate-800">{children}</div>
    </div>
  )
}

const formatDate = (iso: string) =>
  new Date(iso).toLocaleString('pl-PL', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })

export default function InnovationDetail() {
  const id = Number(useParams().id)
  const { persona } = usePersona()
  const { data: innovation, isPending, error } = useInnovation(id, persona?.id ?? null)
  const label = useLabel()
  const { hash } = useLocation()
  const detailReady = Boolean(innovation) && !error

  useEffect(() => {
    if (detailReady && hash) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [id, hash, detailReady])

  if (error) return <ErrorNote error={error} />
  if (isPending || !innovation) return <Loading />
  const org = innovation.organization

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-6">
        <Card className="space-y-5 p-6">
          <div className="flex flex-wrap gap-2">
            <OriginBadge innovation={innovation} />
            <Badge tone="amber">{label('statuses', innovation.status)}</Badge>
            {innovation.kind && <Badge tone="brand">{label('innovation_kinds', innovation.kind)}</Badge>}
            {innovation.stage && <Badge tone="green">{label('stages', innovation.stage)}</Badge>}
          </div>
          <div>
            <h1 className="text-2xl font-semibold leading-tight text-slate-900">{innovation.title}</h1>
            {innovation.summary && <p className="mt-2 text-slate-600">{innovation.summary}</p>}
          </div>
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
          {innovation.source_url && (
            <a
              href={innovation.source_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline"
            >
              Źródło <ExternalLink className="size-3.5" />
            </a>
          )}
        </Card>
        <div id="ocena" className="scroll-mt-20">
          <AssessmentPanel innovation={innovation} />
        </div>
        <div id="sciezka" className="scroll-mt-20">
          <PathPanel innovation={innovation} />
        </div>
        <div id="dopasowania" className="scroll-mt-20">
          <MatchesPanel innovation={innovation} />
        </div>
      </div>

      <aside className="space-y-6">
        <Card className="p-5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Twórcy</h3>
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

        <div id="potwierdzenie-profilu" className="scroll-mt-20">
          <SocialPanel innovation={innovation} />
        </div>
        <SimilarPanel innovation={innovation} />

        <Card className="p-5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Historia</h3>
          <ol className="mt-3 space-y-3">
            {innovation.events.map((event) => (
              <li key={event.id} className="border-l-2 border-brand-100 pl-3">
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
  )
}

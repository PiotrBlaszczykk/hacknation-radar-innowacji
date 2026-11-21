import { ArrowUp, ArrowUpRight, Heart, MessageCircle, Radar } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useToggleBump, type Engagement } from '../api/feed.ts'
import { useLabel } from '../api/hooks.ts'
import type { Innovation } from '../api/types.ts'
import { usePersona } from '../lib/persona.tsx'
import { Badge, Button, ErrorNote, cx } from './ui.tsx'

export function sourceLabel(source: string | null) {
  switch (source) {
    case 'radon_projekty': return 'RAD-on'
    case 'strony_instytucji': return 'Strona instytucji'
    case 'uprp_bup': return 'UPRP · Biuletyn Urzędu Patentowego'
    case 'epo_eps': return 'EPO · European Publication Server'
    case 'interreg': return 'Interreg'
    case 'ncbr': return 'NCBR'
    case 'crossref': return 'Crossref'
    case 'przyklad_biuletyn': return 'Przykładowy biuletyn'
    default: return null
  }
}

export function OriginBadges({ innovation }: { innovation: Innovation }) {
  const radar = innovation.origin === 'radar'
  const source = sourceLabel(innovation.source_name)
  const example = innovation.source_name?.startsWith('przyklad_')
    || innovation.organization?.description?.includes('Dane przykładowe.')

  return (
    <>
      {radar ? (
        <Badge tone="violet">
          <Radar className="size-3 shrink-0" aria-hidden="true" />
          {source ? `Radar · ${source}` : 'Wykryta przez radar'}
        </Badge>
      ) : <Badge>Zgłoszenie</Badge>}
      {radar && !innovation.claimed && <Badge tone="amber">Czeka na potwierdzenie twórcy</Badge>}
      {example && <Badge tone="amber">Dane przykładowe</Badge>}
    </>
  )
}

function FeedActions({ id, engagement }: { id: number; engagement: Engagement }) {
  const { persona } = usePersona()
  const bump = useToggleBump(id, persona?.id ?? null)

  return (
    <div className="mt-4 border-t border-slate-100 pt-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-600">
        <Button
          type="button"
          variant="secondary"
          className={cx('px-2.5 py-1.5 text-xs', engagement.bumped && 'border-brand-500 text-brand-700')}
          title={persona ? undefined : 'Wybierz personę, aby podbić wpis'}
          aria-pressed={engagement.bumped}
          disabled={!persona || bump.isPending}
          onClick={() => bump.mutate()}
        >
          <ArrowUp className="size-4" aria-hidden="true" />
          {engagement.bumped ? 'Podbito' : 'Podbij'} · {engagement.bumps}
        </Button>
        <span className="inline-flex items-center gap-1.5"><Heart className="size-4" aria-hidden="true" /> Zainteresowania · {engagement.interest_count}</span>
        <span className="inline-flex items-center gap-1.5"><MessageCircle className="size-4" aria-hidden="true" /> Komentarze · {engagement.comments_count}</span>
      </div>
      {bump.error && <div className="mt-2"><ErrorNote error={bump.error} /></div>}
    </div>
  )
}

type CardInnovation = Innovation & { why?: string } & (Engagement | Partial<Record<keyof Engagement, undefined>>)

export default function InnovationCard({ innovation }: { innovation: CardInnovation }) {
  const label = useLabel()
  const org = innovation.organization
  const taxonomy = [
    innovation.kind && label('innovation_kinds', innovation.kind),
    innovation.stage && label('stages', innovation.stage),
    ...innovation.domains.map((key) => label('domains', key)),
  ].filter(Boolean).join(' · ')

  return (
    <article className="flex h-full min-w-0 flex-col border-t border-slate-200 px-1 py-4 sm:px-4 lg:even:border-l lg:even:pl-6 xl:py-5">
      <h3 className="font-display text-3xl leading-none font-semibold text-slate-900">
        <Link to={`/innowacje/${innovation.id}`} className="group flex items-start justify-between gap-2 rounded-sm hover:text-brand-700">
          <span className="line-clamp-2 wrap-anywhere">{innovation.title}</span>
          <ArrowUpRight className="mt-1 size-4 shrink-0 text-slate-500 group-hover:text-brand-700" aria-hidden="true" />
        </Link>
      </h3>
      {innovation.summary && <p className="mt-2 line-clamp-3 wrap-anywhere leading-snug text-slate-600">{innovation.summary}</p>}

      <div className="mt-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="line-clamp-2 wrap-anywhere text-sm font-semibold text-slate-800">{org?.name ?? 'Organizacja nieznana'}</p>
          <p className="text-xs text-slate-500">
            {[org && label('org_kinds', org.kind), org?.city, innovation.author?.name].filter(Boolean).join(' · ')}
          </p>
        </div>
        <div className="shrink-0 text-right text-xs text-slate-500">
          {innovation.score == null ? 'Brak oceny' : (
            <>
              <span className="block">Potencjał</span>
              <span className="font-display text-3xl leading-none font-semibold tabular-nums text-brand-700">{Math.round(innovation.score)}</span>
              <span className="pl-0.5 tabular-nums">/100</span>
            </>
          )}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        <OriginBadges innovation={innovation} />
        {innovation.novelty != null && (
          <Badge tone="violet">Świeżość {Math.round(innovation.novelty)}/100</Badge>
        )}
      </div>
      {taxonomy && <p className="mt-2 text-sm text-slate-500">{taxonomy}</p>}

      {innovation.why && (
        <div className="mt-auto pt-4 text-sm leading-snug text-slate-600">
          <strong className="font-semibold text-slate-800">Dlaczego to widzisz?</strong> {innovation.why}
        </div>
      )}
      {innovation.bumps !== undefined && <FeedActions id={innovation.id} engagement={innovation} />}
    </article>
  )
}

import { ArrowUp, Building2, Heart, MessageCircle, Radar, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useToggleBump, type Engagement } from '../api/feed.ts'
import { useLabel } from '../api/hooks.ts'
import type { Innovation } from '../api/types.ts'
import { usePersona } from '../lib/persona.tsx'
import { Badge, Button, Card, ErrorNote, cx } from './ui.tsx'

export function OriginBadge({ innovation }: { innovation: Pick<Innovation, 'origin' | 'claimed'> }) {
  if (innovation.origin !== 'radar') return null
  return (
    <Badge tone="violet">
      <Radar className="size-3" />
      {innovation.claimed ? 'Wykryta przez radar' : 'Wykryta przez radar, czeka na potwierdzenie twórcy'}
    </Badge>
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

  return (
    <Card className="p-5">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-500">
          <Building2 className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-900">{org?.name ?? 'Organizacja nieznana'}</p>
          <p className="text-xs text-slate-500">
            {[org && label('org_kinds', org.kind), org?.city, innovation.author?.name].filter(Boolean).join(' · ')}
          </p>
        </div>
        {innovation.score !== null && (
          <span className="shrink-0 text-right leading-tight" title="Ocena potencjału w skali 0–100">
            <span className="block text-xl font-semibold text-brand-700">{Math.round(innovation.score)}</span>
            <span className="block text-[11px] uppercase tracking-wide text-slate-500">potencjał</span>
          </span>
        )}
      </div>

      <Link to={`/innowacje/${innovation.id}`} className="mt-4 block">
        <h2 className="text-lg font-semibold leading-snug text-slate-900 hover:text-brand-700">{innovation.title}</h2>
      </Link>
      {innovation.summary && <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{innovation.summary}</p>}

      <div className="mt-4 flex flex-wrap gap-2">
        <OriginBadge innovation={innovation} />
        {innovation.novelty != null && (
          <Badge tone="violet">Świeżość {Math.round(innovation.novelty)}/100</Badge>
        )}
        {innovation.kind && <Badge tone="brand">{label('innovation_kinds', innovation.kind)}</Badge>}
        {innovation.stage && <Badge tone="green">{label('stages', innovation.stage)}</Badge>}
        {innovation.domains.map((key) => (
          <Badge key={key}>{label('domains', key)}</Badge>
        ))}
      </div>

      {innovation.why && (
        <p className="mt-4 flex items-start gap-2 rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-700">
          <Sparkles className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span><strong className="font-semibold">Dlaczego to widzisz?</strong> {innovation.why}</span>
        </p>
      )}
      {innovation.bumps !== undefined && <FeedActions id={innovation.id} engagement={innovation} />}
    </Card>
  )
}

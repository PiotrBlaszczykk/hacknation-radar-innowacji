import { UserRound, Repeat2, ArrowUpRight, Building2, Heart, MessageCircle, Radar } from 'lucide-react'
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client.ts'
import { useCreateInteraction } from '../api/social.ts'
import { Link } from 'react-router-dom'
import { useToggleBump, type Engagement } from '../api/feed.ts'
import { useLabel } from '../api/hooks.ts'
import type { Innovation } from '../api/types.ts'
import { usePersona } from '../lib/persona.tsx'
import { Badge, ErrorNote, cx } from './ui.tsx'

function Avatar({ kind, small = false }: { kind: 'person' | 'organization' | 'radar'; small?: boolean }) {
  const Icon = kind === 'person' ? UserRound : kind === 'organization' ? Building2 : Radar
  return <span aria-hidden="true" className={cx('inline-grid shrink-0 place-items-center align-middle', small ? 'size-6' : 'size-10',
    kind === 'person' ? 'rounded-full bg-violet-100 text-violet-800' : 'rounded-md bg-brand-50 text-brand-700')}>
    <Icon className={small ? 'size-4' : 'size-5'} />
  </span>
}

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
  const client = useQueryClient()
  const like = useMutation({
    mutationFn: () => api(`/innovations/${id}/interactions`, { method: 'POST', body: JSON.stringify({ type: 'serce' }) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['feed'] }),
  })
  const comment = useCreateInteraction(id, persona?.id ?? null)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const action = 'inline-flex min-h-11 items-center gap-1.5 px-1 font-semibold tabular-nums disabled:opacity-60'
  return (
    <div className="mt-3 border-t border-slate-200 text-sm text-slate-600">
      <div className="flex items-center gap-5">
        <button type="button" className={action} aria-label="Polubienie" aria-pressed={engagement.liked}
          disabled={!persona || like.isPending} onClick={() => like.mutate()}>
          <Heart className={cx('size-5', engagement.liked && 'fill-current text-rose-600')} />{engagement.likes}
        </button>
        <button type="button" className={action} aria-label="Repost" aria-pressed={engagement.bumped}
          disabled={!persona || bump.isPending} onClick={() => bump.mutate()}>
          <Repeat2 className={cx('size-5', engagement.bumped && 'text-brand-700')} />{engagement.bumps}
        </button>
        <button type="button" className={action} aria-expanded={open} onClick={() => setOpen(!open)}>
          <MessageCircle className="size-4" />{engagement.comments_count} · Skomentuj
        </button>
      </div>
      {engagement.comments?.map((c, index) => (
        <p key={index} className="my-2 border-l-2 border-slate-200 pl-3 wrap-anywhere">
          <Avatar kind="person" small /> <strong className="mr-2 text-slate-900">{c.name}</strong>{c.body}
        </p>
      ))}
      {engagement.comments_count > 2 && <Link className="underline" to={`/innowacje/${id}#komentarze`}>Wszystkie komentarze ({engagement.comments_count})</Link>}
      {open && <form className="mt-2 flex flex-wrap gap-2" onSubmit={event => {
        event.preventDefault()
        if (draft.trim()) comment.mutate({ type: 'komentarz', body: draft.trim() }, { onSuccess: () => setDraft('') })
      }}>
        <input aria-label="Twój komentarz" placeholder="Dodaj komentarz…" maxLength={1000} required
          className="min-w-0 flex-1 rounded border border-slate-200 px-3" value={draft} onChange={e => setDraft(e.target.value)} />
        <button className={action} disabled={!persona || !draft.trim() || comment.isPending}>Opublikuj</button>
      </form>}
      {(like.error || bump.error || comment.error) && <ErrorNote error={like.error || bump.error || comment.error} />}
    </div>
  )
}

function FollowButton({ kind, id, name, active }: { kind: string; id: number; name: string; active: boolean }) {
  const client = useQueryClient()
  const change = useMutation({
    mutationFn: () => api(`/following/${kind}/${id}`, { method: 'PUT', body: JSON.stringify({ active: !active }) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['feed'] }),
  })
  return <><button type="button" aria-label={`Obserwuj: ${name}`} aria-pressed={active} disabled={change.isPending}
    onClick={() => change.mutate()} className="ml-2 text-xs font-semibold text-brand-700 hover:underline">
    {active ? 'Obserwujesz' : '+ Obserwuj'}
  </button>{change.error && <ErrorNote error={change.error} />}</>
}

type CardInnovation = Innovation & { why?: string } & (Engagement | Partial<Record<keyof Engagement, undefined>>)
const feedDate = new Intl.DateTimeFormat('pl-PL', { day: 'numeric', month: 'short', year: 'numeric' })

export default function InnovationCard({ innovation, showReason = false }: { innovation: CardInnovation; showReason?: boolean }) {
  const label = useLabel()
  const { persona } = usePersona()
  const org = innovation.organization
  const author = innovation.author?.name
  const source = sourceLabel(innovation.source_name)
  const radar = innovation.origin === 'radar'
  const example = innovation.source_name?.startsWith('przyklad_') || org?.description?.includes('Dane przykładowe.')
  const taxonomy = [
    innovation.kind && label('innovation_kinds', innovation.kind),
    innovation.stage && label('stages', innovation.stage),
    ...innovation.domains.map((key) => label('domains', key)),
  ].filter(Boolean).join(' · ')

  return (
    <article className="flex min-w-0 flex-col bg-surface px-4 pt-4 pb-3 sm:px-5 sm:pt-5">
      {innovation.network_activity ? <p className="mb-2 flex items-center gap-2 text-sm">
        <Avatar kind="person" small />{innovation.network_activity.name} · {{serce: 'Polubienie', podbicie: 'Repost', komentarz: 'Komentarz'}[innovation.network_activity.type]}
      </p> : innovation.repost_by && <p className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-600"><Avatar kind="person" small /> Repost · {innovation.repost_by}</p>}
      <header className="flex min-w-0 items-start gap-3">
        <Avatar kind={author ? 'person' : org ? 'organization' : 'radar'} />
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 wrap-anywhere text-[.9375rem] leading-snug font-bold text-slate-900">
            {!author && org ? (
              <Link to={`/organizacje/${org.id}`} className="hover:text-brand-700 hover:underline">{org.name}</Link>
            ) : author ?? (radar ? 'Wihajster' : 'Organizacja nieznana')}
            {persona && innovation.author && innovation.author.id !== persona.id && innovation.bumps !== undefined && <FollowButton kind="person" id={innovation.author.id} name={innovation.author.name} active={innovation.follows_author} />}
          </p>
          <p className="mt-0.5 flex flex-wrap items-baseline gap-x-1.5 text-sm leading-snug text-slate-500">
            {author && org && <span>{org.name}</span>}
            {persona && org && innovation.bumps !== undefined && <FollowButton kind="organization" id={org.id} name={org.name} active={innovation.follows_org} />}
            <span>{radar ? (source ?? 'Wykryta przez radar') : 'Zgłoszenie'}</span>
            {innovation.created_at && <time dateTime={innovation.created_at}>· {feedDate.format(new Date(innovation.created_at))}</time>}
            {example && <span>· Dane przykładowe</span>}
          </p>
        </div>
      </header>

      <h3 className="mt-3 font-display text-[1.85rem] leading-[1.02] font-bold text-slate-900 sm:text-[2rem]">
        <Link to={`/innowacje/${innovation.id}`} className="group flex items-start justify-between gap-2 rounded-sm hover:text-brand-700">
          <span className="line-clamp-2 wrap-anywhere">{innovation.title}</span>
          <ArrowUpRight className="mt-1 size-4 shrink-0 text-slate-500 group-hover:text-brand-700" aria-hidden="true" />
        </Link>
      </h3>
      {innovation.summary && <p className="mt-2 line-clamp-3 max-w-[69ch] wrap-anywhere leading-snug text-slate-700">{innovation.summary}</p>}
      {taxonomy && <p className="mt-3 text-sm leading-snug text-slate-500">{taxonomy}</p>}

      <ul className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm leading-snug text-slate-600">
        <li>{innovation.score == null ? 'Brak wyniku potencjału' : <>Potencjał <strong className="tabular-nums text-brand-700">{Math.round(innovation.score)}/100</strong></>}</li>
        {innovation.novelty != null && <li>Świeżość <strong className="tabular-nums text-slate-800">{Math.round(innovation.novelty)}/100</strong></li>}
        {radar && !innovation.claimed && <li>Czeka na potwierdzenie twórcy</li>}
      </ul>

      {innovation.why && (showReason ? (
        <p className="mt-2 text-sm leading-snug text-slate-700">{innovation.why}</p>
      ) : (
        <details className="mt-1 text-sm leading-snug text-slate-600">
          <summary className="w-fit cursor-pointer py-1 font-semibold text-slate-700 hover:text-brand-700">Dlaczego to widzisz?</summary>
          <p className="pb-2">{innovation.why}</p>
        </details>
      ))}
      {innovation.bumps !== undefined && <FeedActions key={persona?.id} id={innovation.id} engagement={innovation} />}
    </article>
  )
}

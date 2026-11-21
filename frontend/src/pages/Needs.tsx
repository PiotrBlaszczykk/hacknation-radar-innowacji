import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useLabel, useMeta } from '../api/hooks.ts'
import { matchStrength, useCreateNeed, useNeedMatches, useNeeds } from '../api/matching.ts'
import type { Need, NeedInput } from '../api/matching.ts'
import { Badge, Button, Card, ChipSelect, ErrorNote, Field, inputClass, Loading } from '../components/ui.tsx'
import { usePersona } from '../lib/persona.tsx'

const emptyInput: NeedInput = { title: '', description: '', domains: [], offers: [] }

function NeedForm({ onCreated }: { onCreated: (id: number) => void }) {
  const { persona } = usePersona()
  const meta = useMeta()
  const create = useCreateNeed()
  const [input, setInput] = useState(emptyInput)
  const organization = persona?.organization

  function publish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!organization || !input.title.trim() || !input.description.trim()) return
    create.mutate(input, {
      onSuccess: (need) => {
        setInput(emptyInput)
        onCreated(need.id)
      },
    })
  }

  return (
    <Card className="p-5">
      <h2 className="section-title">Dodaj zapotrzebowanie</h2>
      {organization ? (
        <p className="mt-1 text-sm text-slate-600">Publikujesz w imieniu organizacji {organization.name}.</p>
      ) : (
        <p className="mt-1 text-sm text-slate-600">Wybierz w nagłówku osobę przypisaną do organizacji.</p>
      )}
      <form onSubmit={publish} className="mt-4 space-y-4">
        <Field label="Tytuł">
          <input
            className={inputClass}
            value={input.title}
            onChange={(event) => setInput({ ...input, title: event.target.value })}
            maxLength={400}
            required
          />
        </Field>
        <Field label="Opis">
          <textarea
            className={inputClass}
            value={input.description}
            onChange={(event) => setInput({ ...input, description: event.target.value })}
            rows={3}
            required
          />
        </Field>
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
        <Button type="submit" disabled={create.isPending || !organization || !meta.data}>
          {create.isPending ? 'Publikowanie i szukanie dopasowań…' : 'Opublikuj zapotrzebowanie'}
        </Button>
        {create.isSuccess && <p role="status" className="text-sm text-emerald-700">Zapotrzebowanie opublikowane.</p>}
      </form>
    </Card>
  )
}

function NeedMatches({ id }: { id: number }) {
  const matches = useNeedMatches(id)
  if (matches.isPending) return <Loading label="Wczytywanie dopasowań…" />
  if (matches.isError) return <ErrorNote error={matches.error} />

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-slate-900">Dopasowane innowacje</h3>
      {matches.data.items.length ? (
        <ol className="divide-y divide-slate-200">
          {matches.data.items.map((match) => (
            <li key={match.id} className="space-y-1 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <Link to={`/innowacje/${match.innovation.id}`} className="font-medium text-brand-700 hover:underline">
                  {match.innovation.title}
                </Link>
                <Badge tone="brand">{matchStrength(match.score)}</Badge>
              </div>
              <p className="text-sm text-slate-700">{match.reason}</p>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-slate-600">Radar nie znalazł jeszcze dopasowanych innowacji.</p>
      )}
    </div>
  )
}

function NeedCard({ need, expanded, toggle }: { need: Need; expanded: boolean; toggle: () => void }) {
  const label = useLabel()

  return (
    <Card className="space-y-3 p-5">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Link to={`/organizacje/${need.organization.id}`} className="text-slate-600 hover:underline">
          {need.organization.name}
        </Link>
        {need.status === 'zamkniete' && <Badge>Zamknięte</Badge>}
      </div>
      <h2 className="text-lg font-semibold text-slate-900">{need.title}</h2>
      {need.description && <p className="whitespace-pre-line break-words text-sm text-slate-700">{need.description}</p>}
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
      <Button variant="secondary" type="button" aria-expanded={expanded} onClick={toggle}>
        {expanded ? 'Ukryj dopasowania' : 'Pokaż dopasowania'}
      </Button>
      {expanded && <NeedMatches id={need.id} />}
    </Card>
  )
}

export default function Needs() {
  const [offset, setOffset] = useState(0)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const needs = useNeeds(offset)

  return (
    <div className="space-y-6">
      <header>
        <h1 className="page-title">Zapotrzebowania</h1>
        <p className="mt-2 text-slate-600">
          Opisz problem, dla którego szukasz rozwiązania. Radar wskaże innowacje, które mogą pomóc.
        </p>
      </header>
      <div className="grid items-start gap-6 lg:grid-cols-[3fr_2fr]">
        <div className="space-y-4">
          {needs.isPending && <Loading />}
          {needs.isError && <ErrorNote error={needs.error} />}
          {needs.data?.items.map((need) => (
            <NeedCard
              key={need.id}
              need={need}
              expanded={need.id === expandedId}
              toggle={() => setExpandedId(need.id === expandedId ? null : need.id)}
            />
          ))}
          {needs.data?.total === 0 && <Card className="p-5 text-sm text-slate-600">Brak zapotrzebowań.</Card>}
          {needs.data && needs.data.total > needs.data.limit && (
            <div className="flex gap-2">
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
        <NeedForm onCreated={(id) => {
          setOffset(0)
          setExpandedId(id)
        }} />
      </div>
    </div>
  )
}

import { ArrowRight, ScanSearch } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useLabel } from '../api/hooks.ts'
import { comparedLabel, labelForRelation, noveltyMinLength, useCheckIdea } from '../api/similar.ts'
import { Badge, Button, Card, ErrorNote, Field, inputClass } from '../components/ui.tsx'

export default function IdeaCheck() {
  const [text, setText] = useState('')
  const check = useCheckIdea()
  const label = useLabel()
  const result = check.data

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (text.trim().length >= noveltyMinLength) check.mutate(text.trim())
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="space-y-2 border-b border-slate-200 pb-4 sm:pb-5">
        <h1 className="page-title">Sprawdź pomysł</h1>
        <p className="text-slate-600">Zobacz, kto w radarze pracuje nad podobnym rozwiązaniem.</p>
      </header>

      <Card className="p-5 sm:p-7">
        <form onSubmit={submit} className="space-y-4">
          <Field label="Opisz swoją innowację albo pomysł" hint="Napisz, komu chcesz pomóc, jaki problem rozwiązujesz i jak ma działać Twój pomysł.">
            <textarea
              rows={6}
              minLength={noveltyMinLength}
              value={text}
              onChange={(event) => {
                setText(event.target.value)
                check.reset()
              }}
              className={`${inputClass} min-h-36 resize-y`}
              placeholder="Uczniowie klas trzecich pomagają pierwszakom w matematyce na cotygodniowych spotkaniach w parach."
              required
            />
          </Field>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-slate-500">Co najmniej 40 znaków</span>
            <Button type="submit" disabled={text.trim().length < noveltyMinLength || check.isPending}>
              <ScanSearch className="size-4" aria-hidden="true" />
              {check.isPending ? 'Porównuję rozwiązania…' : 'Sprawdź świeżość'}
            </Button>
          </div>
          <div aria-live="polite">
            {check.isPending && <p className="text-sm text-slate-500">Trwa porównywanie pomysłu z radarem.</p>}
            {check.error && <ErrorNote error={check.error} />}
          </div>
        </form>
      </Card>

      {result && (
        <section aria-label="Wyniki porównania" aria-live="polite" className="space-y-5">
          <Card className="space-y-5 border-brand-100 bg-brand-50/40 p-5 sm:p-7">
            <div className="flex flex-wrap items-center gap-x-7 gap-y-3">
              <div className="flex items-baseline gap-1 text-brand-700">
                <span className="font-display text-6xl font-semibold tracking-tight tabular-nums">{result.novelty}</span>
                <span className="text-base font-medium">/ 100</span>
              </div>
              <div className="space-y-1">
                <h2 className="text-xl font-semibold">Świeżość pomysłu</h2>
                <p className="text-sm text-slate-600">{comparedLabel(result.compared)}</p>
              </div>
            </div>

            <div>
              <div
                className="relative mx-2 h-2 rounded-full bg-slate-300"
                role="meter"
                aria-label="Świeżość pomysłu w radarze"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={result.novelty}
              >
                <span
                  className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-canvas bg-brand-600"
                  style={{ left: `${result.novelty}%` }}
                />
              </div>
              <div className="mt-2 grid grid-cols-2 gap-3 text-xs text-slate-600">
                <span>Prawie to samo już istnieje</span>
                <span className="text-right">Nic podobnego w radarze</span>
              </div>
            </div>

            <p className="text-sm font-medium text-slate-800">{result.verdict}</p>
          </Card>

          {result.nearest.length > 0 && (
            <Card className="p-5 sm:p-7">
              <h2 className="text-lg font-semibold">Najbliższe rozwiązania</h2>
              <ul className="mt-2 divide-y divide-slate-100">
                {result.nearest.map(({ innovation, relation, shared }) => (
                  <li key={innovation.id} className="space-y-2 py-4 last:pb-0">
                    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
                      <div>
                        <Link
                          to={`/innowacje/${innovation.id}`}
                          className="inline-flex items-baseline gap-2 font-semibold text-brand-700 hover:underline"
                        >
                          {innovation.title}
                          <ArrowRight className="size-3.5 shrink-0 self-center" aria-hidden="true" />
                        </Link>
                        {innovation.organization && <p className="text-sm text-slate-500">{innovation.organization.name}</p>}
                      </div>
                      <Badge tone={relation === 'to_samo' ? 'amber' : 'brand'}>{labelForRelation(relation)}</Badge>
                    </div>
                    {shared.domains.length > 0 && (
                      <p className="text-sm text-slate-600">
                        Wspólne obszary · {shared.domains.map((domain) => label('domains', domain)).join(', ')}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card className="flex flex-wrap items-center justify-between gap-4 p-5 sm:px-7">
            <p className="max-w-lg text-sm text-slate-700">
              {result.novelty <= 35
                ? 'Zobacz, jak zrobili to inni, i odezwij się do twórców. Możesz też zgłosić swój pomysł.'
                : result.novelty >= 80 && result.nearest.length === 0
                  ? 'W radarze nie znaleziono podobnego zgłoszenia. Dodaj swoją innowację.'
                  : 'Sprawdź, co możesz wykorzystać z doświadczeń innych, i zgłoś swój pomysł.'}
            </p>
            <Link
              className="inline-flex items-center gap-2 min-h-10 rounded-sm bg-brand-600 px-4 py-2 text-sm font-semibold text-ink hover:bg-brand-700"
              to="/zglos"
            >
              Zgłoś innowację <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </Card>
        </section>
      )}
    </div>
  )
}

import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useAssessment, useSaveAssessment, type AssessmentItem } from '../../api/assessments.ts'
import type { InnovationFull } from '../../api/types.ts'
import { usePersona } from '../../lib/persona.tsx'
import { Badge, Button, Card, ErrorNote, Field, Loading, inputClass } from '../ui.tsx'

const points = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 0 })
const criterionPoints = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 2 })
const outcomes = {
  confirmed: { text: 'Potwierdzona', tone: 'green' },
  denied: { text: 'Zaprzeczona', tone: 'amber' },
  unknown: { text: 'Brak informacji', tone: 'slate' },
} as const
const dateTime = new Intl.DateTimeFormat('pl-PL', { dateStyle: 'short', timeStyle: 'short' })

function OverrideForm({
  item, disabled, onCancel, onSave,
}: {
  item: AssessmentItem
  disabled: boolean
  onCancel: () => void
  onSave: (score: number, justification: string) => void
}) {
  const [score, setScore] = useState(String(item.score))
  const [justification, setJustification] = useState(item.override ? item.justification : '')

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (score && justification.trim()) onSave(Number(score), justification.trim())
  }

  return (
    <form onSubmit={submit} className="mt-3 space-y-3 rounded-lg bg-slate-50 p-3">
      <Field label="Wynik od 0 do 5">
        <input
          className={inputClass}
          type="number"
          min={0}
          max={5}
          step="any"
          required
          value={score}
          disabled={disabled}
          onChange={(event) => setScore(event.target.value)}
        />
      </Field>
      <Field label="Uzasadnienie poprawki">
        <textarea
          className={inputClass}
          rows={2}
          required
          value={justification}
          disabled={disabled}
          onChange={(event) => setJustification(event.target.value)}
        />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={disabled || !justification.trim()}>
          {disabled ? 'Zapisywanie…' : 'Zapisz poprawkę'}
        </Button>
        <Button type="button" variant="ghost" disabled={disabled} onClick={onCancel}>Anuluj</Button>
      </div>
    </form>
  )
}

export default function AssessmentPanel({ innovation }: { innovation: InnovationFull }) {
  const { data: assessment, isPending, error } = useAssessment(innovation.id)
  const save = useSaveAssessment(innovation.id)
  const { persona } = usePersona()
  const [editing, setEditing] = useState<{ assessmentId: number; key: string } | null>(null)

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="technical-label">Ocena potencjału</h2>
        <Link to="/kryteria" className="text-sm font-medium text-brand-700 hover:underline">Kryteria oceny</Link>
      </div>
      {isPending && <Loading label="Wczytywanie oceny…" />}
      {(error || save.error) && <div className="mt-3"><ErrorNote error={error || save.error} /></div>}
      {assessment === null && (
        <Button className="mt-4" disabled={save.isPending} onClick={() => save.mutate(undefined)}>
          {save.isPending ? 'Oceniam potencjał…' : 'Oceń potencjał'}
        </Button>
      )}
      {assessment && (
        <>
          <div className="mt-4 flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <p className="text-3xl font-semibold tabular-nums text-brand-700">
              {assessment.has_score ? <>{points.format(assessment.total)}<span className="text-base font-normal text-slate-500"> / 100</span></>
                : 'Brak danych do oceny'}
            </p>
            {assessment.has_score && !assessment.ranked && <Badge tone="amber">Wynik wstępny · poza rankingiem</Badge>}
            <span className="text-sm text-slate-600">
              {assessment.scored_weight < 100 ? `Dane pokrywają ${assessment.scored_weight}% wag kryteriów`
                : assessment.needs_review ? 'Ocena wymaga sprawdzenia przez koordynatora'
                  : assessment.confidence == null ? 'Ocena sprawdzona przez koordynatora' : 'Model rozstrzygnął z wystarczającą pewnością'}
            </span>
          </div>
          <ul className="mt-3 divide-y divide-slate-200">
            {assessment.items.map((item) => {
              const canEdit = persona?.role === 'broker'
              const isEditing = canEdit && editing?.assessmentId === assessment.id && editing.key === item.key
              const lowConfidence = item.confidence != null && item.confidence < assessment.review_threshold && !item.missing
              return (
                <li key={item.key} className="space-y-2 py-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                    <h3 className="text-sm font-semibold text-slate-900">{item.label}</h3>
                    <span className="text-sm tabular-nums text-slate-700">
                      {!item.missing && <><strong className="font-semibold">{criterionPoints.format(item.score)} / 5</strong>{' · '}</>}
                      {item.missing && <span>Bez punktacji · </span>}
                      waga {item.weight}%
                    </span>
                  </div>
                  {!item.missing && <div
                    role="progressbar"
                    aria-label={item.label}
                    aria-valuenow={item.score}
                    aria-valuemin={0}
                    aria-valuemax={5}
                    className="h-2 overflow-hidden rounded-full bg-slate-100"
                  >
                    <div
                      className="h-full rounded-full bg-brand-500"
                      style={{ width: `${20 * item.score}%` }}
                    />
                  </div>}
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
                    {item.missing && <Badge tone="amber">Brak danych</Badge>}
                    {lowConfidence && <Badge tone="amber">Do sprawdzenia przez człowieka</Badge>}
                    {item.override && (
                      <Badge tone="green">
                        Poprawka · {item.override.user_name} · {dateTime.format(new Date(item.override.at))}
                      </Badge>
                    )}
                  </div>
                  {!item.checks && <p className="text-sm leading-relaxed text-slate-800">{item.justification}</p>}
                  {item.checks && (
                    <ul className="space-y-2 text-sm text-slate-800">
                      {item.checks.map((check) => (
                        <li key={check.key} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                          <Badge tone={outcomes[check.status].tone}>{outcomes[check.status].text}</Badge>
                          <span>{check.text}</span>
                          <span className="text-slate-500">
                            {check.status === 'unknown' ? `Do ${check.points} pkt`
                              : `${check.status === 'confirmed' ? check.points : 0} / ${check.points} pkt`}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {item.evidence && (
                    <blockquote className="border-l-2 border-brand-100 pl-3 text-sm leading-relaxed text-slate-600">
                      „{item.evidence}”
                    </blockquote>
                  )}
                  {item.question && (
                    <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
                      <strong className="block font-medium">Pytanie do twórcy</strong>
                      {item.question}
                    </p>
                  )}
                  {canEdit && !isEditing && (
                    <Button
                      variant="ghost"
                      className="-ml-2 px-2 py-1 text-xs"
                      disabled={save.isPending}
                      aria-label={`Popraw wynik: ${item.label}`}
                      onClick={() => {
                        save.reset()
                        setEditing({ assessmentId: assessment.id, key: item.key })
                      }}
                    >
                      Popraw wynik
                    </Button>
                  )}
                  {isEditing && (
                    <OverrideForm
                      item={item}
                      disabled={save.isPending}
                      onCancel={() => {
                        save.reset()
                        setEditing(null)
                      }}
                      onSave={(score, justification) =>
                        save.mutate({ key: item.key, score, justification }, { onSuccess: () => setEditing(null) })
                      }
                    />
                  )}
                </li>
              )
            })}
          </ul>
          <p className="break-words border-t border-slate-200 pt-3 text-xs text-slate-500">
            {assessment.engine} · Kryteria v{assessment.criteria_version}
            {assessment.calibrated === false && ' · Silnik zastępczy bez kalibracji'}
          </p>
        </>
      )}
    </Card>
  )
}

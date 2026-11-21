import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCreateInnovation, useMeta } from '../api/hooks.ts'
import type { StructureCard, StructureResult } from '../api/structure.ts'
import type { InnovationInput } from '../api/types.ts'
import AiDraft from '../components/AiDraft.tsx'
import SimilarHints from '../components/SimilarHints.tsx'
import { Badge, Button, Card, ChipSelect, ErrorNote, Field, cx, inputClass } from '../components/ui.tsx'
import { usePersona } from '../lib/persona.tsx'

type DraftField = keyof StructureCard
type FormValues = Omit<InnovationInput, 'keywords'> & { keywords: string }
type FormState = {
  values: FormValues
  edited: ReadonlySet<DraftField>
  draft: StructureResult | null
}

const initial: FormState = {
  values: { title: '', description: '', summary: '', problem: '', solution: '', results: '', keywords: '' },
  edited: new Set(),
  draft: null,
}

export default function Submit() {
  const [{ values, edited, draft }, setForm] = useState(initial)
  const { data: meta } = useMeta()
  const { persona } = usePersona()
  const create = useCreateInnovation()
  const navigate = useNavigate()

  const set = <K extends DraftField>(key: K, value: FormValues[K]) =>
    setForm((current) => ({
      ...current,
      values: { ...current.values, [key]: value },
      edited: new Set([...current.edited, key]),
    }))

  const applyDraft = (result: StructureResult) =>
    setForm((current) => {
      const proposed = { ...result.card, keywords: result.card.keywords.join(', ') }
      const updates = Object.entries(proposed).filter(([key]) => !current.edited.has(key as DraftField))
      const applied = updates.some(([, value]) => Array.isArray(value) ? value.length > 0 : Boolean(value))
      return {
        ...current,
        draft: result,
        values: {
          ...current.values,
          ...Object.fromEntries(updates),
          structured_by: applied ? result.engine.text : current.values.structured_by,
        },
      }
    })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const keywords = [...new Set(values.keywords.split(',').map((value) => value.trim()).filter(Boolean))]
    create.mutate({ ...values, keywords }, { onSuccess: (created) => navigate(`/innowacje/${created.id}`) })
  }

  const missing = (field: DraftField) =>
    draft?.missing.includes(field) && (!edited.has(field) || !values[field]?.length)

  const note = (field: DraftField) => {
    if (!draft) return null
    if (missing(field)) return <Badge tone="amber">{field === 'title' ? 'Uzupełnij nazwę' : 'Brak w opisie'}</Badge>
    if (edited.has(field)) return null
    const calibrated = draft.engine.tags.startsWith('basal-serve:')
    if (field === 'kind' || field === 'stage') {
      if (draft.tags[field].confidence < (calibrated ? 0.60 : 0.75)) return <Badge tone="amber">Tag do sprawdzenia</Badge>
    }
    if (field === 'domains' || field === 'support_needs') {
      const { value, probabilities, confidence } = draft.tags[field]
      const uncertain = value.filter((key) => (probabilities[key] ?? confidence) < (calibrated ? 0.70 : 0.90))
      if (uncertain.length) {
        const labels = uncertain.map((key) => meta?.[field].find((item) => item.key === key)?.label ?? key)
        return <Badge tone="amber">Tagi do sprawdzenia · {labels.join(', ')}</Badge>
      }
    }
    return <Badge tone="brand">Propozycja</Badge>
  }

  const fieldClass = (field: DraftField) =>
    cx(inputClass, missing(field) && 'border-amber-400 bg-amber-50/40')

  const tagGroups = [
    { name: 'domains', label: 'Obszary' },
    { name: 'support_needs', label: 'Czego potrzebujesz, żeby pójść dalej?' },
  ] as const

  return (
    <form onSubmit={submit} className="mx-auto max-w-2xl">
      <Card className="space-y-5 p-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Zgłoś innowację</h1>
          {persona && (
            <p className="mt-1 text-sm text-slate-500">
              Zgłaszasz jako {persona.name}{persona.organization && ` (${persona.organization.name})`}.
            </p>
          )}
        </div>

        <AiDraft
          text={values.description ?? ''}
          onTextChange={(description) =>
            setForm((current) => ({ ...current, values: { ...current.values, description } }))
          }
          onDraft={applyDraft}
        />

        {draft && (
          <div aria-live="polite" className="space-y-2 rounded-lg border border-slate-200 p-4 text-sm text-slate-700">
            <p>Sprawdź propozycję karty i popraw pola przed zgłoszeniem.</p>
            {draft.questions.length > 0 && (
              <>
                <h2 className="font-semibold text-slate-900">Pytania uzupełniające</h2>
                <ul className="list-disc space-y-1 pl-5">
                  {draft.questions.map((question) => <li key={question}>{question}</li>)}
                </ul>
              </>
            )}
          </div>
        )}

        <Field label="Nazwa">
          {note('title')}
          <input required maxLength={400} value={values.title} onChange={(e) => set('title', e.target.value)} className={fieldClass('title')} />
        </Field>
        <Field label="Krótkie streszczenie" hint="To zobaczą inni na liście innowacji.">
          {note('summary')}
          <textarea rows={2} value={values.summary ?? ''} onChange={(e) => set('summary', e.target.value)} className={fieldClass('summary')} />
        </Field>
        <Field label="Jaki problem rozwiązuje?">
          {note('problem')}
          <textarea rows={3} value={values.problem ?? ''} onChange={(e) => set('problem', e.target.value)} className={fieldClass('problem')} />
        </Field>
        <Field label="Jak działa rozwiązanie?">
          {note('solution')}
          <textarea rows={3} value={values.solution ?? ''} onChange={(e) => set('solution', e.target.value)} className={fieldClass('solution')} />
        </Field>
        <Field label="Jakie są efekty?" hint="Liczby, wyniki testów, opinie użytkowników.">
          {note('results')}
          <textarea rows={2} value={values.results ?? ''} onChange={(e) => set('results', e.target.value)} className={fieldClass('results')} />
        </Field>

        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Rodzaj">
            {note('kind')}
            <select value={values.kind ?? ''} onChange={(e) => set('kind', e.target.value || null)} className={fieldClass('kind')}>
              <option value="">Wybierz</option>
              {meta?.innovation_kinds.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
          </Field>
          <Field label="Etap">
            {note('stage')}
            <select value={values.stage ?? ''} onChange={(e) => set('stage', e.target.value || null)} className={fieldClass('stage')}>
              <option value="">Wybierz</option>
              {meta?.stages.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
          </Field>
        </div>

        {tagGroups.map(({ name, label }) => (
          <fieldset key={name} className={cx('space-y-2', missing(name) && 'rounded-lg bg-amber-50 px-2 pb-2')}>
            <legend className="text-sm font-medium text-slate-800">{label}</legend>
            {note(name)}
            <ChipSelect options={meta?.[name] ?? []} value={values[name] ?? []} onChange={(v) => set(name, v)} />
          </fieldset>
        ))}

        <Field label="Słowa kluczowe" hint="Oddziel hasła przecinkami.">
          {note('keywords')}
          <input value={values.keywords} onChange={(e) => set('keywords', e.target.value)} className={fieldClass('keywords')} />
        </Field>

        <SimilarHints text={[values.description, values.title, values.summary, values.problem, values.solution].filter(Boolean).join('\n')} />

        {create.error && <ErrorNote error={create.error} />}
        <div className="flex justify-end">
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? 'Zapisywanie…' : 'Zgłoś innowację'}
          </Button>
        </div>
      </Card>
    </form>
  )
}

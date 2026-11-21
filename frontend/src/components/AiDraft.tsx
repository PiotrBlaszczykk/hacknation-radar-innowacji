import { LoaderCircle, Sparkles } from 'lucide-react'
import { useStructureText, type StructureResult } from '../api/structure.ts'
import { Button, ErrorNote, Field, inputClass } from './ui.tsx'

type Props = {
  text: string
  onTextChange: (text: string) => void
  onDraft: (draft: StructureResult) => void
}

export default function AiDraft({ text, onTextChange, onDraft }: Props) {
  const structure = useStructureText()
  const longEnough = text.trim().length >= 40

  return (
    <section className="space-y-3 rounded-xl border border-brand-100 bg-brand-50/60 p-4">
      <Field
        label="Opisz innowację swoimi słowami albo wklej tekst"
        hint="Do ułożenia karty potrzeba co najmniej 40 znaków. Możesz też uzupełnić pola samodzielnie."
      >
        <textarea
          rows={6}
          className={inputClass}
          value={text}
          readOnly={structure.isPending}
          onChange={(event) => {
            onTextChange(event.target.value)
            if (structure.isError) structure.reset()
          }}
        />
      </Field>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          disabled={!longEnough || structure.isPending}
          onClick={() => structure.mutate(text, { onSuccess: onDraft })}
        >
          {structure.isPending ? (
            <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />
          ) : (
            <Sparkles size={16} aria-hidden="true" />
          )}
          Ułóż kartę
        </Button>
        <span role="status" className="text-sm text-slate-600">
          {structure.isPending ? 'Układamy propozycję karty…' : ''}
        </span>
      </div>
      {structure.error && <ErrorNote error={structure.error} />}
    </section>
  )
}

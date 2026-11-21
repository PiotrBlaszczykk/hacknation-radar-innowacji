import { useCriteria } from '../api/assessments.ts'
import { Badge, Card, ErrorNote, Loading } from '../components/ui.tsx'

export default function Criteria() {
  const { data, isPending, error } = useCriteria()

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <h1 className="page-title">Kryteria oceny potencjału</h1>
        {data && <p className="mt-1 text-sm text-slate-500">Wersja {data.version}</p>}
      </header>
      {isPending && <Loading label="Wczytywanie kryteriów…" />}
      {error && <ErrorNote error={error} />}
      {data && (
        <>
          <Card className="space-y-3 p-5 text-sm leading-relaxed text-slate-700">
            <p>
              Model sprawdza, czy dosłowny fragment karty potwierdza przesłankę, zaprzecza jej
              lub pozostawia ją bez rozstrzygnięcia. Potwierdzone przesłanki dają od 0 do 5 punktów
              na kryterium według poniższej listy.
            </p>
            <p>
              Ocena łączna w skali 0–100 to średnia ważona ocenionych kryteriów, pomnożona przez 20.
              Gdy nie można rozstrzygnąć żadnej przesłanki danego kryterium, jego waga nie wchodzi do średniej.
              Karta wchodzi do rankingu przy pokryciu co najmniej {data.min_rank_weight}% wag.
              Przy mniejszym pokryciu ocena jest wstępna. Gdy nie ma danych do żadnego kryterium,
              panel pokazuje brak oceny.
            </p>
            <p>
              Przy brakach panel pokazuje, jaki odsetek wag ma oparcie w karcie. Gdy ocena ma
              zbyt niską pewność, broker dostaje sprawę do sprawdzenia. Broker może poprawić punktację
              i wpisać uzasadnienie widoczne na karcie.
            </p>
          </Card>
          {data.criteria.map((criterion) => (
            <Card key={criterion.key} className="p-5">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold text-slate-900">{criterion.label}</h2>
                <Badge tone="brand">Waga {criterion.weight}%</Badge>
              </div>
              <p className="mt-2 text-sm text-slate-700">{criterion.question}</p>
              <ul className="mt-3 divide-y divide-slate-100 text-sm text-slate-700">
                {criterion.checks.map((check) => (
                  <li key={check.key} className="grid grid-cols-[3rem_1fr] gap-2 py-2">
                    <span className="font-semibold tabular-nums text-brand-700">{check.points} pkt</span>
                    <span>{check.text}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-sm text-slate-700">
                <span className="block font-medium text-slate-900">Pytanie przy braku danych</span>
                {criterion.missing_question}
              </p>
            </Card>
          ))}
        </>
      )}
    </div>
  )
}

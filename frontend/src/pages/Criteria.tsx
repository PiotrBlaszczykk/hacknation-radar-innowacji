import { reviewThreshold, useCriteria } from '../api/assessments.ts'
import { Badge, Card, ErrorNote, Loading } from '../components/ui.tsx'

export default function Criteria() {
  const { data, isPending, error } = useCriteria()

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Kryteria oceny potencjału</h1>
        {data && <p className="mt-1 text-sm text-slate-500">Wersja {data.version}</p>}
      </header>
      {isPending && <Loading label="Wczytywanie kryteriów…" />}
      {error && <ErrorNote error={error} />}
      {data && (
        <>
          <Card className="space-y-3 p-5 text-sm leading-relaxed text-slate-700">
            <p>
              Każde kryterium ma skalę od 0 do 5. Model wyznacza prawdopodobieństwo każdego poziomu,
              a wynik kryterium to średnia poziomów ważona tymi prawdopodobieństwami.
              Wynik łączny to średnia ważona wyników kryteriów, pomnożona przez 20.
            </p>
            <p>
              Przy braku danych karta pokazuje 2,5/5 i pytanie do twórcy. W obliczeniu wyniku łącznego
              bierze udział tylko to, co udało się ocenić. Gdy brakuje wszystkich danych, panel pokazuje 50/100.
            </p>
            <p>
              Pewność opisuje, jak zdecydowanie model wskazał poziom na skali. Przy pewności poniżej
              {' '}{reviewThreshold * 100}% kryterium trafia do sprawdzenia przez człowieka.
              Pewność łączna to średnia ważona pewności modelu. Brak danych wnosi do niej zero,
              a poprawione przez brokera kryteria są w tej średniej pomijane.
            </p>
          </Card>
          {data.criteria.map((criterion) => (
            <Card key={criterion.key} className="p-5">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold text-slate-900">{criterion.label}</h2>
                <Badge tone="brand">Waga {criterion.weight}%</Badge>
              </div>
              <p className="mt-2 text-sm text-slate-700">{criterion.question}</p>
              <ol start={0} className="mt-3 divide-y divide-slate-100 text-sm text-slate-700">
                {criterion.levels.map((level, index) => (
                  <li key={level} className="grid grid-cols-[2rem_1fr] gap-2 py-2">
                    <span className="font-semibold tabular-nums text-brand-700">{index}</span>
                    <span>{level}</span>
                  </li>
                ))}
              </ol>
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

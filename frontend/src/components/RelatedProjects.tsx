import { Link } from 'react-router-dom'
import { useBrokerDuplicates } from '../api/broker.ts'
import { Badge, Card, ErrorNote, Loading } from './ui.tsx'

export default function RelatedProjects({ preview = false }: { preview?: boolean }) {
  const { data, error } = useBrokerDuplicates()
  if (!data && !error) return <Loading label="Ładowanie porównań…" />

  return (
    <section aria-labelledby="duplicates-title" className="space-y-3">
      <h2 id="duplicates-title" className="section-title">
        Jeden problem, różne organizacje
      </h2>
      <p className="text-sm text-slate-600">Radar porównuje opisy i wskazuje organizacje pracujące nad podobnym problemem lub rozwiązaniem.</p>
      {error && <ErrorNote error={error} />}
      {data && (
        <Card className="divide-y divide-slate-100">
          {data.items.length === 0 && <p className="p-5 text-sm text-slate-600">Brak zapisanych par podobnych innowacji.</p>}
          {(preview ? data.items.slice(0, 1) : data.items).map(({ left, right, relation }) => (
            <div key={`${left.id}-${right.id}`} className="space-y-2 p-4">
              <Badge tone="violet">{relation === 'to_samo' ? 'To samo rozwiązanie' : 'Ten sam problem'}</Badge>
              <div className={preview ? 'space-y-3' : 'grid gap-3 sm:grid-cols-2'}>
                {[left, right].map((innovation) => (
                  <div key={innovation.id}>
                    <Link className={`font-semibold text-sm hover:underline`} to={`/innowacje/${innovation.id}`}>{innovation.title}</Link>
                    <p className="text-xs text-slate-600">{innovation.organization?.name ?? 'Organizacja nieznana'}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </Card>
      )}
      {preview && !!data?.items.length && <Link to="/porownania" className="inline-block text-sm font-semibold text-brand-700 hover:underline">Zobacz porównania →</Link>}
    </section>
  )
}

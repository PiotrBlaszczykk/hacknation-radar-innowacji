import { ArrowRight, ArrowUpRight } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  useBrokerBoard, useBrokerDuplicates, useBrokerQueue, useBrokerSummary, useMoveInnovation,
  type BrokerColumn, type QueueItem,
} from '../api/broker.ts'
import { useLabel, useMeta } from '../api/hooks.ts'
import { Badge, Button, Card, ErrorNote, Loading } from '../components/ui.tsx'
import { usePersona } from '../lib/persona.tsx'

const number = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 1 })
const percent = new Intl.NumberFormat('pl-PL', { style: 'percent', maximumSignificantDigits: 3 })
const titleLink = 'font-semibold text-slate-900 hover:text-brand-700 hover:underline'
const queueTypes: Record<QueueItem['type'], { label: string; section: string }> = {
  low_confidence: { label: 'Ocena do przeglądu', section: 'ocena' },
  path_approval: { label: 'Ścieżka', section: 'sciezka' },
  match_interest: { label: 'Zainteresowanie', section: 'dopasowania' },
  unclaimed_profile: { label: 'Potwierdzenie profilu', section: 'potwierdzenie-profilu' },
}

function Overview() {
  const { data, error, isPending } = useBrokerSummary()
  const { data: meta } = useMeta()
  if (error) return <ErrorNote error={error} />
  if (isPending) return <Loading label="Ładowanie podsumowania…" />

  const { by_origin: origins, by_status: statuses } = data.innovations
  const tiles = [
    { name: 'Wykryte przez radar', count: origins.radar },
    { name: 'Zgłoszone', count: origins.zgloszenie },
    { name: 'Ocenione', count: statuses.oceniona },
    { name: 'Skierowane na ścieżkę', count: statuses.skierowana },
    { name: 'W kontakcie', count: statuses.w_kontakcie },
    { name: 'Wdrażane', count: statuses.wdrazana },
  ]
  const colors = ['bg-slate-400', 'bg-sky-400', 'bg-brand-500', 'bg-violet-400', 'bg-amber-200', 'bg-emerald-400']
  const stages = (meta?.statuses ?? []).filter(({ key }) => key !== 'archiwum')
  const active = data.innovations.total - statuses.archiwum

  return (
    <section aria-label="Podsumowanie przepływu" className="border-y border-slate-200">
      <dl className="grid grid-cols-2 gap-px bg-slate-200 min-[360px]:grid-cols-3 lg:grid-cols-6">
        {tiles.map(({ name, count }) => (
          <div key={name} className="flex min-w-0 flex-col gap-1.5 bg-surface px-3 py-2.5 sm:px-4 sm:py-3">
            <dt className="text-sm leading-tight text-slate-600">{name}</dt>
            <dd className="font-display text-3xl leading-none font-semibold tabular-nums text-slate-900 sm:text-4xl">{number.format(count)}</dd>
          </div>
        ))}
      </dl>
      <div className="space-y-2 border-t border-slate-200 py-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-900">Bieżące etapy przepływu</h2>
          <p className="text-xs text-slate-600">Aktywne innowacje · {number.format(active)}</p>
        </div>
        {active > 0 && (
          <div aria-hidden="true" className="flex h-2.5 overflow-hidden rounded-full bg-slate-100">
            {stages.map(({ key }, index) => (
              <div key={key} className={colors[index]} style={{ flexGrow: statuses[key] ?? 0 }} />
            ))}
          </div>
        )}
        <ul className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-slate-600">
          {stages.map(({ key, label }, index) => (
            <li key={key} className="flex items-center gap-1.5">
              <span aria-hidden className={`size-2 rounded-full ${colors[index]}`} />
              {label} <strong className="tabular-nums text-slate-800">{statuses[key] ?? 0}</strong>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

function BoardColumn({ column, nextStatus, canMove }: { column: BrokerColumn; nextStatus?: string; canMove: boolean }) {
  const label = useLabel()
  const mutation = useMoveInnovation()

  return (
    <section aria-label={label('statuses', column.status)} className="flex min-w-0 flex-col border border-slate-200 bg-shell">
      <div className="flex min-h-14 items-center justify-between gap-2 border-b border-slate-200 px-3 py-2.5">
        <h3 className="text-sm font-semibold leading-tight text-slate-900">{label('statuses', column.status)}</h3>
        <Badge>{column.total}</Badge>
      </div>
      <div className="max-h-[26rem] divide-y divide-slate-200 overflow-y-auto">
        {column.items.map((item) => (
          <article key={item.id} className="space-y-2 px-3 py-3">
            <Link className={`${titleLink} block wrap-anywhere text-sm leading-snug`} to={`/innowacje/${item.id}`}>
              {item.title}
            </Link>
            <p className="text-xs text-slate-600">{item.organization?.name ?? 'Organizacja nieznana'}</p>
            <p className="text-xs text-slate-600">
              {item.score == null ? 'Brak wyniku' : (
                <>Wynik <strong className="font-semibold text-slate-800">{number.format(item.score)} / 100</strong></>
              )}
            </p>
            <div className="flex flex-wrap gap-1">
              {item.needs_review && <Badge tone="amber">Do sprawdzenia</Badge>}
              {item.has_path && <Badge tone="green">Ścieżka zatwierdzona</Badge>}
              {item.matches_count > 0 && <Badge>Dopasowania · {item.matches_count}</Badge>}
              {item.interest_count > 0 && <Badge tone="violet">Zainteresowanie · {item.interest_count}</Badge>}
            </div>
            {canMove && nextStatus && (
              <Button type="button" variant="secondary" className="w-full !px-2 !py-1.5 !text-xs"
                aria-label={`Przenieś ${item.title} do etapu „${label('statuses', nextStatus)}”`}
                disabled={mutation.isPending}
                onClick={() => mutation.mutate({ id: item.id, status: nextStatus })}>
                {mutation.isPending && mutation.variables.id === item.id ? 'Zapisywanie…' : label('statuses', nextStatus)}
                <ArrowRight aria-hidden className="size-3.5 shrink-0" />
              </Button>
            )}
            {mutation.error && mutation.variables?.id === item.id && <ErrorNote error={mutation.error} />}
          </article>
        ))}
        {column.total === 0 && <p className="px-3 py-3 text-sm text-slate-500">Brak innowacji</p>}
      </div>
      {column.total > column.items.length && (
        <p className="border-t border-slate-200 px-3 py-2 text-xs text-slate-600">Pokazano {column.items.length} z {column.total}</p>
      )}
    </section>
  )
}

function Board() {
  const { data, error, isPending } = useBrokerBoard()
  const { data: meta } = useMeta()
  const { persona } = usePersona()
  const canMove = persona?.role === 'broker'
  const statuses = meta?.statuses.map(({ key }) => key) ?? []

  return (
    <section id="tablica" aria-labelledby="board-title" className="min-w-0 scroll-mt-4 space-y-3 lg:scroll-mt-28">
      <div>
        <h2 id="board-title" className="section-title">Tablica innowacji</h2>
        {!canMove && <p className="mt-1 text-sm text-slate-600">Status innowacji może zmienić osoba z rolą brokera.</p>}
      </div>
      {isPending && <Loading label="Ładowanie tablicy…" />}
      {error && <ErrorNote error={error} />}
      {data && (
        <div aria-label="Kolumny etapów" role="region" tabIndex={0}
          className="grid auto-cols-[minmax(9.5rem,1fr)] grid-flow-col items-start gap-2 overflow-x-auto pb-2">
          {data.columns.map((column) => {
            // Wykrycie i zgłoszenie to równoległe początki tego samego przepływu.
            const next = column.status === 'wykryta' ? 'oceniona' : statuses[statuses.indexOf(column.status) + 1]
            return <BoardColumn key={column.status} column={column} nextStatus={meta ? next : undefined} canMove={canMove} />
          })}
        </div>
      )}
    </section>
  )
}

function DecisionQueue() {
  const { data, error, isPending } = useBrokerQueue()
  const [visible, setVisible] = useState(4)

  return (
    <section id="kolejka" aria-labelledby="queue-title" className="min-w-0 scroll-mt-4 space-y-3 lg:scroll-mt-28">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="queue-title" className="section-title">Kolejka decyzji</h2>
        {data && <span className="text-sm tabular-nums text-slate-600"><strong className="text-lg text-brand-700">{number.format(data.total)}</strong> w kolejce</span>}
      </div>
      <div className="border-y border-slate-200 bg-shell">
        {isPending && <Loading label="Ładowanie kolejki…" />}
        {error && <ErrorNote error={error} />}
        {data?.total === 0 && <p className="p-5 text-sm text-slate-600">Żadna sprawa nie czeka teraz na decyzję.</p>}
        {data && data.total > 0 && (
          <ul className="divide-y divide-slate-100">
            {data.items.slice(0, visible).map((item) => {
              const { label, section } = queueTypes[item.type]
              return (
                <li key={`${item.type}-${item.innovation_id}-${item.match_id ?? ''}`}>
                  <Link to={`/innowacje/${item.innovation_id}#${section}`}
                    className="flex items-center justify-between gap-3 px-4 py-3 text-sm hover:bg-slate-50">
                    <div>
                      <p className="technical-label text-brand-700">{label}</p>
                      <p className="mt-1 wrap-anywhere font-semibold text-slate-900">{item.title}</p>
                      <p className="text-slate-600">{item.description}</p>
                    </div>
                    <ArrowUpRight aria-hidden className="size-4 shrink-0 text-brand-700" />
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
        {data && visible < data.total && (
          <div className="border-t border-slate-100 p-3">
            <Button type="button" variant="secondary" onClick={() => setVisible(visible + 8)}>Pokaż kolejne sprawy</Button>
          </div>
        )}
      </div>
    </section>
  )
}

function Metrics() {
  const { data, error, isPending } = useBrokerSummary()
  if (error) return <ErrorNote error={error} />
  if (isPending) return <Loading label="Ładowanie mierników…" />

  const { innovations, assessments, paths, matches, median_days: days, organizations } = data
  const detected = innovations.by_origin.radar
  const ratio = (value: number) => detected ? percent.format(value / detected) : 'Brak wykryć'
  const duration = (value: number | null) => {
    if (value === null) return 'Brak danych'
    if (value === 0) return 'W chwili dodania'
    if (value < 1 / 24) return value < 1 / 1440 ? 'Poniżej minuty' : `${number.format(value * 1440)} min`
    return value < 1 ? `${number.format(value * 24)} godz.` : `${number.format(value)} dni`
  }
  const metrics = [
    { title: 'Wykryte profile z dopasowaniem', value: ratio(matches.radar_innovations_matched),
      detail: `${matches.radar_innovations_matched} z ${detected} wykrytych profili ma co najmniej jedno dopasowanie do organizacji lub zapotrzebowania, które nie zostało odrzucone.` },
    { title: 'Profile potwierdzone przez twórców', value: ratio(innovations.radar_claimed),
      detail: `${innovations.radar_claimed} z ${detected} profili wykrytych przez radar potwierdzili ich twórcy.` },
    { title: 'Średnia ocena potencjału', value: assessments.average_score === null ? 'Brak ocen' : `${number.format(assessments.average_score)} / 100`,
      detail: `Średnia z najnowszych ocen ${assessments.total} innowacji. Liczba ocen o niskiej pewności wynosi ${assessments.low_confidence}.` },
    { title: 'Zatwierdzone ścieżki', value: number.format(paths.total),
      detail: 'Liczba innowacji z odnotowanym zatwierdzeniem ścieżki w historii.' },
    { title: 'Innowacje z nawiązanym kontaktem', value: number.format(matches.innovations_with_contact),
      detail: 'Liczba innowacji z co najmniej jednym dopasowaniem oznaczonym jako kontakt nawiązany.' },
    { title: 'Czas do pierwszej oceny', value: duration(days.to_assessment),
      detail: 'Mediana czasu od wykrycia lub zgłoszenia do pierwszej oceny zapisanej w historii.' },
    { title: 'Czas do pierwszego kontaktu', value: duration(days.to_contact),
      detail: 'Mediana czasu od wykrycia lub zgłoszenia do pierwszego nawiązania kontaktu zapisanego w historii.' },
    { title: 'Organizacje z innowacjami', value: number.format(organizations.total),
      detail: 'Każda organizacja z co najmniej jedną innowacją jest liczona raz.' },
  ]

  return (
    <section aria-labelledby="metrics-title" className="space-y-3">
      <h2 id="metrics-title" className="section-title">Mierniki skuteczności radaru</h2>
      <dl className="grid gap-px border border-slate-200 bg-slate-200 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map(({ title, value, detail }) => (
          <div key={title} className="space-y-2 bg-surface p-4">
            <dt className="text-sm font-medium text-slate-700">{title}</dt>
            <dd className="text-xl font-semibold tabular-nums text-brand-700">{value}</dd>
            <dd className="text-xs leading-relaxed text-slate-600">{detail}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function Duplicates() {
  const { data, error } = useBrokerDuplicates()
  if (!data && !error) return null

  return (
    <section aria-labelledby="duplicates-title" className="space-y-3">
      <h2 id="duplicates-title" className="section-title">
        Te same problemy rozwiązywane w kilku miejscach
      </h2>
      {error && <ErrorNote error={error} />}
      {data && (
        <Card className="divide-y divide-slate-100">
          {data.items.length === 0 && <p className="p-5 text-sm text-slate-600">Brak zapisanych par podobnych innowacji.</p>}
          {data.items.map(({ left, right, relation }) => (
            <div key={`${left.id}-${right.id}`} className="space-y-2 p-4">
              <Badge tone="violet">{relation === 'to_samo' ? 'To samo rozwiązanie' : 'Ten sam problem'}</Badge>
              <div className="grid gap-3 sm:grid-cols-2">
                {[left, right].map((innovation) => (
                  <div key={innovation.id}>
                    <Link className={`${titleLink} text-sm`} to={`/innowacje/${innovation.id}`}>{innovation.title}</Link>
                    <p className="text-xs text-slate-600">{innovation.organization?.name ?? 'Organizacja nieznana'}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </Card>
      )}
    </section>
  )
}

export default function Broker() {
  return (
    <div className="min-w-0 space-y-7">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div>
          <h1 className="page-title">Panel brokera</h1>
          <p className="mt-2 text-slate-600">Śledź innowacje od wykrycia i zgłoszenia po kontakt z partnerem i wdrożenie.</p>
        </div>
        <nav aria-label="Sekcje panelu brokera" className="flex flex-wrap gap-x-4 text-sm font-semibold text-brand-700">
          <a href="#kolejka" className="py-1 hover:underline">Przejdź do kolejki</a>
          <a href="#tablica" className="py-1 hover:underline">Przejdź do tablicy</a>
        </nav>
      </header>
      <Overview />
      <div className="grid gap-6 lg:grid-cols-[minmax(17rem,22rem)_minmax(0,1fr)]">
        <DecisionQueue />
        <Board />
      </div>
      <Metrics />
      <Duplicates />
    </div>
  )
}

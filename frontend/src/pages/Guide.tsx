import { Link } from 'react-router-dom'
import StageGuide from '../components/StageGuide.tsx'

const steps = [
  ['Znajdź rozwiązanie', 'W radarze opisz potrzebę własnymi słowami. „Dla Ciebie” uwzględnia Twój profil, a „Ukryte perełki” pokazują mało zauważone projekty z udokumentowaną próbą lub użyciem.', '/', 'Otwórz radar'],
  ['Sprawdź podstawę oceny', 'Otwórz kartę i sprawdź źródło, wyniki oraz etap. Wynik potencjału podsumowuje kryteria, dla których są dane. Te informacje pomagają zdecydować, czy rozwiązanie warto przetestować u siebie.', '/kryteria', 'Poznaj kryteria'],
  ['Znajdź podobne prace', 'Wpisz opis pomysłu. Radar szuka bliskich znaczeniowo kart i określa, czy łączy je problem, metoda czy całe rozwiązanie. Porównanie obejmuje projekty w bazie.', '/sprawdz-pomysl', 'Wypróbuj przykład'],
  ['Śledź osoby i organizacje', 'Wybierz profil w nagłówku. Kliknij „Obserwuj” przy autorze lub organizacji, a potem otwórz „Obserwowani”, by zobaczyć wpisy i aktywność tej sieci.', '/?tab=obserwowani', 'Otwórz obserwowanych'],
]
export default function Guide() {
  return <div className="mx-auto max-w-3xl space-y-6"><h1 className="page-title">Jak korzystać z Wihajstra?</h1>
    {steps.map(([title, body, to, action]) => <section key={to} className="space-y-2 border-t border-slate-200 pt-4"><h2 className="section-title">{title}</h2><p>{body}</p><Link className="font-semibold text-brand-700 underline" to={to}>{action}</Link></section>)}
    <StageGuide />
  </div>
}

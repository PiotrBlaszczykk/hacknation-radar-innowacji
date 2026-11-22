const groups = [
  { title: 'Pochodzenie karty', rows: [
    ['Wykryte przez radar', 'Radar znalazł opis w publicznym źródle.'],
    ['Zgłoszone', 'Osoba dodała rozwiązanie przez formularz. Pochodzenie zostaje zapisane także po ocenie karty.'],
  ] },
  { title: 'Status sprawy w radarze', rows: [
    ['Wykryta / Zgłoszona', 'Karta jest na początku przeglądu. Nazwa wskazuje, jak trafiła do radaru.'],
    ['Oceniona', 'Karta ma zapisaną ocenę. Szczegóły i dowody znajdziesz na karcie.'],
    ['Skierowana na ścieżkę', 'Wybrano dalszy kierunek pracy, np. transfer technologii albo wdrożenie w innej organizacji.'],
    ['W kontakcie z partnerem', 'Rozpoczęły się rozmowy o współpracy.'],
    ['Wdrażana', 'Trwają prace nad zastosowaniem rozwiązania.'],
    ['Archiwum', 'Karta jest poza bieżącym przeglądem.'],
  ] },
  { title: 'Dojrzałość samego rozwiązania', rows: [
    ['Pomysł', 'Opisano koncepcję.'], ['Prototyp', 'Powstała pierwsza wersja.'],
    ['Pilotaż', 'Rozwiązanie przechodzi próbę w ograniczonej skali.'],
    ['Wdrożona lokalnie', 'Odbiorcy korzystają już z rozwiązania w danym miejscu.'],
    ['Skalowana', 'Rozwiązanie trafia do kolejnych miejsc lub grup odbiorców.'],
  ] },
]

export default function StageGuide() {
  return <details className="my-3 text-sm">
    <summary className="w-fit cursor-pointer font-semibold text-brand-700">Co oznaczają statusy i etapy?</summary>
    <p className="mt-3">Radar może dziś wykryć usługę, z której mieszkańcy korzystają od roku. Jej karta ma wtedy status „Wykryta”, a usługa jest już wdrożona lokalnie.</p>
    {groups.map(group => <section className="my-4" key={group.title}>
      <h3 className="font-semibold">{group.title}</h3>
      <dl className="mt-2 divide-y divide-slate-200">{group.rows.map(([name, description]) =>
        <div className="grid gap-1 py-2 sm:grid-cols-[12rem_1fr]" key={name}><dt className="font-medium">{name}</dt><dd>{description}</dd></div>)}</dl>
    </section>)}
  </details>
}

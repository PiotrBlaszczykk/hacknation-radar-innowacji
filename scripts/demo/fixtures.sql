SET LOCAL search_path = public;

DO $fixtures$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM innovations
        WHERE id = 347 AND origin = 'zgloszenie' AND source_name IS NULL AND source_ref IS NULL
          AND author_id = 3 AND title = 'Test T02 — wypożyczalnia narzędzi w bibliotece'
          AND description = 'W naszej bibliotece od wiosny wypożyczamy narzędzia: wiertarki, drabiny, sekatory. Mieszkańcy biorą je na kartę biblioteczną, tak jak książki. Do tej pory było ponad 400 wypożyczeń i przybyło nam prawie sto nowych czytelników.'
    ) THEN
        RAISE EXCEPTION 'Nie zgadza się tożsamość artefaktu T02';
    END IF;

    IF (
        SELECT count(*) FROM events e
        JOIN assessments a ON a.id::text = e.payload->>'assessment_id' AND a.innovation_id = e.innovation_id
        JOIN assessments kept ON kept.id = 9 AND kept.innovation_id = a.innovation_id
        WHERE (e.id, a.id) IN ((369, 9), (383, 15), (384, 16))
          AND e.innovation_id = 3 AND e.type = 'oceniona' AND e.actor_id IS NULL
          AND e.message = 'Oceniono potencjał innowacji'
          AND (a.criteria_version, a.engine, a.total, a.confidence, a.items)
              = (kept.criteria_version, kept.engine, kept.total, kept.confidence, kept.items)
    ) <> 3 THEN
        RAISE EXCEPTION 'Nie zgadza się tożsamość powtórzeń oceny #3';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM innovations WHERE id = 514 AND origin = 'radar'
          AND source_url = 'https://erzeszow.pl/41-miasto-rzeszow/1713-aktualnosci/147964.html'
    ) OR (
        SELECT count(*) FROM users u
        JOIN organizations o ON o.id = u.organization_id
        WHERE (u.id, u.name) IN ((1, 'Anna Kowalczyk'), (4, 'Tomasz Zieliński'), (6, 'Jakub Mazur'))
          AND o.description LIKE '%Dane przykładowe.%'
    ) <> 3 THEN
        RAISE EXCEPTION 'Nie zgadza się karta lub fikcyjne persony demonstracyjne';
    END IF;

    UPDATE innovations SET status = 'archiwum' WHERE id = 347;

    -- Zachowaj pierwsze wystąpienie, pozostałe wersje oceny i same oceny.
    DELETE FROM events WHERE id IN (383, 384);

    INSERT INTO interactions (user_id, innovation_id, type, body) VALUES
        (1, 514, 'podbicie', '[Przykład T14] Symulowane podbicie.'),
        (4, 514, 'podbicie', '[Przykład T14] Symulowane podbicie.'),
        (6, 514, 'podbicie', '[Przykład T14] Symulowane podbicie.'),
        (1, 514, 'komentarz', '[Przykład T14] Jak mierzyć dostępność usługi po uruchomieniu?'),
        (4, 514, 'komentarz', '[Przykład T14] W symulacji porównujemy liczbę wizyt i liczbę zakończonych spraw.');
END
$fixtures$;

SELECT 'karty', count(*), count(*) FILTER (WHERE status <> 'archiwum'),
       count(*) FILTER (WHERE status = 'archiwum'),
       count(*) FILTER (WHERE score IS NOT NULL AND status <> 'archiwum'),
       md5(string_agg(md5(to_jsonb(i)::text), '' ORDER BY id))
FROM innovations i;

SELECT 'historia', count(*), md5(string_agg(md5(to_jsonb(e)::text), '' ORDER BY id)) FROM events e;
SELECT 'oceny', count(*), md5(string_agg(md5(to_jsonb(a)::text), '' ORDER BY id)) FROM assessments a;
SELECT 'ścieżki', count(*), md5(string_agg(md5(to_jsonb(r)::text), '' ORDER BY id)) FROM recommendations r;
SELECT 'dopasowania', count(*), md5(string_agg(md5(to_jsonb(m)::text), '' ORDER BY id)) FROM matches m;
SELECT 'interakcje', count(*),
       md5(string_agg(md5((to_jsonb(i) - 'created_at')::text), '' ORDER BY id))
FROM interactions i;

SELECT id, status, score, path, claimed, source_url FROM innovations WHERE id IN (1,3,244,347,508,514,523,559,574) ORDER BY id;
SELECT id, innovation_id, type, payload FROM events WHERE id IN (369,383,384) ORDER BY id;
SELECT innovation_id, type, count(*) FROM interactions GROUP BY 1, 2 ORDER BY 1, 2;

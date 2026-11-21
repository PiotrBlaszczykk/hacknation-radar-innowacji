DO $guard$
BEGIN
    IF current_database() <> 'radar_t14_demo' OR (
        SELECT shobj_description(oid, 'pg_database')
        FROM pg_database WHERE datname = current_database()
    ) IS DISTINCT FROM 'Wihajster T14 demo copy' THEN
        RAISE EXCEPTION 'Cel nie jest oznaczoną bazą pokazową T14';
    END IF;
    PERFORM pg_advisory_xact_lock(140021);
END
$guard$;

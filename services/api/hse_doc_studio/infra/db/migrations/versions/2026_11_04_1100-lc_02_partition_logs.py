"""audit_log и ai_usage: партиционирование по месяцам, функции ведения партиций

Revision ID: lc_02_partition_logs
Revises: lc_01_lifecycle_runs
Create Date: 2026-11-04 11:00:00

Как переходим. Старая таблица не копируется: она становится партицией `<таблица>_legacy` с диапазоном
(MINVALUE, граница), рядом создаются месячные партиции и DEFAULT. Граница это начало следующего месяца (если до него
меньше двух суток, то месяца после следующего). Единственное, что растёт с размером таблицы: сборка уникального индекса
(id, at) и проверка диапазона при подключении партиции, обе под блокировкой записи (чтение идёт; вставки ждут около
секунды на миллион строк). Для очень больших журналов индекс строят заранее без блокировки:
`CREATE UNIQUE INDEX CONCURRENTLY <таблица>_idat_uq ON <таблица> (id, at)`; миграция увидит его и не будет строить сама.
Строки старше срока хранения внутри `_legacy` стирает фоновая очистка пачками, а сама партиция исчезает, когда вся
целиком вышла за срок.

Откат копирует строки из партиций в обычную таблицу (долго на больших журналах, зато без потерь).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "lc_02_partition_logs"
down_revision: str | None = "lc_01_lifecycle_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (таблица, ключ, индексы родителя по определению; имена совпадают с ORM, определения с прежними индексами таблицы).
_TABLES = {
    "audit_log": {
        "key": "id",
        "indexes": (
            "CREATE INDEX ix_audit_log_at ON audit_log (at)",
            "CREATE INDEX ix_audit_log_actor_id_desc ON audit_log (actor_id, id DESC)",
            "CREATE INDEX ix_audit_log_target_id_desc ON audit_log (target, id DESC)",
            "CREATE INDEX ix_audit_log_action_id_desc ON audit_log (action varchar_pattern_ops, id DESC)",
        ),
    },
    "ai_usage": {
        "key": "id",
        "indexes": (
            "CREATE INDEX ix_ai_usage_at ON ai_usage (at)",
            "CREATE INDEX ix_ai_usage_user_at ON ai_usage (user_id, at)",
            "CREATE INDEX ix_ai_usage_provider_at ON ai_usage (provider_id, at)",
        ),
    },
}

# Месяцы считаем по UTC независимо от часового пояса сессии: имена партиций и границы не плавают.
_CUTOVER_SQL = """
SELECT (CASE
    WHEN (now() AT TIME ZONE 'UTC') + interval '2 days' >= date_trunc('month', now() AT TIME ZONE 'UTC') + interval '1 month'
    THEN date_trunc('month', now() AT TIME ZONE 'UTC') + interval '2 months'
    ELSE date_trunc('month', now() AT TIME ZONE 'UTC') + interval '1 month'
END) AT TIME ZONE 'UTC'
"""

# Таблицы, которыми можно управлять функциями ниже: SECURITY DEFINER не должен стать способом удалить любую таблицу.
_ENSURE = """
CREATE FUNCTION lifecycle_ensure_partitions(parent text, months_ahead integer) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    first_month timestamp;
    cutover timestamptz;
    month_start timestamp;
    created integer := 0;
    part text;
BEGIN
    IF parent NOT IN ('audit_log', 'ai_usage') THEN
        RAISE EXCEPTION 'lifecycle: table % is not partition-managed', parent USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT upper_bound INTO cutover FROM lifecycle_partition_bounds(parent) WHERE part_name = parent || '_legacy';
    first_month := greatest(
        date_trunc('month', now() AT TIME ZONE 'UTC'),
        coalesce(cutover AT TIME ZONE 'UTC', '-infinity'::timestamp));
    FOR i IN 0..greatest(months_ahead, 0) LOOP
        month_start := first_month + (i || ' months')::interval;
        part := parent || '_p' || to_char(month_start, 'YYYYMM');
        IF to_regclass(part) IS NULL THEN
            BEGIN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                    part, parent, month_start AT TIME ZONE 'UTC', (month_start + interval '1 month') AT TIME ZONE 'UTC');
                IF parent = 'audit_log' THEN
                    EXECUTE format(
                        'CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON %I '
                        'FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only()', part);
                END IF;
                created := created + 1;
            EXCEPTION WHEN check_violation OR invalid_object_definition THEN
                -- В DEFAULT уже лежат строки этого месяца: партицию не создаём, строки остаются на месте.
                RAISE WARNING 'lifecycle: partition % not created, rows already in the default partition', part;
            END;
        END IF;
    END LOOP;
    RETURN created;
END;
$$
"""

# Границы партиций без разбора текста relpartbound: диапазон читаем из pg_get_expr один раз и только здесь.
_BOUNDS = """
CREATE FUNCTION lifecycle_partition_bounds(parent text)
RETURNS TABLE(part_name text, upper_bound timestamptz, is_default boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT c.relname::text,
           CASE WHEN pg_get_expr(c.relpartbound, c.oid) = 'DEFAULT' THEN NULL
                ELSE substring(pg_get_expr(c.relpartbound, c.oid) FROM 'TO \\(''([^'']+)''\\)')::timestamptz END,
           pg_get_expr(c.relpartbound, c.oid) = 'DEFAULT'
    FROM pg_inherits i
    JOIN pg_class c ON c.oid = i.inhrelid
    WHERE i.inhparent = to_regclass(parent)
$$
"""

_DROP = """
CREATE FUNCTION lifecycle_drop_partitions_before(parent text, cutoff timestamptz) RETURNS text[]
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    rec record;
    dropped text[] := ARRAY[]::text[];
BEGIN
    IF parent NOT IN ('audit_log', 'ai_usage') THEN
        RAISE EXCEPTION 'lifecycle: table % is not partition-managed', parent USING ERRCODE = 'insufficient_privilege';
    END IF;
    FOR rec IN
        SELECT part_name FROM lifecycle_partition_bounds(parent)
        WHERE NOT is_default AND upper_bound <= cutoff ORDER BY upper_bound
    LOOP
        EXECUTE format('DROP TABLE %I', rec.part_name);
        dropped := dropped || rec.part_name;
    END LOOP;
    RETURN dropped;
END;
$$
"""

# Построчное стирание в партициях, которые срок хранения пересекает (legacy, DEFAULT): пачкой, чтобы не держать
# длинную транзакцию. Журнал аудита проходит через ту же защиту от DELETE, что и audit_log_purge.
_PURGE_BATCH = """
CREATE FUNCTION audit_log_purge_batch(cutoff timestamptz, batch integer) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    removed bigint;
BEGIN
    PERFORM set_config('hse.audit_purge', 'on', true);
    DELETE FROM audit_log WHERE id IN (SELECT id FROM audit_log WHERE at < cutoff ORDER BY at LIMIT batch);
    GET DIAGNOSTICS removed = ROW_COUNT;
    PERFORM set_config('hse.audit_purge', 'off', true);
    RETURN removed;
END;
$$
"""


def _cutover() -> str:
    return str(op.get_bind().exec_driver_sql(_CUTOVER_SQL).scalar_one().isoformat())


def _prepare(table: str) -> None:
    """Уникальный индекс (id, at) для первичного ключа родителя. Оператор может построить его заранее без блокировки
    записи: `CREATE UNIQUE INDEX CONCURRENTLY <таблица>_idat_uq ON <таблица> (id, at)`; тогда здесь он уже есть."""
    op.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {table}_idat_uq ON {table} (id, at)")


def _swap(table: str, cutover: str) -> None:
    legacy = f"{table}_legacy"
    spec = _TABLES[table]
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT pk_{table}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT pk_{table}_legacy PRIMARY KEY USING INDEX {table}_idat_uq")
    op.execute(
        f"DO $$ DECLARE r record; BEGIN FOR r IN SELECT indexname FROM pg_indexes "
        f"WHERE tablename = '{table}' AND schemaname = 'public' AND indexname LIKE 'ix\\_%' "
        f"LOOP EXECUTE format('ALTER INDEX %I RENAME TO %I', r.indexname, r.indexname || '_l'); END LOOP; END $$"
    )
    if table == "audit_log":
        op.execute("DROP TRIGGER audit_log_no_change ON audit_log")
        op.execute("DROP TRIGGER audit_log_no_truncate ON audit_log")
    op.execute(f"ALTER TABLE {table} RENAME TO {legacy}")
    op.execute(f"CREATE TABLE {table} (LIKE {legacy} INCLUDING DEFAULTS INCLUDING COMMENTS) PARTITION BY RANGE (at)")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT pk_{table} PRIMARY KEY ({spec['key']}, at)")
    for definition in spec["indexes"]:  # type: ignore[attr-defined]
        op.execute(definition)
    op.execute(f"ALTER TABLE {table} ATTACH PARTITION {legacy} FOR VALUES FROM (MINVALUE) TO ('{cutover}')")
    op.execute(f"CREATE TABLE {table}_default PARTITION OF {table} DEFAULT")
    if table == "audit_log":
        op.execute("ALTER SEQUENCE audit_log_id_seq OWNED BY audit_log.id")
        op.execute(
            "CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log "
            "FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()"
        )
        for part in (legacy, f"{table}_default"):
            op.execute(
                f"CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON {part} "
                "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only()"
            )
        op.execute(
            "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
            "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only()"
        )


def upgrade() -> None:
    cutover = _cutover()
    for table in _TABLES:
        _prepare(table)
    op.execute(_BOUNDS)
    op.execute(_ENSURE)
    op.execute(_DROP)
    op.execute(_PURGE_BATCH)
    for table in _TABLES:
        _swap(table, cutover)
    for fn in (
        "lifecycle_partition_bounds(text)",
        "lifecycle_ensure_partitions(text, integer)",
        "lifecycle_drop_partitions_before(text, timestamptz)",
        "audit_log_purge_batch(timestamptz, integer)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
    for table in _TABLES:
        op.execute(f"SELECT lifecycle_ensure_partitions('{table}', 3)")


def _flatten(table: str) -> None:
    spec = _TABLES[table]
    flat = f"{table}_flat"
    op.execute(f"CREATE TABLE {flat} (LIKE {table} INCLUDING DEFAULTS INCLUDING COMMENTS)")
    if table == "audit_log":
        op.execute("ALTER SEQUENCE audit_log_id_seq OWNED BY NONE")
    op.execute(f"INSERT INTO {flat} SELECT * FROM {table}")
    op.execute(f"DROP TABLE {table}")
    op.execute(f"ALTER TABLE {flat} RENAME TO {table}")
    if table == "audit_log":
        op.execute("ALTER SEQUENCE audit_log_id_seq OWNED BY audit_log.id")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT pk_{table} PRIMARY KEY ({spec['key']})")
    for definition in spec["indexes"]:  # type: ignore[attr-defined]
        op.execute(definition)
    if table == "audit_log":
        op.execute("REVOKE ALL ON audit_log FROM PUBLIC")
        op.execute(
            "CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log "
            "FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()"
        )
        op.execute(
            "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
            "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only()"
        )


def downgrade() -> None:
    for table in _TABLES:
        _flatten(table)
    op.execute("DROP FUNCTION audit_log_purge_batch(timestamptz, integer)")
    op.execute("DROP FUNCTION lifecycle_drop_partitions_before(text, timestamptz)")
    op.execute("DROP FUNCTION lifecycle_ensure_partitions(text, integer)")
    op.execute("DROP FUNCTION lifecycle_partition_bounds(text)")

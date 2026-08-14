# Alembic migrations, explained

Notes on adopting Alembic on a database that already had tables — not the
plain "first migration ever" flow, which is a slightly different sequence.

## Why this replaced `create_all()`

`app/database.py` used to expose `init_db()`, called from `app/main.py`'s
`lifespan` on every app startup:

```python
def init_db() -> None:
    from app.models import db as _models
    Base.metadata.create_all(bind=engine)
```

`create_all()` can only do one thing: create a table that doesn't exist
yet. It has no way to *alter* an existing one — add a column, rename one,
change a type. There was no real way to evolve the schema without manually
hand-editing the database. Both `init_db()` and the `lifespan` are now
gone entirely — schema management belongs to Alembic, run explicitly, not
implicitly on every boot.

## The problem: adopting Alembic on a database that already matches the models

A brand-new project runs `alembic revision --autogenerate` against an
empty database, and the generated migration *is* the "create everything"
script. This project wasn't in that position — the real dev database
(`resume_screening`) already had `candidates`, `jobs`, and `match_results`
from years (well, weeks) of `create_all()` runs. Autogenerating directly
against it would compare the database to the models, find they already
match, and produce a useless empty migration.

**The fix**: generate the migration against a database that's actually
empty, then handle the already-populated one separately.

```bash
# 1. Force the test database empty (it already existed from the test suite work)
python3 -c "
from sqlalchemy import create_engine
from app.database import Base
from app.models import db as _models
engine = create_engine('postgresql://postgres:postgres@127.0.0.1:5433/resume_screening_test')
Base.metadata.drop_all(bind=engine)
"

# 2. Autogenerate against that empty database
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/resume_screening_test \
  alembic revision --autogenerate -m "initial schema"
```

This produced `alembic/versions/cb36370cdbb9_initial_schema.py` — reviewed
by hand, and it correctly captured every column, type, and constraint from
`app/models/db.py`: `UUID` primary keys, `JSONB` columns, the
`unique=True` on both `pinecone_id` columns, and the two foreign keys on
`match_results`.

**Two different commands for two different environments**:

```bash
# The already-populated dev DB: mark it as "already here", run no DDL
alembic stamp head

# A fresh environment (a new clone, CI, eventually production): actually create the tables
alembic upgrade head
```

`stamp` writes a row to Alembic's own `alembic_version` tracking table
without touching the schema at all — correct here, since the schema
already matches exactly. Running `upgrade head` against the dev DB instead
would have failed outright (`relation "candidates" already exists`).

## `alembic/env.py` — wired to the app's own settings, not a second config

```python
from app.config import get_settings
from app.database import Base
from app.models import db as _models  # noqa: F401 - registers model classes on Base.metadata

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata
```

Two things worth noting:
- **One source of truth for the connection string.** `alembic.ini`'s own
  `sqlalchemy.url` line is left as an unused placeholder — Alembic reads
  `DATABASE_URL` through the exact same `Settings` class everything else
  in the app uses, instead of a second, easily-drifting config file.
- **The `_models` import isn't decorative.** `Base.metadata` only knows
  about model classes that have actually been imported somewhere —
  without this line, `target_metadata` would be an empty, table-less
  `MetaData` object and autogenerate would see nothing to compare against.

## CI: a verification step, not a deployment step

```yaml
- name: Verify migrations apply to a fresh database
  env:
    DATABASE_URL: postgresql://postgres:postgres@localhost:5432/resume_screening_test
  run: alembic upgrade head
```

Added to `.github/workflows/ci.yml`, right before the `pytest` step. This
proves the migration genuinely applies cleanly to a brand-new database —
GitHub Actions' Postgres service container starts empty on every run, so
this is a real test of the "fresh environment" path, not just a local
sanity check. `pytest`'s own `Base.metadata.create_all()`/`drop_all()`
fixtures still run afterward exactly as before — `create_all()` is
idempotent, so tables the migration already created don't cause a
conflict.

## What's deliberately not done here

- **No Kubernetes/Helm migration step.** The Helm chart still assumes the
  schema already exists — an initContainer or a one-shot Job running
  `alembic upgrade head` before the app starts is the natural next piece,
  not built in this pass. Same treatment as the documented KEDA/queue-depth
  autoscaling gap.
- **`Dockerfile` doesn't copy `alembic.ini`/`alembic/` into the image** —
  only `COPY app ./app`. Irrelevant until the deployment wiring above
  happens; not a gap on its own right now, since nothing currently needs
  to run migrations from inside the built image.
- **The pytest suite still uses `Base.metadata.create_all()`**, not real
  migrations, for building its schema — a deliberate choice to keep the
  already-working SAVEPOINT-based test isolation simple and fast. Migration
  correctness is covered by the CI step above instead.

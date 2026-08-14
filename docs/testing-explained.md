# Testing, explained

Notes on `tests/`. **Happy-path only** — every test here covers the
success case for something; error/edge-case tests are a deliberate,
separate follow-up, not an oversight.

## The two decisions that shaped everything else

**Real Postgres, not SQLite.** `app/models/db.py` uses `UUID(as_uuid=True)`
from `sqlalchemy.dialects.postgresql` — a Postgres-specific type. SQLite
would silently behave differently (or fail) on exactly the type real
production code depends on, so tests run against a real Postgres: a
dedicated `resume_screening_test` database in the *same* docker-compose
Postgres container used for local dev, and a Postgres **service container**
in CI (`.github/workflows/ci.yml`). Neither ever touches the real
`resume_screening` dev database.

**Every test rolls back cleanly, even though application code calls
`db.commit()`.** `candidate_service.py`, `job_service.py`, `ranking.py`,
and `app/worker.py` all call `.commit()` internally — normal application
behavior we don't want to change just to make testing easier. SQLAlchemy
2.0 has a built-in answer: `sessionmaker(bind=connection,
join_transaction_mode="create_savepoint")`. Every `Session` built from that
factory nests into one connection's outer transaction via `SAVEPOINT`.
Application code's `commit()` only releases the savepoint; a final
`rollback()` on the outer transaction at test teardown discards
*everything* — no manual cleanup between tests, no risk of one test's data
leaking into the next.

## `tests/conftest.py` — the fixtures, and why each one exists

```python
test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
```
A **separate** engine from `app.database.engine` (which stays bound to the
dev `DATABASE_URL`). `TEST_DATABASE_URL` is read from an environment
variable, defaulting locally to
`postgresql://postgres:postgres@127.0.0.1:5433/resume_screening_test` — CI
sets it explicitly to point at its own service container instead (see
below).

```python
@pytest.fixture(scope="session")
def _test_schema(): ...  # Base.metadata.create_all / drop_all
```
Runs once per test session — and **deliberately not `autouse`**. Only
fixtures that actually need the database (`db_connection` and everything
built on it) pull this in. Confirmed by actually running
`tests/test_resume_parser.py` and `tests/test_ranking_embed_text.py` with
`TEST_DATABASE_URL` pointed at an unreachable address — both files still
passed, proving those tests genuinely never touch Postgres.

```python
@pytest.fixture
def db_connection(_test_schema): ...  # one connection + one outer transaction
@pytest.fixture
def session_factory(db_connection): ...  # join_transaction_mode="create_savepoint"
@pytest.fixture
def db_session(session_factory): ...
```
One connection, one outer transaction, per test — rolled back at teardown.
`session_factory` is exposed as its own fixture (not just baked into
`db_session`) specifically so `app/worker.py` tests can get a *sessionmaker*
to monkeypatch onto `worker.SessionLocal`, since `_process_message()` opens
its own session rather than using FastAPI's `get_db`.

```python
@pytest.fixture
def client(db_session): ...
```
**A real bug found and designed around before it happened**: `app/main.py`
runs a `lifespan()` that calls `init_db()` — `Base.metadata.create_all()`
against `app.database.engine`, the **dev** database, not the test one.
Entering `TestClient` as `with TestClient(app) as c:` triggers that
lifespan startup. This fixture instantiates `TestClient(app)` plainly
instead — lifespan never runs, and schema setup stays fully owned by
`_test_schema` against the correct database.

```python
@pytest.fixture
def mock_vector_store(monkeypatch): ...
```
`vector_store` (`app/services/embeddings.py`) is imported *by name* into
`candidate_service.py`, `job_service.py`, and `ranking.py` — all three hold
a reference to the exact same object. The fix isn't to patch the name in
each importing module separately; it's to monkeypatch **methods on that one
shared instance** (`monkeypatch.setattr(vector_store, "upsert_candidate",
...)`), which every consumer sees automatically.

## `tests/factories.py` — fakes and builders

`get_llm()`'s real return value gets used as `PROMPT | llm` (a LangChain
`Runnable` composition) before `.invoke(...)` is called — so a fake `llm`
has to be a real `Runnable` too, not just any object with an `.invoke()`
method. `FakeStructuredLLM.with_structured_output()` returns a
`langchain_core.runnables.RunnableLambda` wrapping a fixed value, which
satisfies that requirement for free. `FakePdfReader`/`FakePdfPage` are a
minimal stand-in for `pypdf.PdfReader` so tests never need a real PDF file
on disk. `make_parsed_resume`/`make_match_explanation`/`make_candidate_create`/`make_job_create`
are builders with sensible defaults and `**overrides` for the one field a
given test actually cares about.

## Where each mock gets patched, and why it's not always the "obvious" place

`get_llm` and `PdfReader` are both *name-imports* into their consuming
modules (`from app.llm.ollama_client import get_llm`,
`from pypdf import PdfReader`) — Python copies the reference into the
importing module's own namespace at import time. Patching
`app.llm.ollama_client.get_llm` after that point does **nothing** to
`resume_parser.py`'s already-bound copy. Every mock in this suite patches
at the *consuming* module (`app.services.resume_parser.get_llm`,
`app.services.matching.get_llm`), not the source.

## CI changes (`.github/workflows/ci.yml`)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    env:
      POSTGRES_DB: resume_screening_test
    ports:
      - 5432:5432
```
A **service container** — GitHub Actions spins up Postgres as a sibling
container to the job, reachable at `localhost:5432` from the runner (no
port-shifting needed like the local `5433`, since there's no host Postgres
to conflict with on an ephemeral CI VM). `TEST_DATABASE_URL` is set
explicitly on the `Test` step to point at it. The old
`pytest || [ $? -eq 5 ]` "no tests collected" workaround is gone — it did
its job as a stopgap and is no longer needed now that real tests exist.

## Running it

```bash
# one-time local setup
docker compose exec postgres psql -U postgres -c "CREATE DATABASE resume_screening_test;"

pytest -v
```

## Error/edge-case coverage (added after the happy-path pass)

Same fixtures, same mocking patterns — just exercising the other branch of
each `try`/`except` in `app/exceptions.py`'s exception-to-HTTP-status
mapping:

- Blank/scanned PDF → `ValueError` (`resume_parser`)
- Non-PDF upload → `400`
- Unparseable resume (`ValueError` from parsing) → `422`
- LLM unavailable (generic exception from parsing) → `503`
- Vector indexing failure on create → `502`
- Unknown candidate/job id → `404`
- Unknown job id on `/screening/rank` → `404`
- Zero vector matches → a valid empty result (`200`, not an error) — worth
  locking in explicitly so "no candidates found" never regresses into a 500
- `app/worker.py`'s `_process_message` correctly propagates
  `ResumeContentError` for an empty resume, and never reaches
  `_mark_status` when it does (verified via `fake_table.update_item.assert_not_called()`)

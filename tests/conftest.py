from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from app.auth import require_api_key
from app.database import Base, get_db
from app.main import app
from app.models.db import Tenant

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:5433/resume_screening_test",
)

# Dedicated engine for the test database. Never shares app.database.engine,
# which stays bound to the *dev* DATABASE_URL.
test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)


@pytest.fixture(scope="session")
def _test_schema() -> Generator[None, None, None]:
    """Create tables once per test session. Not autouse: only tests that
    actually need the DB (via db_connection below) pay this cost, so pure
    unit tests (resume_parser text/LLM mocks, ranking embed-text builders)
    never require Postgres to be reachable at all."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_connection(_test_schema) -> Generator[Connection, None, None]:
    """One connection + one outer transaction per test. Rolling this back
    at teardown discards everything the test did, including anything
    application code committed (see db_session/session_factory)."""
    connection = test_engine.connect()
    outer_txn = connection.begin()
    try:
        yield connection
    finally:
        outer_txn.rollback()
        connection.close()


@pytest.fixture
def session_factory(db_connection: Connection) -> sessionmaker:
    """Sessionmaker bound to this test's single connection.
    join_transaction_mode="create_savepoint" means every Session made from
    this factory nests into db_connection's outer transaction via
    SAVEPOINT; app code's db.commit() only releases the savepoint."""
    return sessionmaker(bind=db_connection, join_transaction_mode="create_savepoint")


@pytest.fixture
def db_session(session_factory: sessionmaker) -> Generator[Session, None, None]:
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def tenant(db_session: Session) -> Tenant:
    """A real Tenant row - candidates/jobs have a NOT NULL FK to it, so
    even tests that bypass auth need a real tenant_id to attach rows to."""
    t = Tenant(name="Test Tenant")
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture
def client(db_session: Session, tenant: Tenant) -> Generator[TestClient, None, None]:
    """TestClient with get_db overridden and auth resolved to a fixed test
    tenant. Deliberately NOT `with TestClient(app) as c:` - entering that
    context runs app.main's lifespan, which calls init_db() against
    app.database.engine (the *dev* DATABASE_URL), not the test DB. Schema
    setup here is fully owned by _test_schema.

    Auth is bypassed (not exercised) here so the ~26 functional tests using
    this fixture don't all need a real API key threaded through them just
    to reach the behavior they're actually testing - see test_auth.py for
    tests of the auth dependency itself, which use `authenticated_client`
    instead."""

    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[require_api_key] = lambda: tenant.id
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_api_key, None)


@pytest.fixture
def authenticated_client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with only get_db overridden - the real require_api_key
    dependency runs, so tests using this fixture exercise actual auth
    enforcement (see test_auth.py)."""

    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def worker_session_local(session_factory: sessionmaker) -> sessionmaker:
    """Monkeypatch this onto app.worker.SessionLocal in worker tests.
    _process_message() creates its own Session via SessionLocal() rather
    than through get_db, so it needs its own hookup into the same
    per-test connection/transaction to roll back cleanly."""
    return session_factory


@pytest.fixture
def mock_vector_store(monkeypatch):
    """Patch methods directly on the shared vector_store singleton.
    vector_store is imported *by name* into candidate_service, job_service,
    and ranking (`from app.services.embeddings import vector_store`), so
    all three hold references to the exact same VectorStore object -
    patching methods on that one instance (not reassigning the name in
    each importing module) is what actually affects all of them."""
    from app.services.embeddings import vector_store

    monkeypatch.setattr(
        vector_store,
        "upsert_candidate",
        lambda candidate_id, text, metadata, namespace: f"candidate-{candidate_id}",
    )
    monkeypatch.setattr(
        vector_store,
        "upsert_job",
        lambda job_id, text, metadata, namespace: f"job-{job_id}",
    )
    monkeypatch.setattr(
        vector_store,
        "query_similar_candidates",
        lambda job_text, namespace, top_k=20: [],
    )
    return vector_store

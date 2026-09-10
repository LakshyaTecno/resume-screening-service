"""Cross-tenant isolation: a resource created under one tenant's API key
must be invisible to every other tenant, across list, get-by-id, and -
most importantly - ranking, which reaches candidates indirectly through
Pinecone rather than a direct lookup."""

from app.auth import _hash_key
from app.models.db import ApiKey, Tenant
from app.services import ranking
from tests.factories import make_match_explanation


def _make_tenant_with_key(db_session, name: str, raw_key: str) -> Tenant:
    tenant = Tenant(name=name)
    db_session.add(tenant)
    db_session.flush()
    db_session.add(
        ApiKey(tenant_id=tenant.id, hashed_key=_hash_key(raw_key), key_prefix=raw_key[:8])
    )
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def test_candidate_created_by_one_tenant_is_invisible_to_another(
    authenticated_client, db_session, mock_vector_store
):
    _make_tenant_with_key(db_session, "Tenant A", "key-a")
    _make_tenant_with_key(db_session, "Tenant B", "key-b")

    create_response = authenticated_client.post(
        "/api/v1/candidates/",
        headers={"X-API-Key": "key-a"},
        json={"full_name": "Alice", "skills": [], "experience": [], "education": []},
    )
    candidate_id = create_response.json()["id"]

    # Tenant B can't see it in their list.
    list_response = authenticated_client.get("/api/v1/candidates/", headers={"X-API-Key": "key-b"})
    assert candidate_id not in [c["id"] for c in list_response.json()]

    # Tenant B can't fetch it directly by id either - 404, not a data leak.
    get_response = authenticated_client.get(
        f"/api/v1/candidates/{candidate_id}", headers={"X-API-Key": "key-b"}
    )
    assert get_response.status_code == 404

    # Tenant A can still see their own candidate.
    own_get_response = authenticated_client.get(
        f"/api/v1/candidates/{candidate_id}", headers={"X-API-Key": "key-a"}
    )
    assert own_get_response.status_code == 200
    assert own_get_response.json()["id"] == candidate_id


def test_job_created_by_one_tenant_is_invisible_to_another(
    authenticated_client, db_session, mock_vector_store
):
    _make_tenant_with_key(db_session, "Tenant A", "key-a")
    _make_tenant_with_key(db_session, "Tenant B", "key-b")

    create_response = authenticated_client.post(
        "/api/v1/jobs/",
        headers={"X-API-Key": "key-a"},
        json={"title": "Backend Engineer", "description": "Build APIs."},
    )
    job_id = create_response.json()["id"]

    get_response = authenticated_client.get(
        f"/api/v1/jobs/{job_id}", headers={"X-API-Key": "key-b"}
    )
    assert get_response.status_code == 404


def test_ranking_cannot_resolve_another_tenants_candidate_even_if_vector_layer_is_misconfigured(
    authenticated_client, db_session, mock_vector_store, monkeypatch
):
    """Simulates the exact failure mode namespace scoping is meant to
    prevent: a Pinecone query somehow returns a candidate_id belonging to
    a different tenant (e.g. a namespace bug). The DB-level tenant filter
    in candidate_repository.get_by_id must still refuse to resolve it."""
    _make_tenant_with_key(db_session, "Tenant A", "key-a")
    _make_tenant_with_key(db_session, "Tenant B", "key-b")

    candidate_response = authenticated_client.post(
        "/api/v1/candidates/",
        headers={"X-API-Key": "key-a"},
        json={"full_name": "Alice", "skills": [], "experience": [], "education": []},
    )
    tenant_a_candidate_id = candidate_response.json()["id"]

    job_response = authenticated_client.post(
        "/api/v1/jobs/",
        headers={"X-API-Key": "key-b"},
        json={"title": "Backend Engineer", "description": "Build APIs."},
    )
    job_id = job_response.json()["id"]

    # Simulate a leaky vector layer: tenant B's ranking query somehow gets
    # back tenant A's candidate id.
    monkeypatch.setattr(
        ranking.vector_store,
        "query_similar_candidates",
        lambda job_text, namespace, top_k=20: [
            {"candidate_id": tenant_a_candidate_id, "vector_score": 0.99, "metadata": {}}
        ],
    )
    monkeypatch.setattr(
        ranking, "generate_match_explanation", lambda **kwargs: make_match_explanation()
    )

    response = authenticated_client.post(
        "/api/v1/screening/rank",
        headers={"X-API-Key": "key-b"},
        json={"job_id": job_id},
    )

    assert response.status_code == 200
    body = response.json()
    # The vector layer "found" one match, but the tenant-scoped DB lookup
    # must refuse to resolve it - zero candidates actually ranked.
    assert body["ranked_candidates"] == []

import httpx

from tests.test_discovery import valid_create_service_payload


async def test_no_auth_when_token_not_set(client):
    """When API_TOKEN is not set, requests pass through without auth."""
    response = await client.get("/health")
    assert response.status_code == 200


async def test_auth_rejects_missing_token(monkeypatch):
    """When API_TOKEN is set, requests without token are rejected."""
    monkeypatch.setenv("API_TOKEN", "test-secret-token")

    # Re-import to pick up new settings
    from app.core.config import Settings
    import app.core.security as sec
    import app.core.config as cfg

    cfg.settings = Settings()
    sec.settings = cfg.settings

    from main import app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        response = await test_client.post(
            "/create-new-service",
            json=valid_create_service_payload(),
        )
    assert response.status_code == 403

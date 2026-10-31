import importlib

from main import app


def valid_create_service_payload():
    return {
        "create-repository": True,
        "service-name": "test-service",
        "github-owner": "SparrowX-Labs",
        "repository-url": "",
        "prod-required": False,
        "runtime": "python",
        "base-image": "python:3.12-slim",
        "container-port": 8000,
        "api-path": "/api/test-service",
        "dev-hostname": "test.dev.example.com",
        "prod-hostname": "",
        "external-health-path": "/api/test-service/health",
        "internal-health-path": "/health",
        "database-enabled": True,
        "database-enabled-prod": False,
        "database-engine": "postgres",
        "multi-az-enabled": True,
        "database-version": "16",
        "database-size-dev": "small",
        "database-storage-dev": 20,
        "database-size-prod": "medium",
        "database-storage-prod": 20,
        "object-storage-enabled": False,
        "object-storage-name": "",
        "object-storage-enabled-prod": False,
        "object-storage-name-prod": "",
        "replica-count-dev": 1,
        "pod-size-dev": "small",
        "enable-probes-dev": True,
        "enable-service-monitor-dev": True,
        "replica-count-prod": 0,
        "pod-size-prod": "",
        "enable-probes-prod": False,
        "enable-service-monitor-prod": False,
    }


class FakeProject:
    def __init__(self, path):
        self.html_url = f"https://github.com/{path}"


class FakeGitProvider:
    def __init__(self):
        self.merged_requests = []

    def get_project(self, path):
        return FakeProject(path)

    def create_project(self, name, owner):
        return FakeProject(f"{owner}/{name}")

    def create_branch(self, project, branch, source):
        return None

    def commit_files(self, project, branch, actions, message):
        return "https://github.com/example/commit/1"

    def create_merge_request(self, project, source_branch, target_branch):
        return f"https://github.com/example/pull/{source_branch}"

    def merge_merge_request(self, project, source_branch, target_branch):
        self.merged_requests.append((source_branch, target_branch))


async def test_modules_registered(client):
    """All modules from modules.yaml should be registered as routes."""
    routes = [r.path for r in app.routes]
    assert "/create-new-service" in routes
    assert "/list-directory" in routes
    assert "/pwd" in routes
    assert "/mkdir" in routes


async def test_create_service_returns_validation_error(client):
    """Calling a module endpoint with missing required fields returns 422."""
    response = await client.post("/create-new-service", json={})
    assert response.status_code == 422


async def test_create_service_accepts_valid_payload(client, monkeypatch):
    """The new service module validates and provisions through the Git provider."""
    module = importlib.import_module("app.modules.create-new-service.module")
    fake_git = FakeGitProvider()
    monkeypatch.setattr(module, "get_git_provider", lambda provider: fake_git)

    response = await client.post("/create-new-service", json=valid_create_service_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["service_name"] == "test-service"
    assert len(data["merge_request_urls"]) == 4
    assert len(fake_git.merged_requests) == 4
    assert set(data["phase_status"].values()) == {"merged"}

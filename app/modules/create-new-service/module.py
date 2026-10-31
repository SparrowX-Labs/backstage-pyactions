from __future__ import annotations

import time
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.core.logging import ActionLogger
from app.core.dependencies import get_git_provider
from .schemas import CreateNewServiceParams


ORG_REPOS = {
    "crossplane": "SparrowX-Labs/crossplane",
    "argocd": "SparrowX-Labs/ArgoCD-Apps",
    "gateway": "SparrowX-Labs/gateway-api",
}


def _repository_path(repository_url: str) -> str:
    parsed = urlparse(repository_url)
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if parsed.scheme != "https" or parsed.netloc != "github.com" or len(parts) != 2 or not all(parts):
        raise ValueError("repository-url must be an https GitHub repository URL")
    return "/".join(parts)


def _validate_request(params: CreateNewServiceParams) -> None:
    """Validate cross-field constraints before making any GitHub changes."""

    expected_prefix = "node:" if params.runtime == "node" else "python:"
    if not params.base_image.startswith(expected_prefix):
        raise ValueError(f"base-image must start with {expected_prefix} for runtime {params.runtime}")

    if not params.create_repository:
        if not params.repository_url:
            raise ValueError("repository-url is required when create-repository is false")
        _repository_path(params.repository_url)

    if params.prod_required:
        if not params.prod_hostname:
            raise ValueError("prod-hostname is required when prod-required is true")
        if params.replica_count_prod < 1:
            raise ValueError("replica-count-prod must be at least 1 when prod-required is true")
        if not params.pod_size_prod:
            raise ValueError("pod-size-prod is required when prod-required is true")


def _database_name(service_name: str) -> str:
    return f"{service_name.split('-')[0]}db"


def _context(params: CreateNewServiceParams, environment: str) -> dict:
    is_frontend = params.runtime == "node"
    database_enabled = (
        params.database_enabled if environment == "dev" else params.database_enabled_prod
    ) and not is_frontend
    hostname = params.dev_hostname if environment == "dev" else params.prod_hostname

    return {
        "service_name": params.service_name,
        "runtime": params.runtime,
        "is_frontend": is_frontend,
        "base_image": params.base_image,
        "container_port": params.container_port,
        "environment": environment,
        "hostname": hostname,
        "api_path": "/" if is_frontend else params.api_path,
        "internal_health_path": "/" if is_frontend else params.internal_health_path,
        "external_health_path": params.external_health_path,
        "database_enabled": database_enabled,
        "database_engine": params.database_engine,
        "multi_az_enabled": params.multi_az_enabled if environment == "prod" else False,
        "database_name": _database_name(params.service_name),
        "database_version": params.database_version,
        "database_size": params.database_size_dev if environment == "dev" else params.database_size_prod,
        "database_storage": params.database_storage_dev if environment == "dev" else params.database_storage_prod,
        "object_storage_enabled": (
            params.object_storage_enabled if environment == "dev" else params.object_storage_enabled_prod
        ),
        "object_storage_name": (
            params.object_storage_name if environment == "dev" else params.object_storage_name_prod
        ),
        "replica_count": params.replica_count_dev if environment == "dev" else params.replica_count_prod,
        "pod_size": params.pod_size_dev if environment == "dev" else params.pod_size_prod,
        "enable_probes": params.enable_probes_dev if environment == "dev" else params.enable_probes_prod,
        "enable_service_monitor": params.enable_service_monitor_dev if environment == "dev" else params.enable_service_monitor_prod,
        "github_owner": params.github_owner,
        "repository_url": params.repository_url,
        "prod_required": params.prod_required,
    }


def _render_templates(env: Environment, params: CreateNewServiceParams, environment: str) -> dict[str, str]:
    context = _context(params, environment)
    prefix = "frontend" if params.runtime == "node" else "backend"

    files = {
        "Dockerfile": env.get_template(f"sparrowx/docker/Dockerfile-{prefix}").render(**context),
        ".github/workflows/ci.yaml": env.get_template("sparrowx/ci-cd/ci.yaml").render(**context),
        ".github/workflows/pr-validation.yaml": env.get_template("sparrowx/ci-cd/pr-validation.yaml").render(**context),
        ".github/workflows/deploy-dev.yaml": env.get_template("sparrowx/ci-cd/deploy-dev.yaml").render(**context),
        ".github/workflows/promote-prod.yaml": env.get_template("sparrowx/ci-cd/promote-prod.yaml").render(**context),
        ".github/workflows/rollback-prod.yaml": env.get_template("sparrowx/ci-cd/rollback-prod.yaml").render(**context),
        "app-sec-policy.yaml": env.get_template("sparrowx/app-sec-policy/app-sec-policy.yaml").render(**context),
        "catalog-info.yaml": env.get_template("sparrowx/backstage-catalog/catalog-info.yaml").render(**context),
        "helm-values-dev.yaml": env.get_template("sparrowx/argo-values/app-helm-values.yaml").render(
            **_context(params, "dev")
        ),
    }

    return files


def _render_environment_files(
    env: Environment, params: CreateNewServiceParams, environment: str, repository_url: str
) -> dict[str, dict[str, str]]:
    context = _context(params, environment)
    context["repository_url"] = repository_url
    return {
        "crossplane": {
            f"environments/{environment}/{params.service_name}.yaml": env.get_template(
                "sparrowx/argo-values/crossplane-values.yaml"
            ).render(**context),
        },
        "argocd": {
            f"{environment}/infrastructure/{params.service_name}.yaml": env.get_template(
                "sparrowx/argo-apps/resources-app.yaml"
            ).render(**context),
            f"{environment}/applications/{params.service_name}.yaml": env.get_template(
                "sparrowx/argo-apps/application-app.yaml"
            ).render(**context),
        },
        "gateway": {
            f"{environment}/{params.service_name}.yaml": env.get_template(
                "sparrowx/argo-values/gateway-values.yaml"
            ).render(**context),
        },
    }


def _provision_repository(
    git,
    logger: ActionLogger,
    repository_path: str,
    branch: str,
    files: dict[str, str],
    message: str,
) -> str:
    project = git.get_project(repository_path)
    git.create_branch(project, branch, "main")
    actions = [{"action": "create", "file_path": path, "content": content} for path, content in files.items()]
    commit_url = git.commit_files(project, branch, actions, message)
    if not commit_url:
        raise RuntimeError(f"GitHub commit failed for {repository_path} on branch {branch}")
    pull_request = git.create_merge_request(project, branch, "main")
    git.merge_merge_request(project, branch, "main")
    logger.append(f"Created and merged pull request for {repository_path}: {pull_request}")
    return pull_request


async def handler(params: CreateNewServiceParams):
    logger = ActionLogger()
    errors: list[str] = []
    phase_status: dict[str, str] = {}
    merge_request_urls: list[str] = []

    try:
        _validate_request(params)
        git = get_git_provider("github")
        templates = Environment(
            loader=FileSystemLoader("app/templates"),
            autoescape=False,
            undefined=StrictUndefined,
            variable_start_string="[[",
            variable_end_string="]]",
        )
        repository_url = params.repository_url or f"https://github.com/{params.github_owner}/{params.service_name}.git"

        if params.database_enabled and params.runtime == "node":
            logger.append("Frontend selected: database provisioning is disabled for the generated infrastructure")

        service_files = _render_templates(templates, params, "dev")
        if params.prod_required:
            service_files["helm-values-prod.yaml"] = templates.get_template(
                "sparrowx/argo-values/app-helm-values.yaml"
            ).render(
                **_context(params, "prod")
            )

        generated_by_target: dict[str, dict[str, str]] = {
            "argocd": {},
            "crossplane": {},
            "gateway": {},
        }
        environments = ("dev", "prod") if params.prod_required else ("dev",)
        for environment in environments:
            generated = _render_environment_files(templates, params, environment, repository_url)
            for target, files in generated.items():
                generated_by_target[target].update(files)

        branch = f"feature/add-new-service-{params.service_name}"
        for target, files in generated_by_target.items():
            phase_name = target.title()
            try:
                repository = ORG_REPOS[target]
                merge_request_urls.append(
                    _provision_repository(
                        git,
                        logger,
                        repository,
                        branch,
                        files,
                        f"Add {params.service_name} configuration",
                    )
                )
                phase_status[phase_name] = "merged"
            except Exception as exc:
                phase_status[phase_name] = "failed"
                errors.append(f"{phase_name}: {exc}")

        if errors:
            return {
                "status": "failed",
                "phase_status": phase_status,
                "errors": errors,
                "logs": logger.logs,
                "merge_request_urls": merge_request_urls,
            }

        if params.create_repository:
            service_project = git.create_project(params.service_name, params.github_owner)
            logger.append(f"Service repository ready: {service_project.html_url}")
        else:
            service_project = git.get_project(_repository_path(params.repository_url))
            logger.append(f"Using existing service repository: {service_project.html_url}")

        service_branch = "feature/bootstrapping-repo"
        for attempt in range(5):
            try:
                git.create_branch(service_project, service_branch, "main")
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(2)

        actions = [
            {"action": "create", "file_path": path, "content": content}
            for path, content in service_files.items()
        ]
        commit_url = git.commit_files(
            service_project,
            service_branch,
            actions,
            f"Bootstrap {params.service_name} service repository",
        )
        if not commit_url:
            raise RuntimeError(f"GitHub commit failed for service repository {params.service_name}")
        service_pr = git.create_merge_request(service_project, service_branch, "main")
        git.merge_merge_request(service_project, service_branch, "main")
        merge_request_urls.append(service_pr)
        phase_status["Service repository"] = "merged"
        logger.append(f"Created and merged service repository pull request: {service_pr}")

        return {
            "status": "success",
            "service_name": params.service_name,
            "phase_status": phase_status,
            "errors": [],
            "logs": logger.logs,
            "merge_request_urls": merge_request_urls,
        }
    except Exception as exc:
        logger.append(f"Create-new-api failed: {exc}", level="error")
        errors.append(str(exc))
        return {
            "status": "failed",
            "service_name": params.service_name,
            "phase_status": phase_status,
            "errors": errors,
            "logs": logger.logs,
            "merge_request_urls": merge_request_urls,
        }

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateNewServiceParams(BaseModel):
    """Input contract for the Backstage Create New Service template."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )

    # Repository and environment configuration.
    create_repository: bool = Field(alias="create-repository")
    service_name: str = Field(
        alias="service-name",
        min_length=3,
        max_length=40,
        pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$",
    )
    github_owner: str = Field(alias="github-owner", min_length=1)
    repository_url: str = Field(default="", alias="repository-url")
    prod_required: bool = Field(alias="prod-required")

    # Application configuration. The runtime selects backend or frontend behavior.
    runtime: Literal["python", "node"]
    base_image: str = Field(alias="base-image", min_length=1)
    container_port: int = Field(alias="container-port", ge=1, le=65535)
    api_path: str = Field(alias="api-path", pattern=r"^/api/[a-z0-9][a-z0-9/-]*[a-z0-9]$")
    dev_hostname: str = Field(alias="dev-hostname", min_length=1)
    prod_hostname: str = Field(default="", alias="prod-hostname")
    external_health_path: str = Field(alias="external-health-path", pattern=r"^/[^ ]*$")
    internal_health_path: str = Field(alias="internal-health-path", pattern=r"^/[^ ]*$")

    # Database configuration. The platform currently supports PostgreSQL only.
    database_enabled: bool = Field(alias="database-enabled")
    database_engine: Literal["postgres"] = Field(alias="database-engine")
    multi_az_enabled: bool = Field(default=True, alias="multi-az-enabled")
    database_name: str = Field(default="", alias="database-name")
    database_version: Literal["16"] = Field(default="16", alias="database-version")
    database_size_dev: Literal["small", "medium", "large", "xlarge"] = Field(
        default="small",
        alias="database-size-dev",
    )
    database_storage_dev: int = Field(default=20, alias="database-storage-dev", ge=20)
    database_size_prod: Literal["small", "medium", "large", "xlarge"] = Field(
        default="medium",
        alias="database-size-prod",
    )
    database_storage_prod: int = Field(default=20, alias="database-storage-prod", ge=20)

    # Optional object storage configuration.
    object_storage_enabled: bool = Field(alias="object-storage-enabled")
    object_storage_name: str = Field(default="", alias="object-storage-name")

    # Kubernetes deployment configuration.
    replica_count_dev: int = Field(alias="replica-count-dev", ge=1, le=10)
    pod_size_dev: Literal["micro", "small", "medium", "large", "xlarge"] = Field(
        alias="pod-size-dev",
    )
    enable_probes_dev: bool = Field(alias="enable-probes-dev")
    enable_service_monitor_dev: bool = Field(alias="enable-service-monitor-dev")
    replica_count_prod: int = Field(default=0, alias="replica-count-prod", ge=0, le=20)
    pod_size_prod: Literal["", "micro", "small", "medium", "large", "xlarge"] = Field(
        default="",
        alias="pod-size-prod",
    )
    enable_probes_prod: bool = Field(default=False, alias="enable-probes-prod")
    enable_service_monitor_prod: bool = Field(default=False, alias="enable-service-monitor-prod")

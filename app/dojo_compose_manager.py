import subprocess
import yaml
import logging
import docker
from docker.models.containers import Container
from docker.errors import APIError, NotFound
from pathlib import Path
from .dojo_user_instance import DojoUserInstance

logger = logging.getLogger(__name__)


class DojoComposeManager:
    def __init__(self, user_instance: DojoUserInstance):
        self._user_instance = user_instance
        self._client = docker.from_env()

    def exec_compose_up(self) -> None:
        if not self._user_instance.has_compose_file():
            raise FileNotFoundError(
                f"Compose file not found for challenge: {self._user_instance.compose_file_path}"
            )

        compose_file_path = self._build_sanitized_compose_file()
        subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                self._user_instance.compose_project_name,
                "-f",
                str(compose_file_path),
                "up",
                "-d",
            ],
            check=True,
        )

        container = self.resolve_container_from_id(self._user_instance.instance_id)
        container.reload()

        for network in self._client.networks.list():
            if network.name and network.name.startswith(
                self._user_instance.compose_project_name
            ):
                network.connect(container)

    def exec_compose_down(self) -> None:
        if not self._user_instance.has_compose_file():
            raise FileNotFoundError(
                f"Compose file not found for challenge: {self._user_instance.compose_file_path}"
            )

        try:
            for network in self._client.networks.list():
                if network.name and network.name.startswith(
                    self._user_instance.compose_project_name
                ):
                    try:
                        network.disconnect(self._user_instance.instance_id, force=True)
                    except:
                        # Container might already be stopped and removed by the time we try to disconnect it, so we ignore any errors here
                        pass
        except:
            logger.exception(
                f"Pre-cleanup of networks failed for container {self._user_instance.instance_id} and project {self._user_instance.compose_project_name}, proceeding with compose down anyway"
            )

        compose_file_path = self._build_sanitized_compose_file()
        subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                self._user_instance.compose_project_name,
                "-f",
                str(compose_file_path),
                "down",
            ],
            check=True,
        )

    def resolve_container_from_id(self, container_id: str, retry: int = 3) -> Container:
        try:
            container = self._client.containers.get(container_id)
            return container
        except (NotFound, APIError):
            if --retry > 0:
                return self.resolve_container_from_id(container_id, retry=retry)
            else:
                raise ValueError(
                    f"Container with id '{container_id}' not found after multiple attempts"
                )

    def _build_sanitized_compose_file(self) -> Path:
        data = yaml.safe_load(self._user_instance.compose_file_path.read_text())

        required_keys = {"services"}
        forbidden_keys_by_scope = {
            "service": {"build", "ports", "environment", "container_name", "volumes"},
            "root": {"volumes"},
        }

        for key in required_keys:
            if key not in data:
                raise ValueError(f"Compose file is missing required key: {key}")

        for scope, forbidden_keys in forbidden_keys_by_scope.items():
            if scope == "service":
                for service_name, service_data in data.get("services", {}).items():
                    for forbidden_key in forbidden_keys:
                        if forbidden_key in service_data:
                            service_data.pop(forbidden_key)
            elif scope == "root":
                for forbidden_key in forbidden_keys:
                    if forbidden_key in data:
                        data.pop(forbidden_key)

        compose_networks_names = set()
        if "networks" in data:
            for network_name, network_data in data["networks"].items():
                compose_networks_names.add(network_name)
                data["networks"][network_name] = {
                    "driver": "bridge",
                }

        for service_name, service_data in data.get("services", {}).items():
            if "networks" in service_data:
                allowed_networks_names = set()
                for network_name in service_data["networks"]:
                    if network_name not in compose_networks_names:
                        continue
                    allowed_networks_names.add(network_name)
                service_data["networks"] = list(allowed_networks_names)

        sanitized_compose_file_path = (
            self._user_instance.tmp_dir()
            / f"{self._user_instance.compose_project_name}_sanitized_compose.yaml"
        )
        sanitized_compose_file_path.write_text(yaml.safe_dump(data))
        return sanitized_compose_file_path

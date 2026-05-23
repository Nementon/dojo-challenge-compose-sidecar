import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DojoUserInstance:
    _DOJO_ROOT_DIR = Path(os.getenv("DOJO_ROOT_DIR", "/var/dojos"))

    def __init__(
        self,
        instance_name: str,
        instance_id: str,
        user_id: str,
        dojo_id: str,
        module_id: str,
        challenge_id: str,
    ) -> None:
        self._instance_name = instance_name
        self._instance_id = instance_id
        self._user_id = user_id
        self._dojo_id = dojo_id
        self._module_id = module_id
        self._challenge_id = challenge_id

    @property
    def instance_name(self) -> str:
        return self._instance_name

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def is_valid(self) -> bool:
        if not all(
            [
                self._instance_id,
                self._user_id,
                self._dojo_id,
                self._module_id,
                self._challenge_id,
            ]
        ):
            logger.debug(
                f"Invalid DojoUserInstance with instance_id='{self._instance_id}', user_id='{self._user_id}', dojo_id='{self._dojo_id}', module_id='{self._module_id}', challenge_id='{self._challenge_id}'"
            )
            return False

        if not self._DOJO_ROOT_DIR.is_dir():
            logger.warning(
                f"Dojo root directory '{self._DOJO_ROOT_DIR}' does not exist or is not a directory"
            )
            return False

        if not self.tmp_dir().is_dir():
            logger.warning(
                f"Dojo tmp directory '{self.tmp_dir()}' does not exist or is not a directory"
            )
            return False

        if not self._instance_name == f"user_{self._user_id}":
            logger.warning(
                f"Container name '{self._instance_name}' does not match expected format 'user_{self._user_id}' for user_id '{self._user_id}'"
            )
            return False

        try:
            challenge_path = self.challenge_path
            return challenge_path.is_dir()
        except ValueError as e:
            logger.debug(f"Invalid challenge path for DojoUserInstance: {e}")
            return False

    def root_dir(self) -> Path:
        return self._DOJO_ROOT_DIR

    def tmp_dir(self) -> Path:
        return self._DOJO_ROOT_DIR / "tmp"

    @property
    def challenge_path(self) -> Path:
        challenge_hash = self.challenge_hash
        if not challenge_hash:
            raise ValueError(
                f"Invalid dojo_id format, missing challenge hash: {self._dojo_id}"
            )

        return (
            self._DOJO_ROOT_DIR
            / str(self.challenge_hash)
            / self._module_id
            / self._challenge_id
        )

    @property
    def challenge_hash(self) -> str | None:
        if "~" in self._dojo_id:
            _, hash = self._dojo_id.split("~", 1)
            return hash
        return None

    def has_compose_file(self) -> bool:
        try:
            return self.compose_file_path.is_file()
        except ValueError:
            return False

    @property
    def compose_file_path(self) -> Path:
        return self.challenge_path / "docker-compose.yaml"

    @property
    def compose_project_name(self) -> str:
        return f"{self._instance_name}-compose"

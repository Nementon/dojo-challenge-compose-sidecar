import logging
import docker
import os
import sys
from typing import Any
from docker.errors import APIError, NotFound
from docker.models.containers import Container
from .dojo_compose_manager import DojoComposeManager
from .dojo_user_instance import DojoUserInstance


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


configure_logging()
logger = logging.getLogger(__name__)


def handle_container_start(
    client: docker.DockerClient, container_id: str, event: dict[str, Any]
) -> None:
    container = resolve_container(client, container_id)
    attributes = get_event_attributes(event)

    container_name = attributes.get("name", "unknown")
    image_name = attributes.get("image", "unknown")
    labels = {k: v for k, v in attributes.items() if k not in {"name", "image"}}

    if container is not None:
        container_name = container.name or container_name
        image_name = (
            container.image.tags[0]
            if container.image and container.image.tags
            else image_name
        )
        labels = container.labels or labels

    logger.info(f"""
Container {container_id} ({container_name}) started with 
    - image={image_name} 
    - labels={labels}

""")

    user_instance = DojoUserInstance(
        instance_name=container_name,
        instance_id=container_id,
        user_id=labels.get("dojo.user_id", ""),
        dojo_id=labels.get("dojo.dojo_id", ""),
        module_id=labels.get("dojo.module_id", ""),
        challenge_id=labels.get("dojo.challenge_id", ""),
    )
    if not user_instance.is_valid():
        logger.debug(
            f"Container {container_id} does not correspond to a valid DojoUserInstance, skipping compose up"
        )
        return

    if user_instance.has_compose_file():
        logger.debug(
            f"User instance has compose file, executing docker-compose up for {user_instance.compose_file_path}"
        )
        try:
            DojoComposeManager(user_instance).exec_compose_up()
        except Exception:
            logger.exception(
                f"Error executing docker-compose up for {user_instance.compose_file_path}"
            )
    else:
        logger.debug(
            f"No compose file found for user instance, skipping compose up << {user_instance.compose_file_path} >>"
        )


def handle_container_stop(
    client: docker.DockerClient, container_id: str, event: dict[str, Any]
) -> None:
    container = resolve_container(client, container_id)
    attributes = get_event_attributes(event)

    container_name = attributes.get("name", "unknown")
    image_name = attributes.get("image", "unknown")
    labels = {k: v for k, v in attributes.items() if k not in {"name", "image"}}

    if container is not None:
        container_name = container.name or container_name
        image_name = (
            container.image.tags[0]
            if container.image and container.image.tags
            else image_name
        )
        labels = container.labels or labels

    logger.info(f"""
Container {container_id} ({container_name}) stopped with 
    - image={image_name} 
    - labels={labels}

""")

    user_instance = DojoUserInstance(
        instance_name=container_name,
        instance_id=container_id,
        user_id=labels.get("dojo.user_id", ""),
        dojo_id=labels.get("dojo.dojo_id", ""),
        module_id=labels.get("dojo.module_id", ""),
        challenge_id=labels.get("dojo.challenge_id", ""),
    )
    if not user_instance.is_valid():
        logger.debug(
            f"Container {container_id} does not correspond to a valid DojoUserInstance, skipping compose down"
        )
        return

    if user_instance.has_compose_file():
        logger.debug(
            f"User instance has compose file, executing docker-compose down for {user_instance.compose_file_path}"
        )
        try:
            DojoComposeManager(user_instance).exec_compose_down()
        except Exception:
            logger.exception(
                f"Error executing docker-compose down for {user_instance.compose_file_path}"
            )
    else:
        logger.debug(
            f"No compose file found for user instance, skipping compose down << {user_instance.compose_file_path} >>"
        )


def resolve_container(
    client: docker.DockerClient, container_id: str
) -> Container | None:
    try:
        container = client.containers.get(container_id)
        return container
    except NotFound:
        # Container may already be removed by the time the event is handled.
        logger.debug(f"Container not found during event handling: {container_id}")
        return None
    except APIError as exc:
        logger.warning(
            f"Docker API error while resolving container {container_id}: {exc}"
        )
        return None


def get_event_attributes(event: dict[str, Any]) -> dict[str, str]:
    actor = event.get("Actor") or {}
    if not isinstance(actor, dict):
        return {}

    attributes = actor.get("Attributes") or {}
    if not isinstance(attributes, dict):
        return {}

    return {str(key): str(value) for key, value in attributes.items()}


def get_container_id_from_event(event: dict) -> str | None:
    container_id = event.get("id")
    if container_id:
        return container_id

    actor = event.get("Actor") or {}
    if isinstance(actor, dict):
        actor_id = actor.get("ID")
        if actor_id:
            return actor_id

        attributes = actor.get("Attributes") or {}
        if isinstance(attributes, dict):
            for key in ("container", "container_id", "id"):
                value = attributes.get(key)
                if value:
                    return value

    return None


def main() -> None:
    _handlers = {
        "start": handle_container_start,
        "restart": handle_container_start,
        "create": handle_container_start,
        "stop": handle_container_stop,
        "die": handle_container_stop,
        "kill": handle_container_stop,
    }

    client = docker.from_env()
    for event in client.events(decode=True):
        if event.get("Type") != "container":
            continue

        action = event.get("Action")
        container_id = get_container_id_from_event(event)

        if not container_id:
            logger.error(f"Skipping container event without container id: {event}")
            continue

        if action in _handlers:
            _handlers[action](client, container_id, event)
        else:
            logger.info(
                f"Unhandled container event: {action} for container {container_id}"
            )


if __name__ == "__main__":
    main()

"""Validate configuration before any mutation occurs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from careeros.core.errors import (
    ConfigValidationError,
    ExternalActionPolicyError,
    SecretInConfigError,
    UnsupportedConfigVersionError,
)
from careeros.core.roots import RootLayout


CONFIG_SCHEMA = "careeros.config.v1"
CONFIG_VERSION = "1.0.0"
REQUIRED_SECTIONS = (
    "workspace",
    "candidate",
    "privacy",
    "career",
    "discovery",
    "qualification",
    "resume",
    "applications",
    "adapters",
    "runtime",
)
SECRET_KEY_PATTERN = re.compile(r"(?:password|secret|token|api[_-]?key|private[_-]?key)$", re.I)


@dataclass(frozen=True)
class ValidatedConfig:
    path: Path
    raw: dict[str, Any]
    roots: RootLayout


def _find_inline_secrets(value: object, path: tuple[str, ...] = ()) -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, str(key))
            if SECRET_KEY_PATTERN.search(str(key)) and child not in (None, "", "ENV", "KEYRING"):
                findings.append(".".join(child_path))
            findings.extend(_find_inline_secrets(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_find_inline_secrets(child, (*path, str(index))))
    return findings


def validate_config(data: dict[str, Any], config_path: Path) -> ValidatedConfig:
    if not isinstance(data, dict):
        raise ConfigValidationError("configuration root must be an object")
    if data.get("schema") != CONFIG_SCHEMA:
        raise ConfigValidationError("configuration schema must be careeros.config.v1")
    if data.get("config_version") != CONFIG_VERSION:
        raise UnsupportedConfigVersionError(
            "only CareerOSConfigV1 version 1.0.0 is supported",
            details={"received": data.get("config_version")},
        )
    missing = [section for section in REQUIRED_SECTIONS if not isinstance(data.get(section), dict)]
    if missing:
        raise ConfigValidationError("required configuration sections are missing", details={"sections": missing})

    secrets = _find_inline_secrets(data)
    if secrets:
        raise SecretInConfigError("secrets must be references, not inline values", details={"fields": secrets})

    roots = RootLayout.from_relative_paths(config_path, data["workspace"])
    privacy = data["privacy"]
    applications = data["applications"]
    adapters = data["adapters"]
    if privacy.get("require_human_approval_for_external_actions") is not True:
        raise ExternalActionPolicyError("human approval must be required for consequential external actions")
    if applications.get("approval_policy") != "human_before_external_action":
        raise ExternalActionPolicyError("application approval policy must remain human_before_external_action")
    for name, adapter in adapters.items():
        if not isinstance(adapter, dict):
            raise ConfigValidationError("adapter configuration must be an object", details={"adapter": name})
        if adapter.get("enabled") is True and adapter.get("external_actions") is True:
            if adapter.get("require_human_approval") is not True:
                raise ExternalActionPolicyError(
                    "enabled external-action adapters must require human approval",
                    details={"adapter": name},
                )
    naming = data["resume"].get("output_naming")
    if not isinstance(naming, str) or "{public_name}" not in naming or "{target_role}" not in naming:
        raise ConfigValidationError("resume.output_naming must use public_name and target_role tokens")
    if not isinstance(data["workspace"].get("timezone"), str) or not data["workspace"].get("timezone"):
        raise ConfigValidationError("workspace.timezone is required")
    if not isinstance(data["workspace"].get("locale"), str) or not data["workspace"].get("locale"):
        raise ConfigValidationError("workspace.locale is required")
    return ValidatedConfig(path=config_path.resolve(), raw=data, roots=roots)


def load_config(path: Path) -> ValidatedConfig:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigValidationError(f"unable to load configuration: {exc}") from exc
    return validate_config(data, path)


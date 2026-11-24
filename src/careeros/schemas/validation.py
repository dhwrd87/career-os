"""Small JSON Schema subset used to validate Phase 1 contracts without mutation.

The published schema documents remain Draft 2020-12. This validator intentionally
supports only the keywords used by the Phase 1 bundle so bootstrap checks need no
third-party dependency.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from careeros.core.errors import ContractValidationError


class SchemaRegistry:
    def __init__(self, schema_dir: Path) -> None:
        self.schema_dir = schema_dir
        self.by_id: dict[str, dict[str, Any]] = {}
        self.by_contract: dict[str, str] = {}
        for path in sorted(schema_dir.glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            schema_id = schema.get("$id")
            if not isinstance(schema_id, str) or not schema_id:
                raise ContractValidationError(f"schema lacks $id: {path.name}")
            self.by_id[schema_id] = schema
        metadata_path = schema_dir / "registry.v1.json"
        self.metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {"entries": []}
        for entry in self.metadata.get("entries", []):
            self.by_contract[entry["schema_id"]] = entry["urn"]

    def validate(self, schema_id: str, instance: Any) -> None:
        if schema_id not in self.by_id:
            raise ContractValidationError(f"unknown schema: {schema_id}")
        errors: list[str] = []
        self._validate(self.by_id[schema_id], instance, "$", errors)
        if errors:
            raise ContractValidationError("; ".join(errors[:20]), details={"errors": errors})

    def list_entries(self) -> list[dict[str, Any]]:
        return list(self.metadata.get("entries", []))

    def validate_path(self, path: Path) -> dict[str, Any]:
        try:
            instance = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractValidationError(f"unable to read JSON document: {exc}", cause=exc) from exc
        contract = instance.get("schema") if isinstance(instance, dict) else None
        if not isinstance(contract, str) or contract not in self.by_contract:
            raise ContractValidationError("document has no registered schema identifier", details={"schema": contract})
        urn = self.by_contract[contract]
        self.validate(urn, instance)
        return {"schema": "careeros.schema-validation-result.v1", "status": "VALID", "path": str(path),
                "contract": contract, "schema_id": urn}

    def _resolve_ref(self, ref: str) -> dict[str, Any]:
        if ref not in self.by_id:
            raise ContractValidationError(f"unresolved schema reference: {ref}")
        return self.by_id[ref]

    def _validate(self, schema: dict[str, Any], value: Any, path: str, errors: list[str]) -> None:
        if "$ref" in schema:
            self._validate(self._resolve_ref(schema["$ref"]), value, path, errors)
            return
        if "oneOf" in schema:
            matching = 0
            for alternative in schema["oneOf"]:
                alternative_errors: list[str] = []
                self._validate(alternative, value, path, alternative_errors)
                if not alternative_errors:
                    matching += 1
            if matching != 1:
                errors.append(f"{path}: expected exactly one matching schema, found {matching}")
            return
        if "const" in schema and value != schema["const"]:
            errors.append(f"{path}: expected constant {schema['const']!r}")
            return
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: value is not in the allowed enum")
            return
        expected = schema.get("type")
        if expected:
            allowed = expected if isinstance(expected, list) else [expected]
            matches = any(self._matches_type(kind, value) for kind in allowed)
            if not matches:
                errors.append(f"{path}: expected type {expected}")
                return
        if isinstance(value, dict):
            required = schema.get("required", [])
            for key in required:
                if key not in value:
                    errors.append(f"{path}.{key}: required property missing")
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                for key in value:
                    if key not in properties:
                        errors.append(f"{path}.{key}: additional property forbidden")
            for key, child_schema in properties.items():
                if key in value:
                    self._validate(child_schema, value[key], f"{path}.{key}", errors)
        elif isinstance(value, list):
            if len(value) < int(schema.get("minItems", 0)):
                errors.append(f"{path}: too few items")
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for index, child in enumerate(value):
                    self._validate(item_schema, child, f"{path}[{index}]", errors)
        elif isinstance(value, str):
            if len(value) < int(schema.get("minLength", 0)):
                errors.append(f"{path}: string is too short")
            pattern = schema.get("pattern")
            if pattern and re.search(pattern, value) is None:
                errors.append(f"{path}: string does not match required pattern")
            if schema.get("format") == "date-time":
                try:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    errors.append(f"{path}: invalid date-time")

    @staticmethod
    def _matches_type(kind: str, value: Any) -> bool:
        return {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }.get(kind, False)

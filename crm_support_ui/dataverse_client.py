from __future__ import annotations

import json
import locale
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


DEFAULT_ENVIRONMENT = "https://developersolutions.crm5.dynamics.com"
DEFAULT_TENANT_ID = "7f25deda-221b-44f6-89eb-8551818911f0"
INCIDENT_ENTITY = "gc_techsupportincident"


class DataverseError(RuntimeError):
    pass


def _response_error(response: requests.Response) -> str:
    try:
        body = response.json()
        message = body.get("error", {}).get("message")
        if message:
            return f"HTTP {response.status_code}: {message}"
    except ValueError:
        pass
    text = response.text.strip().replace("\n", " ")
    return f"HTTP {response.status_code}: {text[:800]}"


@dataclass(frozen=True)
class Relationship:
    attribute: str
    navigation_property: str
    referenced_entity: str


class DataverseClient:
    def __init__(self, environment: str, access_token: str) -> None:
        self.environment = environment.rstrip("/")
        self.api_url = f"{self.environment}/api/data/v9.2"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "OData-MaxVersion": "4.0",
                "OData-Version": "4.0",
                "Prefer": (
                    'odata.include-annotations="'
                    'OData.Community.Display.V1.FormattedValue"'
                ),
            }
        )
        self._entity_cache: dict[str, dict[str, Any]] = {}
        self._relationships: dict[str, list[Relationship]] = {}

    def get(
        self,
        path_or_url: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = (
            path_or_url
            if path_or_url.startswith("http")
            else f"{self.api_url}/{path_or_url}"
        )
        response = self.session.get(url, params=params, timeout=60)
        if not response.ok:
            raise DataverseError(_response_error(response))
        return response.json()

    def get_entity(self, logical_name: str) -> dict[str, Any]:
        if logical_name not in self._entity_cache:
            escaped = logical_name.replace("'", "''")
            self._entity_cache[logical_name] = self.get(
                f"EntityDefinitions(LogicalName='{escaped}')",
                {
                    "$select": (
                        "LogicalName,EntitySetName,PrimaryIdAttribute,"
                        "PrimaryNameAttribute"
                    )
                },
            )
        return self._entity_cache[logical_name]

    def get_relationships(self, logical_name: str) -> list[Relationship]:
        if logical_name in self._relationships:
            return self._relationships[logical_name]

        escaped = logical_name.replace("'", "''")
        path: str | None = (
            f"EntityDefinitions(LogicalName='{escaped}')/ManyToOneRelationships"
        )
        params: dict[str, str] | None = {
            "$select": (
                "ReferencingAttribute,ReferencingEntityNavigationPropertyName,"
                "ReferencedEntity"
            )
        }
        rows: list[dict[str, Any]] = []
        while path:
            page = self.get(path, params)
            rows.extend(page.get("value", []))
            path = page.get("@odata.nextLink")
            params = None

        relationships = [
            Relationship(
                attribute=row["ReferencingAttribute"],
                navigation_property=row[
                    "ReferencingEntityNavigationPropertyName"
                ],
                referenced_entity=row["ReferencedEntity"],
            )
            for row in rows
            if row.get("ReferencingAttribute")
            and row.get("ReferencingEntityNavigationPropertyName")
            and row.get("ReferencedEntity")
        ]
        self._relationships[logical_name] = relationships
        return relationships

    def lookup_binding(
        self,
        source_entity: str,
        attribute: str,
        record_id: str,
        referenced_entity: str | None = None,
    ) -> tuple[str, str]:
        candidates = [
            relationship
            for relationship in self.get_relationships(source_entity)
            if relationship.attribute == attribute
            and (
                referenced_entity is None
                or relationship.referenced_entity == referenced_entity
            )
        ]
        if len(candidates) != 1:
            targets = sorted({item.referenced_entity for item in candidates})
            detail = f"; candidates: {', '.join(targets)}" if targets else ""
            raise DataverseError(
                f"Cannot resolve lookup {attribute!r} for referenced entity "
                f"{referenced_entity!r}{detail}."
            )

        relationship = candidates[0]
        entity_set = self.get_entity(relationship.referenced_entity)["EntitySetName"]
        normalized_id = normalize_guid(record_id, attribute)
        return (
            f"{relationship.navigation_property}@odata.bind",
            f"/{entity_set}({normalized_id})",
        )

    def create(self, entity_set: str, payload: dict[str, Any]) -> str:
        response = self.session.post(
            f"{self.api_url}/{entity_set}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=60,
        )
        if response.status_code not in (201, 204):
            raise DataverseError(_response_error(response))
        entity_id = response.headers.get("OData-EntityId", "")
        match = re.search(r"\(([0-9a-fA-F-]{36})\)", entity_id)
        return match.group(1) if match else entity_id or "created"


def normalize_guid(raw: str, field_name: str) -> str:
    try:
        return str(uuid.UUID(raw.strip().strip("{}")))
    except (ValueError, AttributeError) as exc:
        raise DataverseError(f"Invalid GUID in {field_name}: {raw!r}") from exc


def _decode_process_output(value: bytes | None) -> str:
    if not value:
        return ""
    encodings = ["utf-8", locale.getpreferredencoding(False)]
    if os.name == "nt":
        encodings.extend(["mbcs", "cp936"])
    for encoding in dict.fromkeys(encodings):
        try:
            return value.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return value.decode("utf-8", errors="replace")


def _resolve_azure_cli(explicit_path: str | None = None) -> str:
    if explicit_path:
        candidate = Path(explicit_path).expanduser()
        if not candidate.is_file():
            raise DataverseError(f"Azure CLI path does not exist: {candidate}")
        return str(candidate)

    if os.name == "nt":
        executable_names = ("az.cmd", "az.exe", "az.bat")
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            directory = directory.strip().strip('"')
            if not directory:
                continue
            for executable_name in executable_names:
                candidate = Path(directory) / executable_name
                if candidate.is_file():
                    return str(candidate)
    else:
        import shutil

        candidate = shutil.which("az")
        if candidate:
            return candidate

    raise DataverseError(
        "Azure CLI was not found in this process PATH. Run 'where az' in the "
        "same terminal, restart the terminal after installation, or configure "
        "CRM_AZ_PATH with the full az.cmd path."
    )


def acquire_azure_cli_token(
    tenant_id: str,
    environment: str,
    explicit_path: str | None = None,
) -> str:
    azure_cli = _resolve_azure_cli(explicit_path)
    arguments = [
        "account",
        "get-access-token",
        "--tenant",
        tenant_id,
        "--resource",
        environment,
        "--query",
        "accessToken",
        "-o",
        "tsv",
    ]
    use_shell = (
        os.name == "nt"
        and Path(azure_cli).suffix.lower() in {".cmd", ".bat"}
    )
    result = subprocess.run(
        [azure_cli, *arguments],
        check=False,
        capture_output=True,
        shell=use_shell,
    )
    stdout = _decode_process_output(result.stdout)
    stderr = _decode_process_output(result.stderr)
    if result.returncode != 0:
        message = stderr.strip() or stdout.strip()
        raise DataverseError(f"Azure CLI could not obtain a token: {message}")
    token = stdout.strip()
    if not token:
        raise DataverseError("Azure CLI returned an empty access token")
    return token


def parse_actual_end(raw_value: str) -> str:
    value = raw_value.strip()
    for date_format in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            date_value = datetime.strptime(value, date_format).date()
            return f"{date_value.isoformat()}T00:00:00Z"
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataverseError(
            f"Unsupported actualend value {raw_value!r}; use YYYY/M/D or ISO 8601"
        ) from exc
    return parsed.isoformat()

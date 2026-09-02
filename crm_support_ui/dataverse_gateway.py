from __future__ import annotations

import uuid
from typing import Any, Callable
from urllib.parse import urlencode

from .dataverse_client import INCIDENT_ENTITY, DataverseError, parse_actual_end


VALID_SCOPES = {"all", "owned", "related"}
FORMATTED_VALUE = "@OData.Community.Display.V1.FormattedValue"
SOURCE_ENTITIES = {
    "gc_accounttechsupport": "account",
    "gc_opportunitytechsupport": "opportunity",
}
DEFAULT_APP_ID = "4c43e99b-eb5d-e911-a998-000d3a81e7bd"
SOURCE_APP_IDS = {
    "gc_accounttechsupport": "a22d2062-9fa0-ea11-a812-000d3a8543fd",
    "gc_opportunitytechsupport": DEFAULT_APP_ID,
}
OPPORTUNITY_STATE_LABELS = {0: "已开启", 1: "赢单", 2: "丢单"}


def _normalized_lookup_id(row: dict, attribute: str) -> str:
    value = row.get(f"_{attribute}_value")
    if not value:
        return ""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError):
        return ""


def _display_labels(attribute: dict) -> list[str]:
    display_name = attribute.get("DisplayName") or {}
    return [
        str(item.get("Label") or "").strip()
        for item in display_name.get("LocalizedLabels") or []
        if item.get("Label")
    ]


def assignment_fields_from_attributes(attributes: list[dict]) -> list[str]:
    result: list[str] = []
    for attribute in attributes:
        logical_name = str(attribute.get("LogicalName") or "").lower()
        targets = {str(target).lower() for target in attribute.get("Targets") or []}
        labels = _display_labels(attribute)
        is_consultant = (
            any(label.startswith("\u6280\u672f\u987e\u95ee") for label in labels)
            or "technicalconsultant" in logical_name
            or "techconsultant" in logical_name
        )
        if logical_name == "ownerid" or ("systemuser" in targets and is_consultant):
            result.append(logical_name)
    unique = list(dict.fromkeys(result))
    if "ownerid" in unique:
        unique.remove("ownerid")
        unique.insert(0, "ownerid")
    return unique


def build_assignment_filter(
    user_id: str,
    assignment_fields: list[str],
    scope: str,
) -> str:
    if scope not in VALID_SCOPES:
        raise ValueError(f"Unsupported scope: {scope}")
    if scope == "all":
        return "statecode eq 0"
    normalized_user_id = str(uuid.UUID(user_id))
    fields = ["ownerid"] if scope == "owned" else list(dict.fromkeys(assignment_fields))
    if "ownerid" not in fields:
        fields.insert(0, "ownerid")
    comparisons = " or ".join(
        f"_{field}_value eq {normalized_user_id}" for field in fields
    )
    return f"statecode eq 0 and ({comparisons})"


class DataverseGateway:
    """Application-facing operations over the generic Dataverse client."""

    def __init__(
        self,
        client_factory: Callable[[], Any],
        app_id: str = DEFAULT_APP_ID,
    ) -> None:
        self._client_factory = client_factory
        self._app_id = str(uuid.UUID(app_id))

    @staticmethod
    def _lookup_metadata(client: Any, entity: str) -> list[dict]:
        escaped = entity.replace("'", "''")
        path = (
            f"EntityDefinitions(LogicalName='{escaped}')/Attributes/"
            "Microsoft.Dynamics.CRM.LookupAttributeMetadata"
        )
        rows: list[dict] = []
        params: dict[str, str] | None = {
            "$select": "LogicalName,DisplayName,Targets"
        }
        while path:
            page = client.get(path, params)
            rows.extend(page.get("value", []))
            path = page.get("@odata.nextLink")
            params = None
        return rows

    @staticmethod
    def _formatted(row: dict, attribute: str) -> str:
        return str(row.get(f"_{attribute}_value{FORMATTED_VALUE}") or "")

    @staticmethod
    def _navigation_property(
        client: Any,
        entity: str,
        attribute: str,
        referenced_entity: str,
    ) -> str:
        for relationship in client.get_relationships(entity):
            if (
                relationship.attribute == attribute
                and relationship.referenced_entity == referenced_entity
            ):
                return str(relationship.navigation_property)
        return ""

    @staticmethod
    def _record_url(
        environment: str,
        app_id: str,
        entity: str,
        record_id: str,
    ) -> str:
        query = urlencode(
            {
                "appid": app_id,
                "forceUCI": "1",
                "newWindow": "true",
                "pagetype": "entityrecord",
                "etn": entity,
                "id": record_id,
            }
        )
        return f"{environment.rstrip('/')}/main.aspx?{query}"

    @staticmethod
    def _available_entitlement_counts(client: Any) -> dict[str, int]:
        counts: dict[str, int] = {}
        path: str | None = "entitlements"
        params: dict[str, str] | None = {
            "$select": "_customerid_value,_gc_account_value",
            "$filter": "statecode eq 1",
        }
        while path:
            page = client.get(path, params)
            for row in page.get("value", []):
                account_ids = {
                    account_id
                    for account_id in (
                        _normalized_lookup_id(row, "customerid"),
                        _normalized_lookup_id(row, "gc_account"),
                    )
                    if account_id
                }
                for account_id in account_ids:
                    counts[account_id] = counts.get(account_id, 0) + 1
            path = page.get("@odata.nextLink")
            params = None
        return counts

    def list_sources(self, scope: str = "related") -> dict:
        if scope not in VALID_SCOPES:
            raise ValueError(f"Unsupported scope: {scope}")

        client = self._client_factory()
        who_am_i = client.get("WhoAmI")
        user_id = str(uuid.UUID(who_am_i["UserId"]))
        user_row = client.get(
            f"systemusers({user_id})",
            {"$select": "fullname,domainname"},
        )

        items: list[dict] = []
        for entity, source_type in SOURCE_ENTITIES.items():
            metadata = client.get_entity(entity)
            attributes = self._lookup_metadata(client, entity)
            attribute_names = {
                str(attribute.get("LogicalName") or "").lower()
                for attribute in attributes
            }
            selected = [
                metadata["PrimaryIdAttribute"],
                metadata["PrimaryNameAttribute"],
            ]
            selected.extend(
                f"_{name}_value"
                for name in ("gc_account", "gc_opportunity", "ownerid")
                if name in attribute_names
            )
            opportunity_navigation = ""
            if source_type == "opportunity":
                opportunity_navigation = self._navigation_property(
                    client,
                    entity,
                    "gc_opportunity",
                    "opportunity",
                )
            params: dict[str, str] | None = {
                "$select": ",".join(dict.fromkeys(selected)),
                "$filter": build_assignment_filter(
                    user_id,
                    assignment_fields_from_attributes(attributes),
                    scope,
                ),
                "$orderby": metadata["PrimaryNameAttribute"],
            }
            if opportunity_navigation:
                params["$expand"] = (
                    f"{opportunity_navigation}($select=statecode)"
                )
            path: str | None = metadata["EntitySetName"]
            while path:
                page = client.get(path, params)
                for row in page.get("value", []):
                    record_id = str(row[metadata["PrimaryIdAttribute"]])
                    opportunity_state = None
                    opportunity_status = ""
                    if opportunity_navigation:
                        opportunity_row = row.get(opportunity_navigation) or {}
                        raw_state = opportunity_row.get("statecode")
                        if raw_state is not None:
                            opportunity_state = int(raw_state)
                            opportunity_status = str(
                                opportunity_row.get(
                                    f"statecode{FORMATTED_VALUE}"
                                )
                                or OPPORTUNITY_STATE_LABELS.get(
                                    opportunity_state, ""
                                )
                            )
                    items.append(
                        {
                            "id": record_id,
                            "entity": entity,
                            "type": source_type,
                            "name": str(row.get(metadata["PrimaryNameAttribute"]) or ""),
                            "customer": self._formatted(row, "gc_account"),
                            "opportunity": self._formatted(row, "gc_opportunity"),
                            "opportunity_state": opportunity_state,
                            "opportunity_status": opportunity_status,
                            "_account_id": _normalized_lookup_id(row, "gc_account"),
                            "owner": self._formatted(row, "ownerid"),
                            "url": self._record_url(
                                client.environment,
                                SOURCE_APP_IDS[entity],
                                entity,
                                record_id,
                            ),
                        }
                    )
                path = page.get("@odata.nextLink")
                params = None

        if any(item["type"] == "account" for item in items):
            entitlement_counts = self._available_entitlement_counts(client)
        else:
            entitlement_counts = {}
        for item in items:
            account_id = item.pop("_account_id")
            item["available_entitlement_count"] = (
                entitlement_counts.get(account_id, 0)
                if item["type"] == "account"
                else None
            )

        items.sort(key=lambda item: (item["name"].casefold(), item["id"]))
        return {
            "user": {
                "id": user_id,
                "name": str(user_row.get("fullname") or ""),
                "login": str(user_row.get("domainname") or ""),
            },
            "items": items,
        }

    def create_incident(
        self,
        *,
        source_entity: str,
        source_id: str,
        subject: str,
        description: str,
        actual_end: str,
    ) -> dict:
        client = self._client_factory()
        return self._create_incident_with_client(
            client,
            source_entity=source_entity,
            source_id=source_id,
            subject=subject,
            description=description,
            actual_end=actual_end,
        )

    def list_incidents(self, limit: int = 500) -> dict:
        if not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("Incident history limit must be between 1 and 500")

        client = self._client_factory()
        who_am_i = client.get("WhoAmI")
        user_id = str(uuid.UUID(who_am_i["UserId"]))
        user_row = client.get(
            f"systemusers({user_id})",
            {"$select": "fullname,domainname"},
        )
        metadata = client.get_entity(INCIDENT_ENTITY)
        selected = [
            metadata["PrimaryIdAttribute"],
            "subject",
            "description",
            "actualend",
            "createdon",
            "modifiedon",
            "_createdby_value",
            "_gc_account_value",
            "_gc_accounttechsupport_value",
            "_gc_opportunity_value",
            "_gc_opportunitytechsupport_value",
            "_regardingobjectid_value",
        ]
        params: dict[str, str] | None = {
            "$select": ",".join(dict.fromkeys(selected)),
            "$filter": f"_createdby_value eq {user_id}",
            "$orderby": "createdon desc",
            "$top": str(limit),
        }
        path: str | None = metadata["EntitySetName"]
        items: list[dict] = []
        while path and len(items) < limit:
            page = client.get(path, params)
            for row in page.get("value", []):
                if len(items) >= limit:
                    break
                incident_id = str(row[metadata["PrimaryIdAttribute"]])
                account_support_id = _normalized_lookup_id(
                    row, "gc_accounttechsupport"
                )
                opportunity_support_id = _normalized_lookup_id(
                    row, "gc_opportunitytechsupport"
                )
                if opportunity_support_id:
                    source_type = "opportunity"
                    source_entity = "gc_opportunitytechsupport"
                    source_id = opportunity_support_id
                    source_name = self._formatted(
                        row, "gc_opportunitytechsupport"
                    )
                elif account_support_id:
                    source_type = "account"
                    source_entity = "gc_accounttechsupport"
                    source_id = account_support_id
                    source_name = self._formatted(row, "gc_accounttechsupport")
                else:
                    source_type = ""
                    source_entity = ""
                    source_id = ""
                    source_name = self._formatted(row, "regardingobjectid")

                items.append(
                    {
                        "id": incident_id,
                        "subject": str(row.get("subject") or ""),
                        "description": str(row.get("description") or ""),
                        "actual_end": str(
                            row.get(f"actualend{FORMATTED_VALUE}")
                            or row.get("actualend")
                            or ""
                        ),
                        "created_on": str(
                            row.get(f"createdon{FORMATTED_VALUE}")
                            or row.get("createdon")
                            or ""
                        ),
                        "modified_on": str(
                            row.get(f"modifiedon{FORMATTED_VALUE}")
                            or row.get("modifiedon")
                            or ""
                        ),
                        "source_type": source_type,
                        "source_entity": source_entity,
                        "source_id": source_id,
                        "source_name": source_name,
                        "customer": self._formatted(row, "gc_account"),
                        "opportunity": self._formatted(row, "gc_opportunity"),
                        "owner": self._formatted(row, "createdby")
                        or self._formatted(row, "ownerid"),
                        "url": self._record_url(
                            client.environment,
                            self._app_id,
                            INCIDENT_ENTITY,
                            incident_id,
                        ),
                        "source_url": (
                            self._record_url(
                                client.environment,
                                SOURCE_APP_IDS[source_entity],
                                source_entity,
                                source_id,
                            )
                            if source_entity and source_id
                            else ""
                        ),
                    }
                )
            path = page.get("@odata.nextLink")
            params = None

        return {
            "user": {
                "id": user_id,
                "name": str(user_row.get("fullname") or ""),
                "login": str(user_row.get("domainname") or ""),
            },
            "items": items,
            "count": len(items),
        }

    def _create_incident_with_client(
        self,
        client: Any,
        *,
        source_entity: str,
        source_id: str,
        subject: str,
        description: str,
        actual_end: str,
    ) -> dict:
        if source_entity not in SOURCE_ENTITIES:
            raise DataverseError(f"Unsupported source entity: {source_entity!r}")
        try:
            normalized_source_id = str(uuid.UUID(source_id))
        except (ValueError, AttributeError) as exc:
            raise DataverseError(f"Invalid source record id: {source_id!r}") from exc

        normalized_subject = subject.strip()
        if not normalized_subject:
            raise DataverseError("subject is required")
        if not actual_end.strip():
            raise DataverseError("actual_end is required")

        payload: dict[str, object] = {
            "subject": normalized_subject,
            "actualend": parse_actual_end(actual_end),
        }
        if description.strip():
            payload["description"] = description.strip()

        source_key, source_value = client.lookup_binding(
            INCIDENT_ENTITY,
            source_entity,
            normalized_source_id,
            source_entity,
        )
        regarding_key, regarding_value = client.lookup_binding(
            INCIDENT_ENTITY,
            "regardingobjectid",
            normalized_source_id,
            source_entity,
        )
        payload[source_key] = source_value
        payload[regarding_key] = regarding_value

        incident_set = client.get_entity(INCIDENT_ENTITY)["EntitySetName"]
        record_id = client.create(incident_set, payload)
        environment = str(client.environment).rstrip("/")
        query = urlencode(
            {
                "appid": self._app_id,
                "pagetype": "entityrecord",
                "etn": INCIDENT_ENTITY,
                "id": record_id,
            }
        )
        return {"id": record_id, "url": f"{environment}/main.aspx?{query}"}

    def run_batch(
        self,
        items: list[dict],
        on_start: Callable[[dict], None],
        on_success: Callable[[dict, dict], None],
        on_failure: Callable[[dict, Exception], None],
    ) -> None:
        try:
            client = self._client_factory()
        except Exception as exc:
            for item in items:
                on_start(item)
                on_failure(item, exc)
            return
        for item in items:
            on_start(item)
            try:
                result = self._create_incident_with_client(
                    client,
                    source_entity=item["source_entity"],
                    source_id=item["source_id"],
                    subject=item["subject"],
                    description=item.get("description") or "",
                    actual_end=item["actual_end"],
                )
            except Exception as exc:
                on_failure(item, exc)
            else:
                on_success(item, result)

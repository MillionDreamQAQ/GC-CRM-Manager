from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .dataverse_client import (
    DEFAULT_ENVIRONMENT,
    DEFAULT_TENANT_ID,
    DataverseClient,
    DataverseError,
    acquire_azure_cli_token,
)

from .dataverse_gateway import DataverseGateway
from .batch_jobs import BatchJobManager, BatchJobStore, parse_excel_tsv


STATIC_DIR = Path(__file__).resolve().parent / "static"


class IncidentInput(BaseModel):
    source_entity: str
    source_id: str
    subject: str
    description: str = ""
    actual_end: str


class BatchItemInput(IncidentInput):
    client_key: str
    source_name: str = ""


class BatchInput(BaseModel):
    items: list[BatchItemInput]


class PasteInput(BaseModel):
    text: str


def build_default_gateway() -> DataverseGateway:
    environment = os.environ.get("CRM_ENVIRONMENT", DEFAULT_ENVIRONMENT).rstrip("/")
    tenant_id = os.environ.get("CRM_TENANT_ID", DEFAULT_TENANT_ID)
    az_path = os.environ.get("CRM_AZ_PATH") or None

    def client_factory() -> DataverseClient:
        token = acquire_azure_cli_token(tenant_id, environment, az_path)
        return DataverseClient(environment, token)

    return DataverseGateway(client_factory)


def _api_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


def create_app(
    gateway: DataverseGateway | None = None,
    batch_manager: BatchJobManager | None = None,
) -> FastAPI:
    production_gateway = gateway is None
    service = gateway or build_default_gateway()
    manager = batch_manager
    if manager is None and production_gateway:
        database_path = Path(
            os.environ.get(
                "CRM_BATCH_DATABASE",
                Path(__file__).resolve().parent / "data" / "batch_jobs.db",
            )
        )
        manager = BatchJobManager(BatchJobStore(database_path), service)

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        try:
            yield
        finally:
            if manager is not None:
                manager.close()

    application = FastAPI(
        title="CRM \u6280\u672f\u652f\u6301\u5f55\u5165",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @application.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @application.get("/api/sources")
    def list_sources(scope: str = Query("related", pattern="^(related|owned|all)$")) -> dict:
        try:
            return service.list_sources(scope)
        except (DataverseError, requests.RequestException, OSError, ValueError) as exc:
            raise _api_error(exc) from exc

    @application.post("/api/incidents", status_code=201)
    def create_incident(values: IncidentInput) -> dict:
        try:
            return service.create_incident(**values.model_dump())
        except (DataverseError, requests.RequestException, OSError, ValueError) as exc:
            raise _api_error(exc) from exc

    @application.get("/api/incidents")
    def list_incidents(limit: int = Query(500, ge=1, le=500)) -> dict:
        try:
            return service.list_incidents(limit)
        except (DataverseError, requests.RequestException, OSError, ValueError) as exc:
            raise _api_error(exc) from exc

    @application.post("/api/parse-paste")
    def parse_paste(values: PasteInput) -> dict:
        if len(values.text) > 2_000_000:
            raise HTTPException(status_code=413, detail="Pasted content is too large")
        rows = parse_excel_tsv(values.text)
        return {
            "rows": rows,
            "row_count": len(rows),
            "column_count": max((len(row) for row in rows), default=0),
        }

    @application.post("/api/batches", status_code=202)
    def create_batch(values: BatchInput) -> dict:
        if manager is None:
            raise HTTPException(status_code=503, detail="Batch processing is unavailable")
        if not 1 <= len(values.items) <= 200:
            raise HTTPException(status_code=400, detail="A batch must contain 1 to 200 items")
        try:
            return manager.create_job([item.model_dump() for item in values.items])
        except (DataverseError, OSError, ValueError) as exc:
            raise _api_error(exc) from exc

    @application.get("/api/batches/{job_id}")
    def get_batch(job_id: str) -> dict:
        if manager is None:
            raise HTTPException(status_code=503, detail="Batch processing is unavailable")
        try:
            return manager.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Batch job was not found") from exc

    @application.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return application


app = create_app()

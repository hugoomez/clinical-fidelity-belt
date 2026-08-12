from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from secrets import token_hex
from typing import Any

import httpx

from idonia_recog.domain import MagicLink, Patient, ReportRef, ReportType, StudyRef

log = logging.getLogger(__name__)

# Upload destinations and Magic Link participant id. These were assigned by
# Idonia support for the hackathon and mean nothing outside that deployment, so
# they are overridable from the environment. The defaults are the values the
# published results were produced with.
DEFAULT_DICOM_DESTINATION = os.environ.get("IDONIA_DICOM_DESTINATION", "dicom_hak_num14")
DEFAULT_REPORT_DESTINATION = os.environ.get("IDONIA_REPORT_DESTINATION", "report_hak_num14")
DEFAULT_MAGIC_LINK_ID = os.environ.get("IDONIA_MAGIC_LINK_ID", "hacknum14")


class IdoniaStubClient:
    _DICOM_UID_ROOT = "1.2.826.0.1.3680043.10.1338"

    def __init__(self, base_url: str = "https://demo.idonia.com/stub", latency_ms: int = 0):
        self.base_url = base_url.rstrip("/")
        self.latency_ms = latency_ms
        self.call_log: list[dict[str, Any]] = []

    async def _lat(self):
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000)

    def _log(self, method: str, **kw):
        self.call_log.append({"method": method, "timestamp": datetime.now(timezone.utc), **kw})
        log.info("IdoniaStub.%s %s", method, kw)

    async def upload_study(
        self, patient: Patient, dicom_bytes: bytes, modality: str = "MR"
    ) -> StudyRef:
        await self._lat()
        study = StudyRef(
            study_id=f"idonia-study-{uuid.uuid4().hex[:12]}",
            study_instance_uid=f"{self._DICOM_UID_ROOT}.{uuid.uuid4().int % 10**12}",
            patient_dni=patient.dni,
            modality=modality,
            n_instances=max(1, len(dicom_bytes) // 524288),
            folder_id=f"folder-{patient.dni}",
        )
        self._log(
            "upload_study",
            dni=patient.dni,
            modality=modality,
            payload_bytes=len(dicom_bytes),
            study_id=study.study_id,
        )
        return study

    async def upload_report(
        self,
        study: StudyRef,
        pdf_bytes: bytes,
        report_type: ReportType,
        filename: str | None = None,
    ) -> ReportRef:
        await self._lat()
        fname = filename or f"informe_{report_type.value.lower()}.pdf"
        report = ReportRef(
            report_id=f"idonia-report-{uuid.uuid4().hex[:12]}",
            study_id=study.study_id,
            report_type=report_type,
            filename=fname,
            size_bytes=len(pdf_bytes),
        )
        self._log(
            "upload_report",
            study_id=study.study_id,
            type=report_type.value,
            report_id=report.report_id,
        )
        return report

    async def generate_magic_link(
        self, study: StudyRef, reports: list[ReportRef], ttl_hours: int = 168
    ) -> MagicLink:
        await self._lat()
        token = uuid.uuid4().hex[:14]
        pin = token_hex(3).upper()
        link = MagicLink(
            url=f"{self.base_url}/v/{token}",
            pin=pin,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
            study_id=study.study_id,
            report_ids=[r.report_id for r in reports],
        )
        self._log(
            "generate_magic_link", study_id=study.study_id, n_reports=len(reports), token=token
        )
        return link


class IdoniaLiveClient:
    """HTTP client against Idonia Connect Cloud (staging).

    AUTHENTICATION: self-signed bearer JWT. The client builds a JWT carrying the
    api_key and signs it with the api_secret (HS256); there is no login
    endpoint. The exact expected shape of the api_key claim was never confirmed
    by Idonia support, which is why `_signing_key` and `_generate_jwt` are kept
    isolated: adapting to a different scheme means changing one function.

    ENDPOINTS (destinations assigned by Idonia support):
      - DICOM   : POST /files/{dicom_destination}
      - Reports : POST /files/{report_destination}
      - Magic   : PUT  /ml

    STATUS: implemented from the staging Swagger and exercised against it, but
    never validated end to end — that depended on activation by Idonia support.
    See docs/results.md.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        dicom_destination: str = DEFAULT_DICOM_DESTINATION,
        report_destination: str = DEFAULT_REPORT_DESTINATION,
        magic_link_id: str = DEFAULT_MAGIC_LINK_ID,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.dicom_destination = dicom_destination
        self.report_destination = report_destination
        self.magic_link_id = magic_link_id
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)
        self._token: str | None = None
        self._token_exp: float = 0.0

    async def aclose(self):
        await self._client.aclose()

    # --- Autenticacion JWT ---

    def _signing_key(self) -> bytes:
        """Derive the HS256 signing key from the API secret.

        Per Idonia support: drop the 'S2' prefix, then base64url-decode the rest.
        """
        secret_without_prefix = self.api_secret[2:]
        padding = "=" * (-len(secret_without_prefix) % 4)
        return base64.urlsafe_b64decode(secret_without_prefix + padding)

    def _generate_jwt(self) -> str:
        # PyJWT ships in the optional `live` extra, so it is imported lazily:
        # hoisting this to module scope would make the whole `clients` package
        # unimportable for anyone who installed only the base dependencies.
        import jwt

        now = int(time.time())
        payload = {
            "sub": self.api_key,  # claim confirmed by Idonia support
            "iat": now - 300,
            "exp": now + 300,
        }
        return jwt.encode(payload, self._signing_key(), algorithm="HS256")

    def _auth_headers(self) -> dict:
        # Token valido 600s (iat-300 a exp+300). Renovar con 60s de margen.
        if not self._token or time.time() >= self._token_exp - 60:
            self._token = self._generate_jwt()
            self._token_exp = time.time() + 540  # 600s - 60s margen
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    @staticmethod
    def _normalize_file_response(raw: Any, operation: str) -> dict[str, Any]:
        """Coerce a /files upload response into a dict with a `file_uuid` key.

        Idonia's upload endpoints were observed returning three different shapes
        for the same operation — a bare uuid string, a single-element list (of
        either strings or objects), and a full object. Rather than guess, the
        client accepts all three and logs which one it got, so that an unexpected
        shape is visible in the trace instead of surfacing as a KeyError later.
        """
        log.info("%s raw: type=%s value=%r", operation, type(raw).__name__, raw)
        if isinstance(raw, list):
            item = raw[0]
            data = {"file_uuid": item} if isinstance(item, str) else item
            log.info(
                "%s list[0]: type=%s → file_uuid=%s",
                operation,
                type(item).__name__,
                data.get("file_uuid"),
            )
        elif isinstance(raw, str):
            data = {"file_uuid": raw}
            log.info("%s str → file_uuid=%s", operation, raw)
        else:
            data = raw
            log.info(
                "%s dict: file_uuid=%s", operation, data.get("file_uuid") or data.get("id_file")
            )
        return data

    # --- Operaciones ---

    async def upload_study(
        self, patient: Patient, dicom_bytes: bytes, modality: str = "MR"
    ) -> StudyRef:
        resp = await self._client.post(
            f"/files/{self.dicom_destination}",
            headers=self._auth_headers(),
            files={"file": (f"{patient.dni}.zip", dicom_bytes, "application/zip")},
        )
        resp.raise_for_status()
        data = self._normalize_file_response(resp.json(), "upload_study")
        return StudyRef(
            study_id=str(data.get("file_uuid") or data.get("id_file")),
            study_instance_uid=str(data.get("file_uuid", "")),
            patient_dni=patient.dni,
            modality=modality,
            n_instances=int(data.get("n_instances", 0)),
            folder_id=str(data.get("parent_id", f"PATIENT/{patient.dni}")),
        )

    async def upload_report(
        self,
        study: StudyRef,
        pdf_bytes: bytes,
        report_type: ReportType,
        filename: str | None = None,
    ) -> ReportRef:
        fname = filename or f"informe_{report_type.value.lower()}.pdf"
        resp = await self._client.post(
            f"/files/{self.report_destination}",
            headers=self._auth_headers(),
            files={"file": (fname, pdf_bytes, "application/pdf")},
            # The form field name for the report type was never confirmed by
            # Idonia support. Idonia ignores unknown fields, so an incorrect name
            # costs the type tag on their side but does not break the upload.
            data={"report_type": report_type.value},
        )
        resp.raise_for_status()
        data = self._normalize_file_response(resp.json(), "upload_report")
        return ReportRef(
            report_id=str(data.get("file_uuid") or data.get("id_file")),
            study_id=study.study_id,
            report_type=report_type,
            filename=fname,
            size_bytes=len(pdf_bytes),
        )

    async def generate_magic_link(
        self, study: StudyRef, reports: list[ReportRef], ttl_hours: int = 168
    ) -> MagicLink:
        route = f"PATIENT/{study.patient_dni}/{study.study_id}"
        params = {"route": route, "validity_period": f"{ttl_hours}h"}
        resp = await self._client.put("/ml", params=params, headers=self._auth_headers())
        resp.raise_for_status()
        data = resp.json()[0]
        # Known limitation: the API host and the patient-facing viewer host are
        # different deployments and Idonia exposes no mapping between them, so
        # the viewer URL is derived by string substitution. Correct for the
        # staging host this was built against; revisit for any other host.
        base = self.base_url.replace("connect-staging.", "demo.")
        return MagicLink(
            url=f"{base}/v/{data['URL']}",
            pin=str(data["PIN"]),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
            study_id=study.study_id,
            report_ids=[r.report_id for r in reports],
        )

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from idonia_recog.domain import HumanizationOptions, HumanizationResult

log = logging.getLogger(__name__)

RECOG_ENDPOINT = "/relisten/dictation/process/report-results"


class RecogStubClient:
    """Offline stub: serves a report from disk as if Recog had produced it.

    Returns the markdown text as `text` and its UTF-8 bytes as `pdf_bytes` — a
    placeholder rather than a real PDF, but enough for the belt and the
    orchestrator to run end to end without network access. Pointing
    `response_path` at a different report is how the demo exercises both the
    approved and the rejected path.

    `options` is accepted and ignored; see `RecogClient`.
    """

    # Repo-relative default: src/idonia_recog/clients/recog.py -> <repo>/data/reports/
    DEFAULT_GOLD = (
        Path(__file__).resolve().parents[3] / "data" / "reports" / "knee_mri_humanized_gold.es.md"
    )

    def __init__(
        self,
        response_path=None,
        latency_ms: int = 0,
        model_version: str = "recog-stub-v0",
        confidence: float = 0.82,
    ):
        path = Path(response_path) if response_path else None
        if path is None:
            path = self.DEFAULT_GOLD
        if not path.exists():
            raise FileNotFoundError(f"RecogStub: no se encuentra {path}")
        self.response_path = path
        self.latency_ms = latency_ms
        self.model_version = model_version
        self.confidence = confidence
        self.call_log: list[dict] = []

    async def humanize_report(
        self, original_text: str, options: HumanizationOptions | None = None
    ) -> HumanizationResult:
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000)
        text = self.response_path.read_text(encoding="utf-8")
        self.call_log.append(
            {
                "method": "humanize_report",
                "input_chars": len(original_text),
                "output_chars": len(text),
            }
        )
        log.info("RecogStub sirvio %d chars de %s", len(text), self.response_path.name)
        return HumanizationResult(
            text=text,
            pdf_bytes=text.encode("utf-8"),  # placeholder — en live sera un PDF real
            model_version=self.model_version,
            confidence=self.confidence,
        )


class RecogLiveClient:
    """HTTP client against the Recog API.

    AUTHENTICATION: a plain API key in the X-API-Key header, no OAuth and no
    token exchange. Key format: rrk_publicId_part2_part3 (four underscore-
    separated parts).

    ENDPOINT:
        POST https://api.recog.es/relisten/dictation/process/report-results
        Body: {"dictationReport": "<report text>"}
        Response: binary PDF

    TEXT EXTRACTION: the response is a PDF, not text. The belt needs text, so it
    is extracted with PyMuPDF (fitz), which ships in the optional `live` extra.

    `options` is accepted and ignored; see `RecogClient`.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.recog.es", timeout: float = 60.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            },
        )

    async def aclose(self):
        await self._client.aclose()

    def _extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extrae texto del PDF devuelto por Recog para pasarlo al cinturon."""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            return "\n".join(page.get_text() for page in doc).strip()
        except ImportError:
            log.warning(
                "PyMuPDF no instalado — el cinturon recibira texto vacio. "
                "Instala con: pip install pymupdf"
            )
            return ""

    async def humanize_report(
        self, original_text: str, options: HumanizationOptions | None = None
    ) -> HumanizationResult:
        resp = await self._client.post(
            RECOG_ENDPOINT,
            json={"dictationReport": original_text},
        )
        resp.raise_for_status()

        pdf_bytes = resp.content
        text = self._extract_text_from_pdf(pdf_bytes)

        log.info("Recog devolvio %d bytes de PDF, %d chars extraidos", len(pdf_bytes), len(text))

        return HumanizationResult(
            text=text,
            pdf_bytes=pdf_bytes,
            model_version=resp.headers.get("X-Model-Version"),
            confidence=None,
        )

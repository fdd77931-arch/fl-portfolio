"""Health AI HTTP service. Health questions are never logged or persisted."""
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import time
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .knowledge import Catalog, Collection, Domain, Source
from .models import Bailian, ModelUnavailable, Settings
from .safety import emergency_signals

logger = logging.getLogger("health_ai")
ROOT = Path(__file__).resolve().parents[2]
INSUFFICIENT = "当前知识库暂未检索到足够可靠的依据，不能将模型的一般性回答作为医学结论。"
EMERGENCY = "如果这些情况正在发生，请立即联系当地急救。中国大陆拨打 120，其他地区拨打当地急救号码。"
UNAVAILABLE = "实时问答暂时不可用。你可以浏览医学知识库或稍后重试。"
LINK_OR_CITATION = re.compile(r"https?\s*[:：]|www\.|\bPMID\s*[:：]?\s*\d|\b10\.\d{4,9}/|\[\s*\d+\s*\]|［\s*\d+\s*］|【\s*\d+\s*】", re.I)
PERSONAL_IDENTIFIERS = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}|(?<!\d)1[3-9]\d{9}(?!\d)|(?<!\w)\d{17}[\dXx](?!\w)", re.I)
PERSONAL_TREATMENT = re.compile(
    r"(?:我|家人|妈妈|爸爸|孩子|本人).{0,120}(?:该吃多少|能停药吗|可以停药吗|吃几粒|吃几片|吃几毫克|要不要加量|要不要减量|是不是得了|确诊了吗)|"
    r"(?:帮我|给我).{0,15}(?:确诊|开处方|调整剂量)|(?:具体|个人).{0,6}(?:用药剂量|服药剂量)"
)


class Question(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(min_length=2, max_length=1200)


class Paragraph(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    section: Literal["问题回答", "医学依据", "注意事项"]
    text: str = Field(min_length=3, max_length=1400)
    citations: list[str] = Field(min_length=1, max_length=8)


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    supported: bool
    paragraphs: list[Paragraph] = Field(max_length=8)


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: list[Source] = Field(min_length=1, max_length=24)
    artifact_base64: str | None = Field(default=None, max_length=1_400_000)
    media_type: Literal["application/pdf", "text/plain", "application/xml", "text/html"] = "text/plain"

    @field_validator("sources")
    @classmethod
    def unique_ids(cls, sources):
        if len({source.id for source in sources}) != len(sources):
            raise ValueError("Duplicate source ids")
        return sources


class RateLimit:
    def __init__(self):
        self.window = -1
        self.hits = Counter()
        self.paid = 0
        self.lock = Lock()

    def allow(self, client, paid):
        with self.lock:
            window = int(time.monotonic() // 60)
            if self.window != window:
                self.window = window
                self.hits.clear()
                self.paid = 0
            self.hits[client] += 1
            if self.hits[client] > 90 or (paid and (self.hits[(client, "paid")] >= 12 or self.paid >= 50)):
                return False
            if paid:
                self.hits[(client, "paid")] += 1
                self.paid += 1
            return True


class ApiGuard:
    def __init__(self, app, limiter, admin_token):
        self.app = app
        self.limiter = limiter
        self.admin_token = admin_token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        path, method = scope["path"], scope["method"]
        paid = path in {"/api/chat", "/api/retrieve"} and method == "POST"
        host = request.client.host if request.client else "unknown"
        start = time.monotonic()

        async def send_response(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                logger.info("%s %s %s %.0fms", method, path if path in API_PATHS else "other",
                            message["status"], (time.monotonic() - start) * 1000)
            await send(message)

        if method != "OPTIONS" and not self.limiter.allow(host, paid):
            if path == "/api/chat" and method == "POST":
                request.state.rate_limited = True
            else:
                response = JSONResponse({"detail": "请求过于频繁，请稍后重试。"}, status_code=429,
                                        headers={"Retry-After": "60"})
                return await response(scope, receive, send_response)
        if path == "/api/ingest" and method == "POST":
            authorization = request.headers.get("authorization", "")
            if not self.admin_token or not secrets.compare_digest(authorization.encode(), ("Bearer " + self.admin_token).encode()):
                response = JSONResponse({"detail": "需要导入服务的管理员令牌。"}, status_code=401)
                return await response(scope, receive, send_response)
        if method != "POST":
            return await self.app(scope, receive, send_response)

        max_bytes = 1_600_000 if path == "/api/ingest" else 12_000
        body = bytearray()
        while True:
            part = await receive()
            if part["type"] == "http.disconnect":
                return
            chunk = part.get("body", b"")
            if len(body) + len(chunk) > max_bytes:
                response = JSONResponse({"detail": "请求体过大。"}, status_code=413)
                return await response(scope, receive, send_response)
            body.extend(chunk)
            if not part.get("more_body"):
                break
        replayed = False

        async def replay():
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        return await self.app(scope, replay, send_response)


def grounded_answer(raw, evidence):
    try:
        draft = Draft.model_validate_json(raw)
    except ValidationError:
        return None
    if not draft.supported or not draft.paragraphs or draft.paragraphs[0].section != "问题回答":
        return None
    by_id = {source.id: source for source in evidence}
    documents = {}
    paragraphs = []
    for number, paragraph in enumerate(draft.paragraphs, 1):
        if LINK_OR_CITATION.search(paragraph.text) or any(key not in by_id for key in paragraph.citations):
            return None
        citations = []
        for key in dict.fromkeys(paragraph.citations):
            source = by_id[key]
            if source.document_id not in citations:
                citations.append(source.document_id)
            document = documents.setdefault(source.document_id, {
                **source.model_dump(mode="json", exclude={"terms", "text"}), "passages": {}
            })
            passage = document["passages"].setdefault(source.id, {
                "id": source.id, "section": source.section, "page_number": source.page_number, "source_url": str(source.url),
                "text": source.text, "excerpt_kind": source.excerpt_kind, "paragraphs": []
            })
            passage["paragraphs"].append(number)
        paragraphs.append({"section": paragraph.section, "text": paragraph.text, "citations": citations})
    for document in documents.values():
        document["passages"] = list(document["passages"].values())
    return {"kind": "answer", "paragraphs": paragraphs, "sources": list(documents.values())}



def verify_answer(model_client, question, answer):
    cited_passages = {
        source["document_id"]: source["passages"] for source in answer["sources"]
    }
    paragraphs = [
        {"text": paragraph["text"], "evidence": [
            passage["text"] for document_id in paragraph["citations"]
            for passage in cited_passages[document_id] if number in passage["paragraphs"]
        ]}
        for number, paragraph in enumerate(answer["paragraphs"], 1)
    ]
    return model_client.verify_support(question, paragraphs)

def create_app(models=None, db_path=None):
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    model_client = models or Bailian(Settings.from_env())
    catalog = Catalog(db_path or os.getenv("HEALTH_AI_DB", str(ROOT / "backend" / "var" / "knowledge.db")))
    min_score = float(os.getenv("HEALTH_AI_MIN_RERANK_SCORE", "0.55"))
    if not 0 < min_score <= 1:
        raise ValueError("HEALTH_AI_MIN_RERANK_SCORE must be in (0, 1]")
    admin_token = os.getenv("HEALTH_AI_INGEST_TOKEN", "")
    allowed_origins = [origin.strip() for origin in os.getenv(
        "HEALTH_AI_CORS", "https://fdd77931-arch.github.io").split(",") if origin.strip() and origin.strip() != "*"]
    limiter = RateLimit()

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            if models is None:
                model_client.client.close()

    app = FastAPI(title="Health AI", lifespan=lifespan)
    app.state.catalog = catalog
    app.state.last_success = None
    app.add_middleware(ApiGuard, limiter=limiter, admin_token=admin_token)
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"])

    @app.exception_handler(RequestValidationError)
    async def invalid(_request, _error):
        return JSONResponse({"detail": "请求字段或格式无效。"}, status_code=422)

    @app.exception_handler(ModelUnavailable)
    async def model_error(_request, error):
        app.state.last_success = None
        logger.warning("model pipeline unavailable: %s", error)
        return JSONResponse({"kind": "unavailable", "message": UNAVAILABLE}, status_code=503)

    @app.get("/api/health")
    def health():
        active, vectors = catalog.state(model_client)
        index_ready = bool(active) and len(active) == len(vectors)
        ready = model_client.configured and index_ready
        last = app.state.last_success
        connected = bool(ready and last is not None and time.monotonic() - last < 900)
        return {"status": "ok", "configured": model_client.configured, "index_ready": index_ready,
                "can_query": ready, "connected": connected}

    @app.get("/api/sources")
    def sources(collection: Collection | None = None, domain: Domain | None = None,
                q: str = Query("", max_length=100), limit: int = Query(24, ge=1, le=60),
                offset: int = Query(0, ge=0)):
        items = [
            source for source in catalog.sources()
            if source.status != "unverified"
            and (collection is None or collection == source.collection)
            and (domain is None or domain == source.domain)
            and (not q or q.casefold().strip() in source.passage().casefold())
        ]
        return {"total": len(items), "sources": items[offset:offset + limit]}

    @app.get("/api/knowledge/stats")
    def stats():
        all_sources = catalog.sources()
        active, vectors = catalog.state(model_client)
        return {
            "documents": len({source.document_id for source in all_sources}),
            "chunks": len(all_sources), "verified_chunks": len(active), "indexed_chunks": len(vectors),
            "collections": dict(Counter(source.collection for source in all_sources)),
            "domains": dict(Counter(source.domain for source in all_sources)),
            "version_status": dict(Counter(source.status for source in all_sources))
        }

    def retrieve_evidence(question):
        if PERSONAL_IDENTIFIERS.search(question):
            raise HTTPException(422, "请删除联系方式或证件号码后重试。")
        if not model_client.configured:
            raise ModelUnavailable("not_configured")
        return catalog.retrieve(question, model_client, min_score)

    @app.post("/api/retrieve")
    def retrieve(payload: Question, trace: bool = False):
        if emergency_signals(payload.question):
            return {"kind": "emergency", "message": EMERGENCY, "sources": []}
        evidence, ranks = retrieve_evidence(payload.question)
        result = {"kind": "evidence" if evidence else "insufficient", "sources": evidence, "domains": ranks["domains"]}
        if trace:
            result["ranking"] = ranks
        return result

    @app.post("/api/chat")
    def chat(payload: Question, request: Request):
        signals = emergency_signals(payload.question)
        if signals:
            return {"kind": "emergency", "message": EMERGENCY, "signals": signals}
        if getattr(request.state, "rate_limited", False):
            raise HTTPException(429, "请求过于频繁，请稍后重试。", headers={"Retry-After": "60"})
        if PERSONAL_TREATMENT.search(payload.question):
            return {"kind": "clinical_boundary",
                    "message": "个人诊断和用药调整需要医疗专业人员结合病史、检查及处方判断。可以改问疾病、检查或药物的一般知识。"}
        evidence, _ = retrieve_evidence(payload.question)
        if evidence:
            model_evidence = [{"id": source.id, "text": source.text, "section": source.section,
                               "title": source.title, "year": source.year} for source in evidence]
            raw = model_client.chat_service(payload.question, model_evidence)
            result = grounded_answer(raw, evidence)
            if result and verify_answer(model_client, payload.question, result):
                app.state.last_success = time.monotonic()
                return result
        return {"kind": "insufficient", "message": INSUFFICIENT}

    @app.post("/api/ingest")
    def ingest(payload: ImportRequest):
        try:
            artifact = base64.b64decode(payload.artifact_base64, validate=True) if payload.artifact_base64 else None
        except ValueError:
            raise HTTPException(422, "原始文档的 Base64 格式无效。") from None
        original = (payload.media_type, artifact) if artifact else None
        catalog.import_sources(payload.sources, model_client, original)
        return {"imported": len(payload.sources), "artifact_sha256": hashlib.sha256(artifact).hexdigest() if artifact else None}

    # Use the same origin for the full product on a standalone deployment.
    app.mount("/demos/xunji", StaticFiles(directory=ROOT / "demos" / "xunji", html=True), name="web")
    return app


API_PATHS = {"/api/chat", "/api/retrieve", "/api/sources", "/api/health", "/api/knowledge/stats", "/api/ingest"}

import json

from fastapi.testclient import TestClient

from health_ai.api import create_app
from health_ai.models import Bailian, Settings


class StubModels:
    configured = True
    embedding_model = "test-embedding"
    identity = "test-region:test-embedding"

    def __init__(self):
        self.calls = []
        self.citation = "cdc-sleep"
        self.supported = True

    def embedding_service(self, texts):
        self.calls.append("embedding")
        return [[1.0, 0.0] for _ in texts]

    def rerank_service(self, query, documents, top_n):
        self.calls.append("rerank")
        score = 0.1 if "火星水晶" in query else 0.98
        return [(index, score) for index in range(min(top_n, len(documents)))]

    def chat_service(self, query, evidence):
        self.calls.append("chat")
        return json.dumps({"supported": True, "paragraphs": [
            {"section": "问题回答", "text": "成年人可以尝试保持固定的作息时间。", "citations": [self.citation]}
        ]})


    def verify_support(self, question, paragraphs):
        self.calls.append("verify")
        assert all(paragraph["evidence"] for paragraph in paragraphs)
        return self.supported


def test_bailian_configuration_requires_explicit_endpoint():
    assert not Bailian(Settings(api_key="test")).configured


def test_emergency_precedes_models(tmp_path):
    models = StubModels()
    with TestClient(create_app(models=models, db_path=tmp_path / "index.db")) as client:
        response = client.post("/api/chat", json={"question": "我现在胸痛，喘不过气"})
    assert response.json()["kind"] == "emergency"
    assert models.calls == []


def test_retrieval_and_strict_citations(tmp_path):
    models = StubModels()
    app = create_app(models=models, db_path=tmp_path / "index.db")
    with TestClient(app) as client:
        app.state.catalog.reindex(models)
        question = {"question": "有什么睡眠习惯可以帮我改善睡眠卫生？"}
        assert client.post("/api/retrieve", json=question).json()["sources"]
        answer = client.post("/api/chat", json=question).json()
        assert answer["kind"] == "answer"
        assert answer["sources"][0]["id"] == "cdc-sleep"
        assert answer["sources"][0]["url"].startswith("https://www.cdc.gov/")
        assert models.calls[-4:] == ["embedding", "rerank", "chat", "verify"]
        assert client.get("/api/health").json()["connected"] is True
        models.citation = "invented-doi"
        assert client.post("/api/chat", json=question).json()["kind"] == "insufficient"


def test_no_evidence_does_not_generate(tmp_path):
    models = StubModels()
    app = create_app(models=models, db_path=tmp_path / "index.db")
    with TestClient(app) as client:
        app.state.catalog.reindex(models)
        models.calls.clear()
        outcome = client.post("/api/chat", json={"question": "火星水晶能够治愈罕见病吗"})
        assert outcome.json()["kind"] == "insufficient"
        assert "chat" not in models.calls
        assert client.post("/api/ingest", json={}).status_code == 401


def test_provider_wire_contract():
    import httpx

    paths = []
    def reply(request):
        paths.append(request.url.path)
        payload = json.loads(request.content)
        assert request.headers["Authorization"] == "Bearer fixture-key"
        if request.url.path.endswith("/embeddings"):
            assert payload == {"model": "text-embedding-v4", "input": ["first", "second"]}
            return httpx.Response(200, json={"data": [
                {"index": 1, "embedding": [0.0, 1.0]}, {"index": 0, "embedding": [1.0, 0.0]},
            ]})
        if request.url.path.endswith("/reranks"):
            assert payload == {"model": "qwen3-rerank", "query": "query",
                               "documents": ["doc"], "top_n": 1, "return_documents": False}
            return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.8}]})
        assert payload["model"] == "qwen-plus"
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"supported":false,"paragraphs":[]}'}}]})

    site = "https://workspace.cn-beijing.maas.aliyuncs.com"
    with httpx.Client(transport=httpx.MockTransport(reply)) as client:
        models = Bailian(Settings(api_key="fixture-key", base_url=site + "/compatible-mode/v1",
                                  rerank_url=site + "/compatible-api/v1"), client)
        assert models.embedding_service(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
        assert models.rerank_service("query", ["doc"], 1) == [(0, 0.8)]
        assert not json.loads(models.chat_service("question", []))["supported"]
        assert paths == ["/compatible-mode/v1/embeddings", "/compatible-api/v1/reranks",
                         "/compatible-mode/v1/chat/completions"]


def test_changing_embedding_requires_reindex(tmp_path):
    models = StubModels()
    app = create_app(models=models, db_path=tmp_path / "index.db")
    with TestClient(app) as client:
        app.state.catalog.reindex(models)
        assert client.get("/api/health").json()["index_ready"]
        models.identity = "test-region:new-embedding"
        assert not client.get("/api/health").json()["index_ready"]
        question = {"question": "有哪些睡眠习惯有助于睡眠卫生？"}
        assert client.post("/api/chat", json=question).status_code == 503
        app.state.catalog.reindex(models)
        assert client.post("/api/chat", json=question).json()["kind"] == "answer"


def test_superseded_source_remains_visible_but_cannot_be_cited(tmp_path, monkeypatch):
    monkeypatch.setenv("HEALTH_AI_INGEST_TOKEN", "fixture-admin")
    models = StubModels()
    app = create_app(models=models, db_path=tmp_path / "index.db")
    with TestClient(app) as client:
        app.state.catalog.reindex(models)
        entry = next(source for source in app.state.catalog.sources() if source.id == "cdc-sleep")
        old = entry.model_copy(update={"status": "superseded"}).model_dump(mode="json")
        headers = {"Authorization": "Bearer fixture-admin"}
        assert client.post("/api/ingest", headers=headers, json={"sources": [old]}).status_code == 200
        assert client.get("/api/knowledge/stats").json()["version_status"]["superseded"] == 1
        question = {"question": "睡眠卫生有哪些习惯？"}
        response = client.post("/api/retrieve", json=question)
        assert all(item["id"] != "cdc-sleep" for item in response.json()["sources"])
        assert client.post("/api/chat", json=question).json()["kind"] == "insufficient"


def test_paragraphs_keep_per_chunk_provenance(tmp_path):
    from health_ai.api import grounded_answer

    app = create_app(models=StubModels(), db_path=tmp_path / "index.db")
    chunks = [source for source in app.state.catalog.sources() if source.document_id == "pmid39008468"]
    draft = {"supported": True, "paragraphs": [
        {"section": "问题回答", "text": "研究提示睡眠不足和高血压风险有关。", "citations": [chunks[0].id]},
        {"section": "医学依据", "text": "综述得到了短睡眠相关的结果。", "citations": [chunks[1].id]},
    ]}
    answer = grounded_answer(json.dumps(draft), chunks)
    assert len(answer["sources"]) == 1
    assert [passage["paragraphs"] for passage in answer["sources"][0]["passages"]] == [[1], [2]]
    assert {passage["excerpt_kind"] for passage in answer["sources"][0]["passages"]} == {"summary", "original"}
    draft["paragraphs"][0]["text"] = "来源 https://example.com/fake"
    assert grounded_answer(json.dumps(draft), chunks) is None


def test_validation_privacy_limits_and_cors(tmp_path):
    models = StubModels()
    with TestClient(create_app(models=models, db_path=tmp_path / "index.db")) as client:
        origin = "https://fdd77931-arch.github.io"
        response = client.post("/api/chat", headers={"Origin": origin}, content=b"x" * 12001)
        assert response.status_code == 413
        assert response.headers["access-control-allow-origin"] == origin
        invalid = client.post("/api/chat", json={"question": ["private data"]})
        assert invalid.status_code == 422 and "private data" not in invalid.text
        private = client.post("/api/chat", json={"question": "我的邮箱 x@example.com，想问睡眠卫生的建议。"})
        assert private.status_code == 422 and "x@example.com" not in private.text
        for _ in range(12):
            client.post("/api/retrieve", json={"question": "请介绍睡眠卫生"})
        assert client.post("/api/chat", json={"question": "有哪些睡眠习惯？"}).status_code == 429
        assert client.post("/api/chat", json={"question": "我突然胸痛"}).json()["kind"] == "emergency"
        assert models.calls == []


def test_semantic_only_question_and_support_rejection(tmp_path):
    models = StubModels()
    app = create_app(models=models, db_path=tmp_path / "index.db")
    with TestClient(app) as client:
        app.state.catalog.reindex(models)
        question = {"question": "夜里老在不同时间躺下，可以怎么改？"}
        response = client.post("/api/chat", json=question)
        assert response.json()["kind"] == "answer"
        models.supported = False
        assert client.post("/api/chat", json=question).json()["kind"] == "insufficient"


def test_colloquial_urgent_signals(tmp_path):
    models = StubModels()
    app = create_app(models=models, db_path=tmp_path / "index.db")
    with TestClient(app) as client:
        for question, signal in [
            ("我有高血压，半边脸突然歪了，右手突然抬不起来", "stroke"),
            ("他流血止不住，怎么办", "bleeding"),
            ("我突然呼吸不上气", "breathing"),
            ("失眠让我想自杀，已经准备跳楼", "self_harm"),
        ]:
            result = client.post("/api/chat", json={"question": question}).json()
            assert result["kind"] == "emergency"
            assert signal in result["signals"]
        assert models.calls == []


def test_unreviewed_import_is_private(tmp_path, monkeypatch):
    monkeypatch.setenv("HEALTH_AI_INGEST_TOKEN", "fixture-admin")
    models = StubModels()
    app = create_app(models=models, db_path=tmp_path / "index.db")
    with TestClient(app) as client:
        source = app.state.catalog.sources()[0]
        entry = source.model_copy(update={"id": "unreviewed", "status": "unverified"}).model_dump(mode="json")
        headers = {"Authorization": "Bearer fixture-admin"}
        assert client.post("/api/ingest", headers=headers, json={"sources": [entry]}).status_code == 200
        listed = client.get("/api/sources?limit=60").json()["sources"]
        assert "unreviewed" not in {item["id"] for item in listed}
        assert models.calls == []

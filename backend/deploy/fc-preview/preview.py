"""Read-only smoke checks for a signed Alibaba FC preview invocation."""
import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

from health_ai.main import app


@app.post("/invoke", include_in_schema=False)
async def preview(request: Request):
    try:
        event = await request.json()
    except ValueError:
        event = None
    if event != {"check": "health-ai"}:
        return JSONResponse({"error": "unsupported_check"}, status_code=400)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        health = await client.get("/api/health")
        catalog = await client.get("/api/knowledge/stats")
        emergency = await client.post("/api/chat", json={"question": "我现在突然胸痛，喘不过气。"})
        frontend = await client.get("/demos/xunji/")
        for check in (health, catalog, emergency, frontend):
            check.raise_for_status()
    return {
        "status": health.json(),
        "documents": catalog.json()["documents"],
        "evidence_chunks": catalog.json()["verified_chunks"],
        "emergency": emergency.json()["kind"],
        "frontend_bundled": "<title>Health AI</title>" in frontend.text,
    }

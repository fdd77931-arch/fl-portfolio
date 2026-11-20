"""Evaluate 115 synthetic questions offline or through the deployed HTTP API."""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from .api import PERSONAL_TREATMENT
from .knowledge import SEED, Source, bm25, matching_terms
from .safety import emergency_signals

CASES = Path(__file__).resolve().parents[1] / "data" / "eval_cases.jsonl"


def load_cases():
    return [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line]


def offline(case, sources):
    question, expected = case["question"], case["expected"]
    signals = emergency_signals(question)
    if expected == "emergency":
        return {"passed": case["signal"] in signals}
    if signals:
        return {"passed": False, "unexpected_signals": signals}
    if expected == "clinical_boundary":
        return {"passed": bool(PERSONAL_TREATMENT.search(question))}
    match = matching_terms(question, sources)
    if expected == "insufficient":
        return {"passed": not match, "check": "no curated term overlap"}
    top = bm25(question, sources)
    by_id = {source.id: source.document_id for source in sources}
    desired = set(case["document_ids"])
    rank = next((n for n, key in enumerate(top, 1) if by_id[key] in desired), None)
    return {"passed": rank is not None and rank <= 20 and bool(match), "bm25_rank": rank}


def live(case, client, interval):
    question, expected = case["question"], case["expected"]
    payload = {"question": question}

    def post(path):
        response = client.post(path, json=payload)
        if interval:
            time.sleep(interval)
        response.raise_for_status()
        return response.json()

    answer = post("/api/chat")
    if expected != "evidence":
        return {"passed": answer["kind"] == expected and (
            expected != "emergency" or case["signal"] in answer["signals"]
        ), "actual": answer["kind"]}

    retrieval = post("/api/retrieve?trace=true")
    # The trace contains stable chunk IDs. These are translated to document IDs by the API.
    ranked = [item["document_id"] for item in retrieval.get("sources", [])]
    by_chunk = retrieval.get("ranking", {}).get("documents", {})
    lexical = [by_chunk.get(key, key) for key in retrieval.get("ranking", {}).get("bm25", [])]
    semantic = [by_chunk.get(key, key) for key in retrieval.get("ranking", {}).get("vector", [])]
    fused = [by_chunk.get(key, key) for key in retrieval.get("ranking", {}).get("fused", [])]
    target = set(case["document_ids"])

    def rank(ids):
        return next((i for i, doc in enumerate(ids, 1) if doc in target), None)

    cited = {citation for paragraph in answer.get("paragraphs", []) for citation in paragraph["citations"]}
    sources = {item["document_id"] for item in answer.get("sources", [])}
    valid = bool(cited) and cited == sources
    return {"passed": answer["kind"] == "answer" and valid and bool(cited & target),
            "bm25_rank": rank(lexical), "vector_rank": rank(semantic), "fused_rank": rank(fused),
            "rerank_rank": rank(ranked), "citation_integrity": valid, "actual": answer["kind"]}


def link_status(url):
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=8) as response:
            return response.status_code
    except httpx.RequestError:
        return None


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--base-url", help="Live FastAPI origin. Omit for local BM25 and safety checks.")
    cli.add_argument("--interval", type=float, default=5.2, help="Seconds between live requests")
    cli.add_argument("--limit", type=int)
    cli.add_argument("--links", action="store_true")
    cli.add_argument("--report", type=Path)
    args = cli.parse_args()
    sources = [Source.model_validate(row) for row in json.loads(SEED.read_text(encoding="utf-8"))
               if row["status"] == "verified"]
    cases = load_cases()[:args.limit]
    results = []
    with httpx.Client(base_url=args.base_url or "http://localhost", timeout=85) as client:
        for case in cases:
            try:
                result = live(case, client, args.interval) if args.base_url else offline(case, sources)
            except httpx.HTTPError as exc:
                result = {"passed": False, "error": type(exc).__name__}
            results.append({**case, **result})
    links = {}
    if args.links:
        urls = list(dict.fromkeys(str(source.url) for source in sources))
        with ThreadPoolExecutor(max_workers=5) as pool:
            links = dict(zip(urls, pool.map(link_status, urls), strict=True))

    report = {"mode": "live" if args.base_url else "offline", "passed": sum(r["passed"] for r in results),
              "total": len(results), "links": links, "cases": results}
    for label in ("evidence", "emergency", "insufficient", "clinical_boundary"):
        subset = [row for row in results if row["expected"] == label]
        print(f"{label}: {sum(row['passed'] for row in subset)}/{len(subset)}")
    for row in results:
        if not row["passed"]:
            print(f"{row['id']}: {row['question']}")
    if links:
        print(f"Source links (2xx): {sum(status is not None and 200 <= status < 300 for status in links.values())}/{len(links)}")
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return int(report["passed"] != report["total"])


if __name__ == "__main__":
    raise SystemExit(main())

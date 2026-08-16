"""REQ-005 proof runner.

Drives the live API from inside the `test` container (which sits on the
`backend` docker network alongside the `api` and `db` services). The
script is intentionally single-purpose: it loads the corpus, runs the
acceptance questions, and persists three machine-readable artifacts
(`corpus-index.json`, `results.json`, `source-map.json`) plus a
human-readable `results.md` and `source-map.md`.

It is idempotent — re-ingesting the same content produces the same
documents (deduped by content_sha), but the script always rewrites the
result files so the verifier sees fresh output.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

# Inside the test container the corpus and proof dirs are mounted/copied
# at canonical locations. The paths also resolve on the host because the
# script lives in /srv/repo/scripts (mapped from ./scripts) and reads
# from /srv/data (mapped from ./data).
CORPUS_DIR = Path(os.environ.get("CORPUS_DIR", "/srv/data/corpus"))
PROOF_DIR = Path(os.environ.get("PROOF_DIR", "/srv/repo/proof"))
QUESTIONS_PATH = PROOF_DIR / "questions.json"

API = os.environ.get("API_BASE", "http://api:8000")
WORKSPACE = os.environ.get("PROOF_WORKSPACE", "default")
COLLECTION = os.environ.get("PROOF_COLLECTION", "proof-corpus")
TIMEOUT = 60.0
POLL_S = 1.0
POLL_TIMEOUT_S = 60.0


_MIME = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
}


def _wait_for_api() -> None:
    """Block until /healthz responds or POLL_TIMEOUT_S elapses."""
    deadline = time.time() + POLL_TIMEOUT_S
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            r = httpx.get(f"{API}/healthz", timeout=2.0)
            if r.status_code == 200:
                return
        except Exception as exc:
            last_err = exc
        time.sleep(POLL_S)
    raise RuntimeError(f"API not reachable at {API}: {last_err}")


def _wait_for_db() -> None:
    """Block until /readyz reports db=ok."""
    deadline = time.time() + POLL_TIMEOUT_S
    last_body: dict | None = None
    while time.time() < deadline:
        try:
            r = httpx.get(f"{API}/readyz", timeout=2.0)
            if r.status_code == 200:
                last_body = r.json()
                if last_body.get("components", {}).get("db") == "ok":
                    return
        except Exception:
            pass
        time.sleep(POLL_S)
    raise RuntimeError(f"DB not ready via /readyz: {last_body}")


def _ingest_one(client: httpx.Client, file_path: Path) -> dict:
    mime = _MIME.get(file_path.suffix.lower(), "application/octet-stream")
    with file_path.open("rb") as fh:
        resp = client.post(
            "/v1/ingest",
            data={"workspace": WORKSPACE, "collection": COLLECTION},
            files={"upload": (file_path.name, fh, mime)},
            timeout=TIMEOUT,
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"ingest failed for {file_path.name}: {resp.status_code} {resp.text}"
        )
    body = resp.json()
    return {
        "file_name": file_path.name,
        "format": file_path.suffix.lower().lstrip("."),
        "document_id": body["document_id"],
        "collection_id": body["collection_id"],
        "chunks_created": body["chunks_created"],
        "content_sha": body["content_sha"],
    }


def _ingest_corpus(client: httpx.Client) -> list[dict]:
    """Ingest every supported file under CORPUS_DIR into COLLECTION.

    Returns the list of per-document metadata records.
    """
    if not CORPUS_DIR.is_dir():
        raise RuntimeError(f"corpus dir not found: {CORPUS_DIR}")
    docs: list[dict] = []
    for path in sorted(CORPUS_DIR.iterdir()):
        if path.suffix.lower() not in _MIME:
            print(f"[skip] {path.name}: unsupported extension")
            continue
        rec = _ingest_one(client, path)
        docs.append(rec)
        print(
            f"[ingest] {path.name} → doc={rec['document_id']} "
            f"chunks={rec['chunks_created']} sha={rec['content_sha'][:12]}…"
        )
    if not docs:
        raise RuntimeError(f"no supported files found in {CORPUS_DIR}")
    return docs


def _query_chunk_text(client: httpx.Client, chunk_id: int) -> dict:
    r = client.get(f"/v1/citations/{chunk_id}", timeout=TIMEOUT)
    if r.status_code != 200:
        return {"error": r.text}
    return r.json()


def _run_questions(client: httpx.Client, collection_id: int) -> list[dict]:
    questions = json.loads(QUESTIONS_PATH.read_text())["questions"]
    out: list[dict] = []
    for q in questions:
        body = {
            "question": q["question"],
            "collection_id": collection_id,
            "workspace": WORKSPACE,
            "top_k": q.get("top_k", 5),
        }
        resp = client.post("/v1/query", json=body, timeout=TIMEOUT)
        if resp.status_code != 200:
            result = {
                "id": q["id"],
                "category": q["category"],
                "topic": q["topic"],
                "question": q["question"],
                "expected_status": q["expected_status"],
                "actual_status": "error",
                "error": resp.text,
                "answer": None,
                "reason": None,
                "citations": [],
                "best_score": None,
                "threshold": None,
            }
        else:
            qbody = resp.json()
            result = {
                "id": q["id"],
                "category": q["category"],
                "topic": q["topic"],
                "question": q["question"],
                "expected_status": q["expected_status"],
                "actual_status": qbody.get("status"),
                "answer": qbody.get("answer"),
                "reason": qbody.get("reason"),
                "citations": qbody.get("citations", []),
                "best_score": qbody.get("best_score"),
                "threshold": qbody.get("threshold"),
            }
            # Resolve each citation's full chunk text so source-map.md
            # can show a clean excerpt.
            for cite in result["citations"]:
                detail = _query_chunk_text(client, cite["chunk_id"])
                cite["_resolved"] = detail
        # Match actual vs expected, with a per-question boolean flag.
        result["matched_expected"] = result["actual_status"] == result["expected_status"]
        # For positive cases, also flag whether the answer text hits at
        # least one of the topic keywords.
        keyword_hit = False
        keyword_check = q.get("expected_topic_keywords", []) or []
        if result["expected_status"] == "answered" and keyword_check:
            haystack = (result.get("answer") or "").lower()
            if any(k.lower() in haystack for k in keyword_check):
                keyword_hit = True
            else:
                # Look inside citations too — the answer template may
                # have folded the keyword into the chunk text but not
                # echoed it in the answer surface.
                for cite in result["citations"]:
                    if any(k.lower() in (cite.get("text", "")).lower() for k in keyword_check):
                        keyword_hit = True
                        break
        result["keyword_hit"] = keyword_hit
        out.append(result)
        flag = "OK " if result["matched_expected"] else "MISS"
        print(
            f"[query] {q['id']} ({q['category']}) {flag} "
            f"expected={q['expected_status']} actual={result['actual_status']}"
        )
    return out


def _write_source_map(
    client: httpx.Client, docs: list[dict], results: list[dict]
) -> dict:
    """Build a source map: document → chunks → answer citations."""
    smap: dict[str, dict] = {}
    for d in docs:
        # Pull every chunk for this document via citation endpoint,
        # discovered through retrieval at top_k=large.
        # Simpler: list the chunks that were cited in the questions.
        cited_chunks: list[dict] = []
        for r in results:
            for cite in r["citations"]:
                detail = cite.get("_resolved") or {}
                if detail.get("document_id") == d["document_id"]:
                    cited_chunks.append(
                        {
                            "chunk_id": cite["chunk_id"],
                            "section": cite.get("section"),
                            "page": cite.get("page"),
                            "score": cite.get("score"),
                            "excerpt": (cite.get("text") or "")[:160],
                        }
                    )
        smap[d["file_name"]] = {
            "document_id": d["document_id"],
            "format": d["format"],
            "content_sha": d["content_sha"],
            "chunks_created": d["chunks_created"],
            "cited_chunks": cited_chunks,
        }
    return smap


def _render_markdown(results: list[dict], docs: list[dict]) -> str:
    lines: list[str] = []
    lines.append("# REQ-005 Proof Results")
    lines.append("")
    lines.append("**Workspace:** `default`  ")
    lines.append(f"**Collection:** `proof-corpus`  ")
    lines.append(f"**Documents ingested:** {len(docs)}  ")
    lines.append(f"**Questions exercised:** {len(results)}")
    lines.append("")

    pos = [r for r in results if r["category"] == "positive"]
    neg = [r for r in results if r["category"] == "negative"]
    pos_ok = sum(1 for r in pos if r["matched_expected"])
    neg_ok = sum(1 for r in neg if r["matched_expected"])
    lines.append("## Headline")
    lines.append("")
    lines.append(f"- Positive: **{pos_ok}/{len(pos)}** matched the expected `answered` status.")
    lines.append(
        f"- Negative: **{neg_ok}/{len(neg)}** matched the expected `refused` status."
    )
    lines.append(
        f"- Topic-keyword hit (positive): "
        f"**{sum(1 for r in pos if r['keyword_hit'])}/{len(pos)}** answer/citations "
        "contain at least one of the topic keywords."
    )
    lines.append("")

    lines.append("## Per-question results")
    lines.append("")
    lines.append("| ID | Category | Expected | Actual | Match | Score |")
    lines.append("|----|----------|----------|--------|-------|-------|")
    for r in results:
        score = r["best_score"]
        score_s = f"{score:.4f}" if isinstance(score, (int, float)) else "—"
        lines.append(
            f"| {r['id']} | {r['category']} | {r['expected_status']} "
            f"| {r['actual_status']} | {'✅' if r['matched_expected'] else '❌'} "
            f"| {score_s} |"
        )
    lines.append("")

    lines.append("## Positive — answered evidence")
    lines.append("")
    for r in pos:
        lines.append(f"### {r['id']} — {r['question']}")
        lines.append("")
        if r["matched_expected"]:
            ans = (r.get("answer") or "").strip()
            ans_first_line = ans.splitlines()[0] if ans else "(empty)"
            lines.append(f"- First line of answer: `{ans_first_line}`")
            lines.append(
                f"- Topic keywords hit: "
                f"{'yes' if r['keyword_hit'] else 'no'} "
                f"(expected any of: {', '.join(_K(r))})"
            )
            lines.append(f"- Citations: {len(r['citations'])}")
            for cite in r["citations"]:
                lines.append(
                    f"  - chunk_id={cite['chunk_id']} "
                    f"file={cite.get('file_name')} "
                    f"section={cite.get('section')!r} "
                    f"page={cite.get('page')} "
                    f"score={cite.get('score')}"
                )
        else:
            lines.append(f"- Refused instead of answered: {r.get('reason')}")
        lines.append("")

    lines.append("## Negative — refusal evidence")
    lines.append("")
    for r in neg:
        lines.append(f"### {r['id']} — {r['question']}")
        lines.append("")
        if r["matched_expected"]:
            lines.append(f"- Refused as expected. reason=`{r.get('reason')}`")
            lines.append(f"- best_score={r.get('best_score')} threshold={r.get('threshold')}")
        else:
            lines.append(
                f"- **UNEXPECTED** status={r['actual_status']} (expected refused)"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def _K(r: dict) -> list[str]:
    """Return the topic keywords recorded in questions.json for r['id']."""
    # Re-load questions.json lazily to grab keywords.
    qmeta = json.loads(QUESTIONS_PATH.read_text())["questions"]
    for q in qmeta:
        if q["id"] == r["id"]:
            return q.get("expected_topic_keywords", []) or []
    return []


def _render_source_map_md(smap: dict) -> str:
    lines: list[str] = []
    lines.append("# Source Map")
    lines.append("")
    lines.append(
        "Every chunk that answered an acceptance question traces back to "
        "the document and section shown here. SHA-256s match `corpus-index.json`."
    )
    lines.append("")
    for fname, entry in smap.items():
        lines.append(f"## {fname}")
        lines.append("")
        lines.append(f"- document_id: `{entry['document_id']}`")
        lines.append(f"- format: `{entry['format']}`")
        lines.append(f"- content_sha: `{entry['content_sha']}`")
        lines.append(f"- chunks created: {entry['chunks_created']}")
        if entry["cited_chunks"]:
            lines.append("- chunks cited by acceptance questions:")
            for cc in entry["cited_chunks"]:
                loc_parts = []
                if cc.get("section"):
                    loc_parts.append(f"section={cc['section']!r}")
                if cc.get("page"):
                    loc_parts.append(f"page={cc['page']}")
                loc = ", ".join(loc_parts) if loc_parts else "no location metadata"
                lines.append(
                    f"  - chunk_id={cc['chunk_id']} "
                    f"({loc}) score={cc['score']} "
                    f"excerpt=`{cc['excerpt']}`"
                )
        else:
            lines.append(
                "- (no chunks cited — either no question targets this "
                "document or all questions refused)"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    PROOF_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[boot] waiting for API at {API}")
    _wait_for_api()
    _wait_for_db()

    with httpx.Client(base_url=API) as client:
        print("[boot] ingesting corpus")
        docs = _ingest_corpus(client)
        collection_id = docs[0]["collection_id"]

        # Reset source-map: previous run may have left stale rows.
        smap_client = httpx.Client(base_url=API)
        try:
            print("[boot] running questions")
            results = _run_questions(client, collection_id)
            print("[boot] building source map")
            smap = _write_source_map(smap_client, docs, results)
        finally:
            smap_client.close()

    # Persist machine-readable outputs.
    (PROOF_DIR / "corpus-index.json").write_text(
        json.dumps(
            {"workspace": WORKSPACE, "collection": COLLECTION, "documents": docs},
            indent=2,
        )
    )
    (PROOF_DIR / "results.json").write_text(
        json.dumps(
            {
                "workspace": WORKSPACE,
                "collection": COLLECTION,
                "collection_id": collection_id,
                "questions": results,
            },
            indent=2,
        )
    )
    (PROOF_DIR / "source-map.json").write_text(json.dumps(smap, indent=2))

    # Persist human-readable outputs.
    (PROOF_DIR / "results.md").write_text(_render_markdown(results, docs))
    (PROOF_DIR / "source-map.md").write_text(_render_source_map_md(smap))

    pos = [r for r in results if r["category"] == "positive"]
    neg = [r for r in results if r["category"] == "negative"]
    pos_ok = sum(1 for r in pos if r["matched_expected"])
    neg_ok = sum(1 for r in neg if r["matched_expected"])
    print(
        f"[done] docs={len(docs)} questions={len(results)} "
        f"positive_ok={pos_ok}/{len(pos)} negative_ok={neg_ok}/{len(neg)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
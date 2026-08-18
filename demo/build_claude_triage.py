"""Build step for the Claude 3,500-alert Triage Explorer dataset.

Joins the committed Claude API predictions (results/claude_api/all) with the
source alerts (data/processed/sample_3500.jsonl) and recomputes the REAL RAG
retrieval for every alert with the same Retriever the pipeline used — exactly
the approach build_demo_data.py takes for the historical 129-alert Ollama run.

Writes: demo/backend/data/claude_alerts.json

Run:  demo/.venv/bin/python demo/build_claude_triage.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_demo_data import (
    DISPLAY_FIELDS,
    OUT,
    ROOT,
    build_retriever,
    classify_pair,
    format_hits,
    index_by_id,
    read_jsonl,
    triage_correct,
)

ALERTS_SRC = ROOT / "data" / "processed" / "sample_3500.jsonl"
CLAUDE_DIR = ROOT / "results" / "claude_api" / "all"
LLM_ONLY_PRED = CLAUDE_DIR / "claude_3500_predictions.jsonl"
LLM_RAG_PRED = CLAUDE_DIR / "rag_claude_predictions.jsonl"


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    alerts = index_by_id(read_jsonl(ALERTS_SRC))
    only_pred = index_by_id(read_jsonl(LLM_ONLY_PRED))
    rag_pred = index_by_id(read_jsonl(LLM_RAG_PRED))

    ids = list(rag_pred.keys())
    print(f"Claude run alerts: {len(ids)}", file=sys.stderr)

    retriever = build_retriever()

    records = []
    tally = {"both_correct": 0, "rag_fixed": 0, "rag_broke": 0, "both_wrong": 0}
    for i, aid in enumerate(ids, 1):
        alert = alerts.get(aid, {})
        op = only_pred.get(aid, {})
        rp = rag_pred.get(aid, {})

        actual = bool(rp.get("actual_is_attack", alert.get("is_attack", False)))
        only_ok = triage_correct(actual, op.get("predicted_is_attack"))
        rag_ok = triage_correct(actual, rp.get("predicted_is_attack"))
        tag = classify_pair(only_ok, rag_ok)
        tally[tag] += 1

        hits = retriever.retrieve(alert) if alert else []
        if i % 100 == 0 or i == len(ids):
            print(f"  [{i}/{len(ids)}]  {tally}", file=sys.stderr)

        display = {k: alert.get(k) for k in DISPLAY_FIELDS}
        records.append({
            "alert_id": aid,
            "display": display,
            "ground_truth": {
                "is_attack": actual,
                "attack_phase": rp.get("actual_attack_phase"),
            },
            "llm_only": {
                "predicted_is_attack": op.get("predicted_is_attack"),
                "predicted_attack_phase": op.get("predicted_attack_phase"),
                "confidence": op.get("confidence"),
                "explanation": op.get("explanation"),
                "latency_ms": op.get("latency_ms"),
                "correct": only_ok,
            },
            "llm_rag": {
                "predicted_is_attack": rp.get("predicted_is_attack"),
                "predicted_attack_phase": rp.get("predicted_attack_phase"),
                "confidence": rp.get("confidence"),
                "explanation": rp.get("explanation"),
                "latency_ms": rp.get("latency_ms"),
                "retrieval_ms": rp.get("retrieval_ms"),
                "correct": rag_ok,
                "retrieved": format_hits(hits),
            },
            "tag": tag,
        })

    out_path = OUT / "claude_alerts.json"
    out_path.write_text(json.dumps(records, indent=1))
    print(f"\nWrote {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)",
          file=sys.stderr)
    print(f"Story tally: {tally}", file=sys.stderr)


if __name__ == "__main__":
    main()

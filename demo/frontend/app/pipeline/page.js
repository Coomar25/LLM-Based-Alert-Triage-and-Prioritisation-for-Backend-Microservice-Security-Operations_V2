"use client";

import { useEffect, useState } from "react";
import { getOverview } from "@/lib/api";

const STAGES = [
  {
    n: 1,
    title: "Parse & normalise",
    body:
      "2.65M alerts from three IDS (Wazuh HIDS, Suricata NIDS, AMiner) in three JSON schemas are normalised into one unified schema, with severity reconciled onto a single 1–5 scale.",
  },
  {
    n: 2,
    title: "Ground-truth labelling",
    body:
      "Each alert is labelled attack vs. benign and tagged with its attack phase, derived from the AIT-ADS attack timelines — the reference for scoring.",
  },
  {
    n: 3,
    title: "Knowledge base",
    body:
      "Runbooks, MITRE ATT&CK techniques and CVEs are chunked, embedded (all-MiniLM-L6-v2) and stored in ChromaDB for source-balanced retrieval.",
  },
  {
    n: 4,
    title: "Triage & evaluate",
    body:
      "An LLM classifies each held-out alert — claude-haiku-4-5 via the Claude API for the headline 3,500-alert run; llama3.1:8b via Ollama for the earlier 129-alert local run. LLM+RAG first retrieves the top-k KB entries. All pipelines are scored on identical precision/recall/F1 metrics.",
  },
];

// Strip the date suffix from a model id for display (…-20251001).
const shortModel = (m) => (m || "").replace(/-\d{8}$/, "");

export default function Pipeline() {
  const [ov, setOv] = useState(null);
  useEffect(() => {
    getOverview().then(setOv).catch(() => {});
  }, []);

  // Claude API headline run (overview.claude_3500); null until loaded or on
  // an overview.json that predates the section.
  const c = ov?.claude_3500;

  return (
    <div className="page">
      <h1 className="title">The pipeline</h1>
      <p className="subtitle">
        End-to-end, from raw multi-IDS alerts to a scored triage decision. The
        demo evaluates the final stage; the earlier stages produce the cached
        data it runs on.
      </p>

      <div className="flow">
        {STAGES.map((s, i) => (
          <div key={s.n} style={{ display: "contents" }}>
            <div className="stage">
              <div className="n">{s.n}</div>
              <h3>{s.title}</h3>
              <p>{s.body}</p>
            </div>
            {i < STAGES.length - 1 && <div className="arrowcol">→</div>}
          </div>
        ))}
      </div>

      <div className="section-label">Experimental setup</div>
      <div className="grid cols-4">
        <div className="card stat">
          <div className="k">Dataset</div>
          <div className="v" style={{ fontSize: 22 }}>
            AIT-ADS
          </div>
          <div className="sub">Zenodo 8263181 · CC-BY 4.0 · 8 attack scenarios</div>
        </div>
        <div className="card stat">
          <div className="k">Model — headline run</div>
          <div className="v" style={{ fontSize: 22 }}>
            {shortModel(c?.config.model) || "claude-haiku-4-5"}
          </div>
          <div className="sub">
            via the Claude API · earlier run:{" "}
            {ov ? ov.config.model : "llama3.1:8b"} (Ollama, local)
          </div>
        </div>
        <div className="card stat">
          <div className="k">Test alerts scored</div>
          <div className="v" style={{ fontSize: 22 }}>
            {c ? c.config.n_alerts.toLocaleString() : "3,500"}
          </div>
          <div className="sub">
            held-out test split · earlier local run:{" "}
            {ov ? ov.config.n_alerts : 129} alerts
          </div>
        </div>
        <div className="card stat">
          <div className="k">Knowledge base</div>
          <div className="v" style={{ fontSize: 22 }}>
            {ov ? ov.config.kb_document_count.toLocaleString() : "—"} docs
          </div>
          <div className="sub">Runbooks · MITRE ATT&CK · CVEs · ChromaDB</div>
        </div>
      </div>

      <div className="section-label">Why these choices (viva notes)</div>
      <div className="card">
        <ul style={{ lineHeight: 1.7, margin: 0, paddingLeft: 20 }}>
          <li>
            <b>Two model tiers, one experiment</b> — the pipeline first ran
            fully locally (llama3.1:8b via Ollama: zero cost, reproducible,
            data-sovereign) on 129 alerts, then scaled to claude-haiku-4-5 via
            the Claude API for the 3,500-alert headline run.
          </li>
          <li>
            <b>RAG&rsquo;s value depends on the model</b> — retrieval improved
            the stronger Claude model (+4.6% F1, 8 of 10 attack phases better,
            none worse) but made the local 8B model more cautious and less
            capable (recall fell). Same KB, same retriever, opposite outcome.
          </li>
          <li>
            <b>all-MiniLM-L6-v2 embeddings</b> — 384-dim, CPU-friendly, a
            standard, defensible RAG baseline.
          </li>
          <li>
            <b>Source-balanced retrieval</b> — CVEs outnumber runbooks ~4600:1,
            so naive top-k floods the prompt with CVE noise; balancing guarantees
            a runbook + a technique are always seen.
          </li>
          <li>
            <b>No ground-truth leakage</b> — retrieval queries use only
            observable alert content, never the label.
          </li>
        </ul>
      </div>
    </div>
  );
}

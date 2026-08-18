"use client";

import { useEffect, useState } from "react";
import { getOverview, getPhases, pct, secs, PALETTE } from "@/lib/api";
import PhaseChart from "./PhaseChart";

function Stat({ k, v, sub, delta }) {
  return (
    <div className="card stat">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
      {sub && <div className="sub">{sub}</div>}
      {delta}
    </div>
  );
}

function best(a, b, higherBetter = true) {
  if (a == null || b == null) return [false, false];
  if (a === b) return [false, false];
  const aWins = higherBetter ? a > b : a < b;
  return [aWins, !aWins];
}

// Headline run: 3,500 held-out test alerts scored with claude-haiku-4-5 via
// the Claude API. Served by the backend as overview.claude_3500 (built from
// results/claude_api/*); the constants below are only a fallback for an
// overview.json that predates that section.
const CLAUDE_3500 = {
  model: "claude-haiku-4-5",
  n_alerts: 3500,
  kb_document_count: 37545,
  top_k: 3,
  dataset: "AIT-ADS (Zenodo 8263181)",
  pipelines: [
    {
      name: "LLM-only",
      precision: 0.953734,
      recall: 0.47,
      f1: 0.629689,
      fpr: 0.057,
      accuracy: 0.605143,
      mean_latency_ms: 1913.99,
    },
    {
      name: "LLM + RAG (top-3)",
      precision: 0.935552,
      recall: 0.5284,
      f1: 0.675358,
      fpr: 0.091,
      accuracy: 0.637143,
      mean_latency_ms: 2127.94,
    },
    {
      name: "LLM + RAG (runbook-only)",
      precision: 0.918262,
      recall: 0.4988,
      f1: 0.646449,
      fpr: 0.111,
      accuracy: 0.610286,
      mean_latency_ms: 2305.69,
    },
  ],
  rag_effect: {
    delta_f1: 0.045669,
    delta_recall: 0.0584,
    delta_precision: -0.018182,
    delta_fpr: 0.034,
    phases_improved: 8,
    phases_worsened: 0,
  },
};

// Fallback per-attack-phase recall for the Claude 3,500-alert run
// (results/claude_api/comparison_claude_3500).
const CLAUDE_PHASES = [
  { phase: "network_scans", llm_only: 0.010345, llm_rag: 0.072414, delta: 0.0621 },
  { phase: "service_scans", llm_only: 0.575862, llm_rag: 0.596552, delta: 0.0207 },
  { phase: "dirb", llm_only: 0.980936, llm_rag: 0.986135, delta: 0.0052 },
  { phase: "wpscan", llm_only: 1.0, llm_rag: 1.0, delta: 0 },
  { phase: "webshell", llm_only: 0.117647, llm_rag: 0.279412, delta: 0.1618 },
  { phase: "cracking", llm_only: 0.019444, llm_rag: 0.175, delta: 0.1556 },
  { phase: "reverse_shell", llm_only: 0.257576, llm_rag: 0.287879, delta: 0.0303 },
  { phase: "privilege_escalation", llm_only: 0.319672, llm_rag: 0.327869, delta: 0.0082 },
  { phase: "service_stop", llm_only: 0.571429, llm_rag: 0.571429, delta: 0 },
  { phase: "dnsteal", llm_only: 0.011111, llm_rag: 0.147222, delta: 0.1361 },
];

// Prefer the backend's overview.claude_3500 section; fall back to the
// baked-in constants above so the page still renders against old data.
function claudeRun(ov) {
  const c = ov?.claude_3500;
  if (!c) return { run: CLAUDE_3500, phases: CLAUDE_PHASES };
  const P = c.pipelines;
  const pipelines = [
    { name: "LLM-only", ...P.llm_only },
    { name: `LLM + RAG (top-${c.config.top_k})`, ...P.llm_rag },
  ];
  if (P.llm_rag_runbook)
    pipelines.push({ name: "LLM + RAG (runbook-only)", ...P.llm_rag_runbook });
  return {
    run: {
      model: c.config.model,
      n_alerts: c.config.n_alerts,
      kb_document_count: c.config.kb_document_count,
      top_k: c.config.top_k,
      dataset: c.config.dataset,
      pipelines,
      rag_effect: c.rag_effect,
    },
    phases: c.phases,
  };
}

const CLAUDE_ROWS = [
  { k: "Precision", key: "precision", hb: true, fmt: pct },
  { k: "Recall", key: "recall", hb: true, fmt: pct },
  { k: "F1 score", key: "f1", hb: true, fmt: pct },
  { k: "Accuracy", key: "accuracy", hb: true, fmt: pct },
  { k: "False-positive rate", key: "fpr", hb: false, fmt: pct },
  { k: "Mean latency / alert", key: "mean_latency_ms", hb: false, fmt: secs },
];

export default function Overview() {
  const [ov, setOv] = useState(null);
  const [phases, setPhases] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    Promise.all([getOverview(), getPhases()])
      .then(([o, p]) => {
        setOv(o);
        setPhases(p);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  if (err)
    return (
      <div className="page">
        <div className="errbox">
          Could not reach the API ({err}).<br />
          Start the backend: <code>demo/.venv/bin/uvicorn backend.main:app
          --app-dir demo --port 8077</code>
        </div>
      </div>
    );
  if (!ov || !phases) return <div className="page loading">Loading…</div>;

  const { run: c, phases: cPhases } = claudeRun(ov);
  const [cOnly, cRag] = c.pipelines;
  const cEff = c.rag_effect;

  const A = ov.pipelines.llm_only;
  const B = ov.pipelines.llm_rag;
  const eff = ov.rag_effect;

  const localRows = [
    { k: "Precision", a: A.precision, b: B.precision, hb: true },
    { k: "Recall", a: A.recall, b: B.recall, hb: true },
    { k: "F1 score", a: A.f1, b: B.f1, hb: true },
    { k: "False-positive rate", a: A.fpr, b: B.fpr, hb: false },
  ];

  return (
    <div className="page">
      <h1 className="title">Does retrieval-augmentation help LLM alert triage?</h1>
      <p className="subtitle">
        Two pipelines classify the same {c.n_alerts.toLocaleString()} held-out
        security alerts from {c.dataset} as attack vs. benign, using{" "}
        <b>{c.model}</b> via the Claude API. The only difference: LLM+RAG first
        retrieves the top-{c.top_k} most relevant entries from a{" "}
        {c.kb_document_count.toLocaleString()}-document knowledge base
        (runbooks · MITRE ATT&CK · CVEs) and injects them into the prompt.
      </p>

      <div className="grid cols-4">
        <Stat
          k="F1 — LLM-only"
          v={pct(cOnly.f1)}
          sub={`${pct(cOnly.precision)} precision · ${pct(cOnly.recall)} recall`}
        />
        <Stat
          k="F1 — LLM + RAG"
          v={pct(cRag.f1)}
          sub={`${pct(cRag.precision)} precision · ${pct(cRag.recall)} recall`}
          delta={
            <div className="sub delta up">
              ▲ {pct(cEff.delta_f1)} F1 vs LLM-only
            </div>
          }
        />
        <Stat
          k="Recall gained"
          v={pct(cEff.delta_recall)}
          sub="RAG caught more genuine attacks"
          delta={
            <div className="sub delta down">
              ▲ {pct(cEff.delta_fpr)} more false positives
            </div>
          }
        />
        <Stat
          k="Latency cost"
          v={`${(cRag.mean_latency_ms / cOnly.mean_latency_ms).toFixed(1)}×`}
          sub={`${secs(cOnly.mean_latency_ms)} → ${secs(cRag.mean_latency_ms)} per alert`}
          delta={<div className="sub delta down">▲ slower with retrieval</div>}
        />
      </div>

      <div className="section-label">Headline comparison</div>
      <div className="grid cols-2">
        <div className="card">
          <table className="cmp">
            <thead>
              <tr>
                <th>Metric</th>
                {c.pipelines.map((p, i) => (
                  <th key={p.name}>
                    <span
                      className="swatch"
                      style={{
                        background: i === 0 ? PALETTE.llmOnly : PALETTE.llmRag,
                        opacity: i === 2 ? 0.55 : 1,
                      }}
                    />
                    {p.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CLAUDE_ROWS.map((r) => {
                const vals = c.pipelines.map((p) => p[r.key]);
                const winner = r.hb ? Math.max(...vals) : Math.min(...vals);
                return (
                  <tr key={r.k}>
                    <td>{r.k}</td>
                    {vals.map((v, i) => (
                      <td key={i} className={v === winner ? "best" : ""}>
                        {r.fmt(v)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="card">
          <div className="section-label" style={{ margin: "0 0 12px" }}>
            The key finding
          </div>
          <div className="callout">
            Retrieval <b>helped</b>: F1 rose {pct(cEff.delta_f1)} and recall
            rose {pct(cEff.delta_recall)}, with {cEff.phases_improved} of 10
            attack phases improved and {cEff.phases_worsened} worsened. The
            trade-off is a small precision dip (
            {pct(Math.abs(cEff.delta_precision))}) and {pct(cEff.delta_fpr)}{" "}
            more false positives. Restricting retrieval to incident runbooks
            alone (top-1) still beats LLM-only but trails the source-balanced
            top-{c.top_k} knowledge base.
          </div>
          <div className="kv" style={{ marginTop: 16 }}>
            <span>
              <b>{c.model}</b> via Claude API
            </span>
            <span>·</span>
            <span>
              <b>{c.n_alerts.toLocaleString()}</b> alerts scored
            </span>
            <span>·</span>
            <span>
              <b>{c.kb_document_count.toLocaleString()}</b>-doc KB
            </span>
          </div>
        </div>
      </div>

      <div className="section-label">Where RAG changed the outcome</div>
      <div className="card">
        <PhaseChart phases={cPhases} />
        <p style={{ fontSize: 13, color: "#898781", marginTop: 8 }}>
          ▲ marks a phase where retrieval improved recall. Eight of ten phases
          improved; none regressed. The biggest gains are on webshell,
          cracking, and dnsteal — phases the LLM-only pipeline almost entirely
          missed.
        </p>
      </div>

      <div className="section-label">
        Earlier local run — {ov.config.model} on {ov.config.n_alerts} alerts
        (Ollama)
      </div>
      <p className="subtitle">
        Kept as a progress record: the first version of this experiment ran
        fully locally on {ov.config.n_alerts} test alerts with{" "}
        <b>{ov.config.model}</b> via Ollama. With the smaller model the
        finding flips: retrieval made it more cautious, not more capable.
      </p>
      <div className="grid cols-2">
        <div className="card">
          <table className="cmp">
            <thead>
              <tr>
                <th>Metric</th>
                <th>
                  <span className="swatch" style={{ background: PALETTE.llmOnly }} />
                  LLM-only
                </th>
                <th>
                  <span className="swatch" style={{ background: PALETTE.llmRag }} />
                  LLM + RAG
                </th>
              </tr>
            </thead>
            <tbody>
              {localRows.map((r) => {
                const [aw, bw] = best(r.a, r.b, r.hb);
                return (
                  <tr key={r.k}>
                    <td>{r.k}</td>
                    <td className={aw ? "best" : ""}>{pct(r.a)}</td>
                    <td className={bw ? "best" : ""}>{pct(r.b)}</td>
                  </tr>
                );
              })}
              <tr>
                <td>Mean latency / alert</td>
                <td className="best">{secs(A.mean_latency_ms)}</td>
                <td>{secs(B.mean_latency_ms)}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="card">
          <div className="callout">
            Locally, RAG made the model <b>more precise but less capable</b> —
            precision rose to {pct(B.precision)} and false positives fell by{" "}
            {pct(Math.abs(eff.delta_fpr))}, but{" "}
            <b>recall dropped {pct(Math.abs(eff.delta_recall))}</b> and F1
            fell, because the retrieved context led the smaller model to
            dismiss some genuine attack steps. Retrieval improved{" "}
            {eff.phases_improved} attack phases and worsened{" "}
            {eff.phases_worsened}. Explore individual alerts from this run in
            the Triage Explorer.
          </div>
          <div className="kv" style={{ marginTop: 16 }}>
            <span>
              <b>{ov.story_counts.rag_fixed}</b> alerts RAG fixed
            </span>
            <span>·</span>
            <span>
              <b>{ov.story_counts.rag_broke}</b> alerts RAG broke
            </span>
            <span>·</span>
            <span>
              <b>{ov.story_counts.both_correct}</b> both correct
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

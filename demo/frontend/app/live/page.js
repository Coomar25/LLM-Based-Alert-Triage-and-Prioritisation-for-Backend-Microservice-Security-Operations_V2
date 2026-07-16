"use client";

import { useEffect, useRef, useState } from "react";
import {
  getLiveHealth,
  getLiveSamples,
  runLive,
  pct,
  secs,
  PALETTE,
} from "@/lib/api";

const PIPES = [
  { key: "baseline", title: "Rule-based (B1)", color: "#6b6a66", tag: "severity ≥ 2 → attack" },
  { key: "llm_only", title: "LLM-only", color: PALETTE.llmOnly, tag: "model, no context" },
  { key: "llm_rag", title: "LLM + RAG", color: PALETTE.llmRag, tag: "model + KB context" },
];

const SRC_COLOR = { runbook: "#4a3aa7", mitre: "#eb6834", cve: "#52514e", unknown: "#898781" };
const SRC_LABEL = { runbook: "RUNBOOK", mitre: "MITRE ATT&CK", cve: "CVE" };

const blank = () =>
  Object.fromEntries(PIPES.map((p) => [p.key, { status: "idle" }]));

function Doc({ d }) {
  const color = SRC_COLOR[d.source] || SRC_COLOR.unknown;
  return (
    <div className="doc">
      <div className="dhead">
        <span className="srctag" style={{ background: color }}>
          {SRC_LABEL[d.source] || d.source}
        </span>
        <span className="dtitle">
          {[d.ident, d.title].filter(Boolean).join(" · ") || "(untitled)"}
        </span>
        {d.similarity != null && (
          <span className="simbar" title={`similarity ${d.similarity}`}>
            <i style={{ width: `${Math.round(d.similarity * 100)}%` }} />
          </span>
        )}
      </div>
      {d.text && <div className="dtext">{d.text}</div>}
    </div>
  );
}

function PipeCard({ pipe, state, gt, tick }) {
  const s = state.status;
  const r = state.result;
  const elapsed =
    s === "running" && state.startedAt
      ? ((tick - state.startedAt) / 1000).toFixed(1) + "s"
      : null;

  let headRight = null;
  if (s === "idle") headRight = <span className="lp-muted">idle</span>;
  else if (s === "queued") headRight = <span className="lp-muted">queued…</span>;
  else if (s === "running")
    headRight = (
      <span className="lp-run">
        <span className="spin" /> {elapsed}
      </span>
    );
  else if (s === "done" && r)
    headRight =
      r.correct == null ? (
        <span className="result-flag ok">done</span>
      ) : (
        <span className={"result-flag " + (r.correct ? "ok" : "no")}>
          {r.correct ? "✓ correct" : "✗ wrong"}
        </span>
      );

  return (
    <div className="verdict" style={{ opacity: s === "idle" ? 0.55 : 1 }}>
      <div className="head" style={{ background: pipe.color }}>
        <span>
          {pipe.title}
          <span className="lp-tag">{pipe.tag}</span>
        </span>
        {headRight}
      </div>
      <div className="body">
        {s === "idle" && <div className="lp-muted">Not selected / not run yet.</div>}
        {(s === "queued" || (s === "running" && !r)) && (
          <div className="lp-status">
            {state.statusMsg || "Waiting for the model…"}
          </div>
        )}

        {state.retrieved && (
          <div style={{ marginBottom: r ? 14 : 0 }}>
            <div className="lp-sub">
              retrieved {state.retrieved.length} KB entries ·{" "}
              {secs(state.retrieval_ms)}
            </div>
            {state.retrieved.map((d, i) => (
              <Doc key={i} d={d} />
            ))}
          </div>
        )}

        {r && (
          <>
            <span
              className={"badge " + (r.predicted_is_attack ? "attack" : "benign")}
            >
              {r.predicted_is_attack ? "⚠ ATTACK" : "✓ benign"}
            </span>
            <div className="kv">
              {r.predicted_attack_phase && (
                <span>
                  phase: <b>{r.predicted_attack_phase}</b>
                </span>
              )}
              {r.confidence != null && (
                <span>
                  confidence: <b>{pct(r.confidence)}</b>
                </span>
              )}
              <span>
                latency: <b>{secs(r.latency_ms)}</b>
              </span>
            </div>
            {r.explanation && <div className="explain">“{r.explanation}”</div>}
          </>
        )}
      </div>
    </div>
  );
}

export default function LivePage() {
  const [health, setHealth] = useState(null);
  const [samples, setSamples] = useState([]);
  const [mode, setMode] = useState("dataset");
  const [selId, setSelId] = useState("");
  const [pasted, setPasted] = useState("");
  const [sel, setSel] = useState({ baseline: true, llm_only: true, llm_rag: true });
  const [model, setModel] = useState("llama3.2:3b");
  const [pipes, setPipes] = useState(blank());
  const [gt, setGt] = useState(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState(null);
  const [tick, setTick] = useState(Date.now());
  const abortRef = useRef(null);

  useEffect(() => {
    getLiveHealth().then(setHealth).catch((e) => setErr(String(e)));
    getLiveSamples()
      .then((s) => {
        setSamples(s);
        const firstAttack = s.find((a) => a.is_attack) || s[0];
        if (firstAttack) setSelId(firstAttack.alert_id);
      })
      .catch(() => {});
  }, []);

  // Live elapsed-time ticker while a run is in progress.
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setTick(Date.now()), 100);
    return () => clearInterval(id);
  }, [running]);

  useEffect(() => {
    if (health?.models?.length && !health.models.includes(model)) {
      setModel(health.default_model || health.models[0]);
    }
  }, [health]); // eslint-disable-line

  const pipelines = PIPES.filter((p) => sel[p.key]).map((p) => p.key);

  async function run() {
    setErr(null);
    setGt(null);
    // reset selected pipes to queued, unselected to idle
    const init = blank();
    pipelines.forEach((k) => (init[k] = { status: "queued" }));
    setPipes(init);
    setRunning(true);

    let payload = { pipelines, model };
    if (mode === "dataset") {
      payload.alert_id = selId;
    } else {
      try {
        payload.alert = JSON.parse(pasted);
      } catch {
        setErr("Pasted alert is not valid JSON.");
        setRunning(false);
        return;
      }
    }

    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await runLive(
        payload,
        (evt) => {
          setPipes((prev) => {
            const next = { ...prev };
            if (evt.type === "pipeline_start")
              next[evt.pipeline] = { status: "running", startedAt: Date.now() };
            else if (evt.type === "status")
              next[evt.pipeline] = {
                ...next[evt.pipeline],
                status: "running",
                statusMsg: evt.message,
              };
            else if (evt.type === "retrieval")
              next[evt.pipeline] = {
                ...next[evt.pipeline],
                retrieved: evt.docs,
                retrieval_ms: evt.retrieval_ms,
              };
            else if (evt.type === "result")
              next[evt.pipeline] = {
                ...next[evt.pipeline],
                status: "done",
                result: evt.result,
              };
            return next;
          });
          if (evt.type === "start") setGt(evt.ground_truth);
          if (evt.type === "error") setErr(evt.message);
        },
        ac.signal
      );
    } catch (e) {
      if (e.name !== "AbortError") setErr(String(e));
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
    setRunning(false);
  }

  const ollamaOk = health?.ollama;
  const selSample = samples.find((s) => s.alert_id === selId);

  return (
    <div className="page wide">
      <h1 className="title">Live Run</h1>
      <p className="subtitle">
        Submit an alert and watch all three pipelines classify it{" "}
        <b>in realtime</b> — the backend calls the real rule-based, LLM-only and
        LLM+RAG code and streams each result back as it finishes. Nothing here is
        cached.
      </p>

      {/* health banner */}
      <div
        className={"lp-banner " + (ollamaOk ? "ok" : "bad")}
        style={{ marginBottom: 20 }}
      >
        {ollamaOk ? (
          <>
            <b>● Ollama connected.</b> Models: {health.models.join(", ")}. KB:{" "}
            {health.kb_present ? "loaded" : "missing"}.
          </>
        ) : (
          <>
            <b>● Ollama not reachable.</b> Start it with{" "}
            <code>ollama serve</code> and pull a model (
            <code>ollama pull llama3.2:3b</code>), then reload.{" "}
            {health?.error && <span>({health.error})</span>}
          </>
        )}
      </div>

      <div className="lp-grid">
        {/* -------- controls -------- */}
        <div className="card">
          <div className="section-label" style={{ marginTop: 0 }}>
            1 · Choose an alert
          </div>
          <div className="lp-tabs">
            <button
              className={"chip" + (mode === "dataset" ? " on" : "")}
              onClick={() => setMode("dataset")}
            >
              From dataset
            </button>
            <button
              className={"chip" + (mode === "paste" ? " on" : "")}
              onClick={() => setMode("paste")}
            >
              Paste JSON
            </button>
          </div>

          {mode === "dataset" ? (
            <>
              <select
                className="lp-select"
                value={selId}
                onChange={(e) => setSelId(e.target.value)}
              >
                {samples.map((s) => (
                  <option key={s.alert_id} value={s.alert_id}>
                    {(s.is_attack ? "⚠ " : "○ ") +
                      (s.description || "(no description)").slice(0, 48) +
                      " · " +
                      s.scenario}
                  </option>
                ))}
              </select>
              {selSample && (
                <div className="lp-sub" style={{ marginTop: 8 }}>
                  ground truth:{" "}
                  <b style={{ color: selSample.is_attack ? PALETTE.bad : PALETTE.good }}>
                    {selSample.is_attack
                      ? `attack · ${selSample.attack_phase}`
                      : "benign"}
                  </b>{" "}
                  · {selSample.log_source}
                </div>
              )}
            </>
          ) : (
            <textarea
              className="lp-textarea"
              placeholder='{"description": "...", "severity_norm": 3, "rule_groups": [...], "raw_message": "..."}'
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
            />
          )}

          <div className="section-label">2 · Pipelines</div>
          <div className="lp-checks">
            {PIPES.map((p) => (
              <label key={p.key} className="lp-check">
                <input
                  type="checkbox"
                  checked={!!sel[p.key]}
                  onChange={(e) =>
                    setSel((v) => ({ ...v, [p.key]: e.target.checked }))
                  }
                />
                <span className="swatch" style={{ background: p.color }} />
                {p.title}
              </label>
            ))}
          </div>

          <div className="section-label">3 · Model</div>
          <select
            className="lp-select"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            {(health?.models || ["llama3.2:3b"]).map((m) => (
              <option key={m} value={m}>
                {m}
                {m === "llama3.2:3b" ? " (fast — recommended)" : ""}
              </option>
            ))}
          </select>

          <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
            {!running ? (
              <button
                className="lp-run-btn"
                disabled={!ollamaOk || !pipelines.length}
                onClick={run}
              >
                ▶ Run triage
              </button>
            ) : (
              <button className="lp-stop-btn" onClick={stop}>
                ■ Stop
              </button>
            )}
          </div>
          {err && <div className="lp-err">{err}</div>}
          <div className="lp-sub" style={{ marginTop: 14 }}>
            Tip: LLM-only and LLM+RAG each take several seconds on{" "}
            {model.includes("8b") ? "the 8B model" : "the 3B model"}; the
            baseline is instant. Results stream in as each finishes.
          </div>
        </div>

        {/* -------- results -------- */}
        <div>
          {gt && (
            <div className="lp-gt">
              Ground truth for this alert:{" "}
              <b style={{ color: gt.is_attack ? PALETTE.bad : PALETTE.good }}>
                {gt.is_attack ? `ATTACK · ${gt.attack_phase}` : "benign"}
              </b>
            </div>
          )}
          <div className="lp-results">
            {PIPES.filter((p) => sel[p.key] || pipes[p.key].status !== "idle").map(
              (p) => (
                <PipeCard
                  key={p.key}
                  pipe={p}
                  state={pipes[p.key]}
                  gt={gt}
                  tick={tick}
                />
              )
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

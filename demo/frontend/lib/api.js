// Central place for the backend base URL. Override with NEXT_PUBLIC_API_BASE.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8077";

async function getJSON(path) {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const getOverview = () => getJSON("/api/overview");
export const getPhases = () => getJSON("/api/phases");

// Triage datasets: "claude_3500" (headline Claude API run) or "local_129"
// (historical Ollama run). Omitting dataset keeps the backend default.
const ds = (dataset) => (dataset ? `?dataset=${dataset}` : "");
export const getAlerts = (dataset) => getJSON(`/api/alerts${ds(dataset)}`);
export const getAlert = (id, dataset) =>
  getJSON(`/api/alerts/${id}${ds(dataset)}`);

// --- Live inference ---------------------------------------------------------
export const getLiveHealth = () => getJSON("/api/live/health");
export const getLiveSamples = () => getJSON("/api/live/samples");

// Stream a live run over SSE-via-fetch (POST body means EventSource can't be
// used). Calls onEvent(evt) for each parsed `data:` event.
export async function runLive(payload, onEvent, signal) {
  const res = await fetch(`${API_BASE}/api/live/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`live/run -> ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop();
    for (const part of parts) {
      const line = part.trim();
      if (line.startsWith("data: ")) {
        try {
          onEvent(JSON.parse(line.slice(6)));
        } catch {
          /* ignore malformed chunk */
        }
      }
    }
  }
}

// Shared display helpers -----------------------------------------------------

export const PALETTE = {
  llmOnly: "#2a78d6", // categorical slot 1 (blue)
  llmRag: "#1baf7a", // categorical slot 2 (aqua)
  good: "#0ca30c",
  bad: "#d03b3b",
};

export const pct = (x) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);
export const secs = (ms) => (ms == null ? "—" : `${(ms / 1000).toFixed(1)}s`);

export const TAG_META = {
  both_correct: { label: "Both correct", color: "#0ca30c" },
  rag_fixed: { label: "RAG fixed it", color: "#2a78d6" },
  rag_broke: { label: "RAG broke it", color: "#d03b3b" },
  both_wrong: { label: "Both wrong", color: "#898781" },
};

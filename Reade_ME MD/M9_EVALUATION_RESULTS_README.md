# Evaluation & Results — Stage 6 of the AIT-ADS Pipeline

This document is the complete reference for **Stage 6**: the multi-way comparison
of all triage approaches, the figures, and the empirical findings. It brings
together the outputs of every prior stage into the dissertation's headline
result.

```
Stage 1: ingest.py                ── parse raw logs into unified schema        [DONE]
Stage 2: label_alerts.py          ── apply ground-truth attack labels          [DONE]
Stage 3: run_baseline.py          ── rule-based baseline + evaluation harness  [DONE]
Stage 4: build_knowledge_base.py  ── RAG knowledge base construction           [DONE]
Stage 5a: run_llm_only.py         ── LLM-only triage                           [DONE]
Stage 5b: run_llm_rag.py          ── LLM+RAG triage (+ runbook-only ablation)  [DONE]
Stage 6:  compare_pipelines.py    ── multi-way comparison + findings           [YOU ARE HERE]
```

This is the stage where the dissertation's contribution is established. It takes
the `results.json` files from four approaches, computes their differences, and
produces the tables and figures that answer the research question.

---

## Table of Contents

1. [Purpose and Research Role](#1-purpose-and-research-role)
2. [What Is Being Compared](#2-what-is-being-compared)
3. [The Comparison Tool](#3-the-comparison-tool)
4. [How to Run It](#4-how-to-run-it)
5. [The Complete Four-Way Result](#5-the-complete-four-way-result)
6. [The Central Finding: the Operating-Point Story](#6-the-central-finding-the-operating-point-story)
7. [The RAG Effect](#7-the-rag-effect)
8. [Per-Phase Analysis](#8-per-phase-analysis)
9. [Retrieval-Configuration Ablation](#9-retrieval-configuration-ablation)
10. [The Rules/LLM Complementarity Nuance](#10-the-rulesllm-complementarity-nuance)
11. [The Figures](#11-the-figures)
12. [Threats to Validity and Limitations](#12-threats-to-validity-and-limitations)
13. [Future Work](#13-future-work)

---

## 1. Purpose and Research Role

Every prior stage produced results in isolation. This stage's job is to compare
them rigorously and extract the finding. The research question — *does retrieval
augmentation improve LLM-based alert triage, and how does the whole approach
compare to conventional rule-based methods?* — is answered here.

The comparison must be fair: all approaches evaluated on identical alerts, scored
by the identical harness. This stage enforces both and produces the artifacts
(tables, figures) the dissertation reports.

---

## 2. What Is Being Compared

Four approaches, all evaluated on the **same 3,500-alert stratified test sample**,
all scored through the same evaluation harness (`baselines/evaluation.py`):

1. **Rule-based** (B1 and B2) — conventional SIEM-style triage.
2. **LLM-only** — Claude Haiku 4.5 reasoning over each alert with no retrieval.
3. **LLM+RAG (source-balanced)** — the same model with source-balanced retrieval
   (best runbook + best MITRE + CVEs, top-3).
4. **LLM+RAG (runbook-only)** — the same model retrieving only from the curated
   runbook corpus (top-1) — a retrieval-source ablation.

Using an identical sample across all four is what makes the comparison
defensible: no approach is advantaged by seeing different data.

---

## 3. The Comparison Tool

`ait_parser/compare_pipelines.py` reads the `results.json` files from the
approaches and produces:

- **Overall metrics** side by side (precision, recall, F1, FPR).
- **Per-phase recall** for each approach, with the delta between LLM-only and
  LLM+RAG.
- **A RAG-effect summary**: the change in each metric, and a count of how many
  phases improved versus worsened.

It writes a `comparison.json` capturing all of this. Because every input
`results.json` came from the shared harness, the tool can combine them uniformly.

---

## 4. How to Run It

From the project root, after all four approaches have been run on the 3,500
sample:

```bash
# Rule-based on the same sample (near-instant)
python3 ait_parser/run_baseline.py \
    --input data/processed/sample_3500.jsonl \
    --output results/baselines_3500

# The three LLM runs (see the LLM READMEs) produce:
#   results/llm_only_claude_3500/results.json
#   results/llm_rag_claude_3500/results.json
#   results/llm_rag_claude_3500_runbook/results.json

# Two-way LLM comparison
python3 ait_parser/compare_pipelines.py \
    --llm-only results/llm_only_claude_3500/results.json \
    --llm-rag  results/llm_rag_claude_3500/results.json \
    --output   results/comparison_claude_3500
```

The rule-based results (`b1_results.json`, `b2_results.json`) are then read
alongside the LLM results to assemble the full four-way table and the figures.

---

## 5. The Complete Four-Way Result

All figures on the identical 3,500-alert sample.

```
                          Precision   Recall    F1      FPR
Rule-based B1               0.748     0.846   0.794   0.713
Rule-based B2               0.733     0.941   0.824   0.859
LLM-only                    0.954     0.470   0.630   0.057
LLM+RAG (source-balanced)   0.936     0.528   0.675   0.091
LLM+RAG (runbook-only)      0.918     0.499   0.646   0.111
```

Two families of approach, in two regions of the metric space:

- **Rule-based:** high recall (0.85–0.94), catastrophic false-positive rate
  (0.71–0.86).
- **LLM-based:** high precision (0.92–0.95), low false-positive rate
  (0.06–0.11), moderate recall (0.47–0.53).

---

## 6. The Central Finding: the Operating-Point Story

The dissertation's headline is **not** "the LLM has the highest F1" — it does
not (B2's F1 of 0.824 is highest). The finding is about the **operating point**.

Rule-based methods reach high recall only by flagging most of the benign traffic
as malicious — false-positive rates of 71–86%. That is the alert-fatigue problem
the dissertation is motivated by, recreated by the very tools meant to solve it.
An analyst using B2 would face an 86% false-positive rate: essentially unusable.

The LLM approaches operate at a fundamentally different point: ~95% precision with
a ~6% false-positive rate for LLM-only. When they flag an alert, it is almost
always a real attack. RAG then recovers a meaningful share of the recall gap
(+5.8 points) while holding the false-positive rate to ~9% — still an order of
magnitude below the rule-based baselines.

**Framing:** the LLM+RAG system is not merely "better on a metric." It occupies
the *deployable* region of precision-recall space — the region with an
analyst-usable false-positive rate — that the rule-based baselines cannot reach.
For the alert-fatigue problem, that false-positive rate is the binding
constraint. This is captured visually in Figure 4 (the precision-recall
trade-off plot).

---

## 7. The RAG Effect

Comparing LLM+RAG (source-balanced) against LLM-only, on identical alerts:

```
delta_recall:    +0.058   (0.470 → 0.528)
delta_f1:        +0.046   (0.630 → 0.675)
delta_precision: -0.018   (0.954 → 0.936)
delta_fpr:       +0.034   (0.057 → 0.091)
phases_improved: 8
phases_worsened: 0
```

**Eight phases improved, zero worsened** (two unchanged — wpscan and service_stop,
both already at ceiling). No phase got worse under RAG. On a clean, full-scale
run this is a robust, consistent directional result: retrieval helps across the
board where there is room to help, and never hurts.

---

## 8. Per-Phase Analysis

The per-phase recall reveals *where* and *why* RAG helps.

| Phase | LLM-only | LLM+RAG (balanced) | Interpretation |
|---|---|---|---|
| wpscan | 1.000 | 1.000 | Self-evident in raw log; no context needed |
| dirb | 0.981 | 0.986 | Self-evident; unchanged |
| service_scans | 0.576 | 0.597 | Small lift |
| service_stop | 0.571 | 0.571 | Unchanged (n=7, indicative) |
| privilege_escalation | 0.320 | 0.328 | Small lift |
| reverse_shell | 0.258 | 0.288 | Modest lift |
| **webshell** | 0.118 | **0.279** | Large lift (×2.4) |
| **cracking** | 0.019 | **0.175** | Large lift (×9) |
| **dnsteal** | 0.011 | **0.147** | Large lift (×13) |
| **network_scans** | 0.010 | **0.072** | Large lift (×7) |

The pattern is bimodal and interpretable:

- **Text-self-evident attacks** (wpscan, dirb) — the LLM already handles these
  from the raw log alone; retrieval neither helps nor hurts.
- **Knowledge-dependent attacks** (cracking, dnsteal, network_scans, webshell) —
  the LLM-only baseline was near-blind to these because recognising them requires
  knowing what the pattern *means* (repeated auth failures = brute force,
  anomalous DNS = exfiltration). Retrieval supplies exactly that knowledge, and
  recall rises multiplicatively.

This is the mechanism the dissertation predicted: RAG delivers its value
precisely on the attacks that require external security knowledge, and nowhere
else. Figure 1 shows this at a glance; Figure 3 shows the recall lift per phase.

---

## 9. Retrieval-Configuration Ablation

Comparing the two RAG configurations isolates the effect of retrieval breadth:

```
                          Precision   Recall    F1      FPR
LLM+RAG (source-balanced)   0.936     0.528   0.675   0.091
LLM+RAG (runbook-only)      0.918     0.499   0.646   0.111
```

Source-balanced beats runbook-only on **recall, F1, and precision** simultaneously.
So restricting retrieval to the 8 curated runbooks alone captures only part of the
benefit — the broader knowledge base (MITRE techniques and CVE context alongside
the runbooks) does real additional work. **Retrieval diversity matters.**

Note also the FPR gradient: runbook-only has the *highest* FPR (0.111) yet lower
recall than source-balanced — so it is not simply "more retrieval = more
flagging." The broader context helps the model flag the *right* things, achieving
both higher recall and higher precision than the runbook-only variant.

---

## 10. The Rules/LLM Complementarity Nuance

An important observation from the four-way comparison: the rule-based B2 catches
the knowledge-dependent phases (cracking 0.878, dnsteal 0.847, network_scans
0.979) that the LLM struggles with — because its burst-correlation rule fires on
exactly those high-volume patterns.

This means rules and LLMs have **complementary strengths**:

- **Rules** excel at high-volume, burst-shaped attacks (scanning, brute-force,
  exfiltration) but are blind to context and drown the analyst in false
  positives.
- **The LLM** is precise and context-aware but misses volume-based patterns
  without external help.

This suggests a **hybrid architecture** — rules for high-volume burst detection,
LLM+RAG for precise, context-aware triage of everything else — as a natural and
well-motivated direction for future work. Naming this complementarity is itself a
contribution: it shows the two paradigms are not simply competitors but
potentially cooperative.

---

## 11. The Figures

Five figures were generated from the clean results (all n=3,500):

- **Figure 1 — Per-phase recall by approach.** Three bars per phase (LLM-only,
  runbook-only, source-balanced), with a divider separating text-self-evident
  phases from knowledge-dependent ones. The centrepiece: it shows RAG's targeted
  lift.
- **Figure 2 — Overall metrics (LLM approaches).** Precision, recall, F1, FPR
  across the three LLM configurations.
- **Figure 3 — RAG recall lift by phase.** The delta (source-balanced minus
  LLM-only) per phase, making the "large gains on knowledge-dependent attacks,
  near-zero elsewhere" pattern unmissable.
- **Figure 4 — Precision-recall trade-off (the key figure).** A scatter of all
  five approaches in precision-recall space, annotated with FPR, with the
  "analyst-usable" and "alert-fatigue" regions shaded. This single figure carries
  the operating-point argument.
- **Figure 5 — Four-way overall metrics.** All five approaches across all four
  metrics.

Files: `fig1_per_phase_recall.png` … `fig5_fourway_metrics.png`.

**Caption note:** in the metric bar charts, FPR is "lower is better" while the
other three metrics are "higher is better" — worth stating in each caption so a
short FPR bar is not misread as poor performance.

---

## 12. Threats to Validity and Limitations

For the dissertation's limitations section.

- **Synthetic dataset.** AIT-ADS is a simulated environment; real-world alert
  streams differ in format, volume, and noise. Results may not transfer directly
  to production without revalidation.
- **Sample size and rare phases.** The evaluation uses a 3,500-alert stratified
  sample. Rare phases (service_stop n=7, reverse_shell n=66, webshell n=68) have
  small counts; their per-phase figures are indicative rather than precise.
- **Model family across backends.** The full-scale results use Claude Haiku 4.5;
  the resource-constrained validation used local Llama 8B. The RAG ablation is
  valid within each backend (both arms use the same model), but absolute numbers
  are model-dependent. The two are framed as deployment modes (hosted at scale
  vs on-prem constrained).
- **Cost and latency.** Hosted LLM inference is paid and slower per alert than
  rule evaluation. This is a real deployment consideration and is disclosed with
  concrete figures.
- **Single-alert context.** All triage is per-alert; multi-alert attack patterns
  are invisible to the LLM approaches (shared with the baselines for fairness),
  which caps achievable recall on volume-based phases.
- **Single-shot retrieval.** One retrieval per alert; no iterative/agentic
  retrieval was explored.
- **No cross-validation over scenarios.** A single scenario-level split was used;
  rotating the test scenarios (cross-validation) is out of scope but would
  strengthen confidence.

---

## 13. Future Work

- **Hybrid rules + LLM+RAG** (Section 10) — combine the burst-detection strength
  of rules with the precision of LLM+RAG.
- **Multi-alert context** — aggregate related alerts (same source, same window)
  into a single triage unit so volume-based attacks become visible to the LLM.
- **Improved retrieval** — hybrid semantic + keyword (BM25) retrieval, and
  retrieve-then-rerank with a cross-encoder, to further raise retrieval relevance.
- **Cross-validation over scenarios** — rotate the held-out scenarios for a more
  robust estimate.
- **Live-data demonstration** — apply the pipeline to freshly generated,
  AIT-ADS-compatible alerts from a live instrumented backend, directly addressing
  the synthetic-dataset limitation.
- **Faithfulness metrics for explanations** — automated evaluation of the
  quality/supportedness of the model's explanations (RAGAS-style), replacing the
  originally-planned expert evaluation.

---

*Stage 6 (Milestone 9) of the dissertation pipeline. Combines all prior stages
into the four-way comparison and the dissertation's headline finding. Author:
Kumar Chaudhary (2562392), MRes Cybersecurity, University of Wolverhampton.*

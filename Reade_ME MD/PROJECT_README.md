# LLM-Based Intelligent Alert Triage and Prioritisation for Backend Microservice Security Operations

**MRes Cybersecurity Dissertation — University of Wolverhampton**
**Author: Kumar Chaudhary (Student ID 2562392)**

This repository implements and evaluates a retrieval-augmented, LLM-based system
for triaging security alerts, compared against conventional rule-based methods.
It is built and evaluated on the AIT Alert Data Set (AIT-ADS).

---

## The Research Question

Security Operations Centres are overwhelmed by alert volume, and conventional
rule-based triage achieves high recall only at false-positive rates that recreate
the very alert fatigue they are meant to solve. This project asks:

> **Can a Large Language Model, augmented with retrieved security knowledge
> (RAG), triage alerts at an operationally usable false-positive rate — and does
> retrieval measurably improve on the LLM alone?**

The answer, established on a clean full-scale evaluation: **yes.** LLM approaches
operate at ~95% precision and ~6% false-positive rate (versus 71–86% for
rule-based methods), and retrieval augmentation improves recall by +5.8 points,
concentrated precisely on the attack types that require external security
knowledge.

---

## The Pipeline at a Glance

The project is a sequence of stages, each documented in its own README.

```
Stage 1  Ingestion & Parsing        raw Wazuh/Suricata/AMiner logs → unified schema
         → PARSER_README.md                        (2,655,821 alerts, zero loss)

Stage 2  Labelling                  apply AIT-ADS ground-truth attack labels
         → LABELLING_README.md                     (1,764,581 attack, 66.4%)

Stage 3  Rule-Based Baseline        B1 + B2 + the shared evaluation harness
         → BASELINE_README.md                      (B2: F1 0.824, FPR 0.859)

Stage 4  Knowledge Base             MITRE + CVE + runbooks → ChromaDB
         → KNOWLEDGE_BASE_README.md                (37,545 documents)

Stage 5a LLM-Only Pipeline          LLM triage, no retrieval (ablation baseline)
         → LLM_ONLY_README.md                      (precision 0.954, recall 0.470)

Stage 5b LLM+RAG Pipeline           LLM triage + source-balanced retrieval
         → LLM_RAG_README.md                       (precision 0.936, recall 0.528)

Stage 6  Evaluation & Results       four-way comparison + figures + findings
         → EVALUATION_RESULTS_README.md            (8 phases improved, 0 worsened)
```

---

## Milestone Status

| Milestone | Description | Status |
|---|---|---|
| M1 | Literature review | Complete |
| M2 | Proposal + ethics approval | Complete |
| M3 | Dataset selection (AIT-ADS) | Complete |
| M4 | Parser / ingestion | Complete → PARSER_README.md |
| M5 | Ground-truth labelling | Complete → LABELLING_README.md |
| M6 | Rule-based baseline | Complete → BASELINE_README.md |
| M7 | Knowledge base | Complete → KNOWLEDGE_BASE_README.md |
| M8 | LLM pipelines (only + RAG) | Complete → LLM_ONLY_README.md, LLM_RAG_README.md |
| M9 | Evaluation & results | Complete → EVALUATION_RESULTS_README.md |
| M10 | Dissertation write-up | In progress |

---

## The Headline Result

All approaches evaluated on the **same 3,500-alert stratified test sample**,
scored by the same harness.

```
                          Precision   Recall    F1      FPR
Rule-based B1               0.748     0.846   0.794   0.713
Rule-based B2               0.733     0.941   0.824   0.859
LLM-only                    0.954     0.470   0.630   0.057
LLM+RAG (source-balanced)   0.936     0.528   0.675   0.091
LLM+RAG (runbook-only)      0.918     0.499   0.646   0.111
```

Three layers of finding:

1. **Operating point.** Rule-based methods reach high recall only at unusable
   false-positive rates (alert fatigue). LLM+RAG occupies the deployable region —
   high precision, low FPR — that rules cannot reach.
2. **RAG works.** Retrieval improves recall (+5.8 pts) and F1 (+4.5 pts) over the
   LLM alone; 8 phases improved, 0 worsened. The gains concentrate on
   knowledge-dependent attacks (cracking ×9, dnsteal ×13, network_scans ×7).
3. **Retrieval diversity matters.** Source-balanced retrieval (runbooks + MITRE +
   CVEs) beats retrieving from the curated runbooks alone.

---

## Key Design Principles

These run through the whole codebase and are worth understanding up front.

- **One shared evaluation harness.** `baselines/evaluation.py` scores every
  approach, so metrics are defined identically everywhere.
- **One scenario-level split.** `baselines/splits.py` defines train/test once;
  the sampler and every pipeline respect it. No episode leaks across the
  boundary.
- **Clean ablation.** The LLM-only and LLM+RAG prompts are character-identical
  except for the retrieved-context block (enforced by a unit test), so any
  difference is attributable to retrieval.
- **No ground-truth leakage in retrieval.** Retrieval queries use only observable
  alert content, never the known label.
- **Infrastructure failures are excluded, not faked.** The `infra_error` flag
  distinguishes "no answer" (excluded from scoring) from "answered X" — without
  which rate-limited runs silently corrupt the metrics.
- **Same sample across approaches.** The final comparison runs all approaches on
  the identical 3,500-alert sample.

---

## Repository Structure

```
code_work/
├── ait_parser/                 the main Python package
│   ├── ingest.py               Stage 1
│   ├── label_alerts.py         Stage 2
│   ├── run_baseline.py         Stage 3
│   ├── build_knowledge_base.py Stage 4
│   ├── run_llm_only.py         Stage 5a
│   ├── run_llm_rag.py          Stage 5b
│   ├── compare_pipelines.py    Stage 6
│   ├── parsers/                per-system parsers + unified schema
│   ├── labeller/               labelling engine
│   ├── baselines/              rule logic, splits, evaluation harness
│   ├── kb/                     knowledge-base construction + retrieval store
│   └── llm/                    sampler, alert repr, prompts, retrieval, provider clients
├── data/
│   ├── raw/                    original AIT-ADS logs
│   ├── processed/              unified + labelled + sampled alerts
│   └── kb/                     built ChromaDB knowledge base
└── results/                    per-approach results.json + the comparison + figures
```

---

## Reproducing the Full Evaluation

From the project root, end to end:

```bash
# Stage 1: ingest raw logs
python3 ait_parser/ingest.py --input <raw-logs> --output data/processed/alerts_unified.jsonl

# Stage 2: label
python3 ait_parser/label_alerts.py --input data/processed/alerts_unified.jsonl \
    --output data/processed/alerts_labeled.jsonl

# Stage 3: rule-based baseline
python3 ait_parser/run_baseline.py --input data/processed/alerts_labeled.jsonl \
    --output results/baselines

# Stage 4: build the knowledge base
python3 ait_parser/build_knowledge_base.py --output data/kb

# Stage 5: draw the shared evaluation sample
python3 ait_parser/llm/sampler.py --input data/processed/alerts_labeled.jsonl \
    --output data/processed/sample_3500.jsonl --profile medium --seed 42

# Stage 5a: LLM-only
python3 ait_parser/run_llm_only.py --input data/processed/sample_3500.jsonl \
    --output results/llm_only_claude_3500 \
    --provider anthropic --model claude-haiku-4-5-20251001 --workers 2

# Stage 5b: LLM+RAG (source-balanced)
python3 ait_parser/run_llm_rag.py --input data/processed/sample_3500.jsonl \
    --output results/llm_rag_claude_3500 --kb-dir data/kb \
    --provider anthropic --model claude-haiku-4-5-20251001 --workers 2 --top-k 3

# Stage 5b: LLM+RAG (runbook-only ablation)
python3 ait_parser/run_llm_rag.py --input data/processed/sample_3500.jsonl \
    --output results/llm_rag_claude_3500_runbook --kb-dir data/kb \
    --provider anthropic --model claude-haiku-4-5-20251001 --workers 2 --top-k 1 --runbook-only

# Stage 3 on the same sample (for like-for-like)
python3 ait_parser/run_baseline.py --input data/processed/sample_3500.jsonl \
    --output results/baselines_3500

# Stage 6: compare
python3 ait_parser/compare_pipelines.py \
    --llm-only results/llm_only_claude_3500/results.json \
    --llm-rag  results/llm_rag_claude_3500/results.json \
    --output   results/comparison_claude_3500
```

---

## Environment Notes

- **Inference backend.** The pipeline supports four backends via `--provider`
  (ollama / groq / gemini / anthropic). The clean full-scale results use
  Anthropic Claude Haiku 4.5 (`--workers 2` to respect rate limits). Local Ollama
  (Llama 8B) provides a free, reliable, slower on-prem option. See LLM_RAG_README
  Section 5 and 10 for the full backend story.
- **API keys** are read from environment variables (never hard-coded). Export in
  `~/.bashrc`, outside the repo, so keys cannot be committed. A `.gitignore`
  excludes `.env`, keys, caches, and large data.
- **No GPU** was available; all local inference is CPU-based.

---

## Dataset & Citation

AIT Alert Data Set (AIT-ADS), Zenodo DOI 10.5281/zenodo.8263181, CC-BY 4.0,
described at CSET 2024 (Landauer, Skopik, Wurzenberger,
DOI 10.1145/3675741.3675748).

---

## Document Index

| README | Stage | Covers |
|---|---|---|
| PROJECT_README.md | — | This overview |
| PARSER_README.md | 1 | Ingestion, unified schema, severity normalisation |
| LABELLING_README.md | 2 | Ground-truth labelling |
| BASELINE_README.md | 3 | Rule-based B1/B2 + the shared evaluation harness |
| KNOWLEDGE_BASE_README.md | 4 | MITRE/CVE/runbook knowledge base |
| LLM_ONLY_README.md | 5a | LLM-only pipeline (ablation baseline) |
| LLM_RAG_README.md | 5b | LLM+RAG pipeline, retrieval, provider layer |
| EVALUATION_RESULTS_README.md | 6 | Four-way comparison, figures, findings |

---

*MRes Cybersecurity dissertation, University of Wolverhampton. Author: Kumar
Chaudhary (2562392).*

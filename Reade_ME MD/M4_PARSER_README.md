# Alert Ingestion & Parsing — Stage 1 of the AIT-ADS Pipeline

This document is the complete reference for **Stage 1**: parsing the raw AIT-ADS
log files from three different intrusion-detection systems into a single unified
alert schema. It covers what each parser does, why the unified schema exists, how
severity is normalised across systems, how to run the ingestion, and the results.

```
Stage 1: ingest.py                ── parse raw logs into unified schema        [YOU ARE HERE]
Stage 2: label_alerts.py          ── apply ground-truth attack labels          [DONE]
Stage 3: run_baseline.py          ── rule-based baseline + evaluation harness  [DONE]
Stage 4: build_knowledge_base.py  ── RAG knowledge base construction           [DONE]
Stage 5a/5b: LLM pipelines        ── LLM-only and LLM+RAG                       [DONE]
Stage 6:  compare_pipelines.py    ── multi-way comparison                      [DONE]
```

This is the foundation stage. Every later stage — labelling, baselines, the
knowledge base, both LLM pipelines — operates on the unified alert records this
stage produces. If ingestion loses or mangles data, everything downstream
inherits the error, so this stage prioritises completeness and fidelity above
all.

---

## Table of Contents

1. [Purpose and Research Role](#1-purpose-and-research-role)
2. [The Source Data: AIT-ADS](#2-the-source-data-ait-ads)
3. [Component Architecture](#3-component-architecture)
4. [The Unified Alert Schema](#4-the-unified-alert-schema)
5. [The Three Parsers](#5-the-three-parsers)
6. [Severity Normalisation](#6-severity-normalisation)
7. [Design Decisions](#7-design-decisions)
8. [How to Run It](#8-how-to-run-it)
9. [Outputs](#9-outputs)
10. [Results and Fidelity Guarantee](#10-results-and-fidelity-guarantee)
11. [Known Limitations](#11-known-limitations)

---

## 1. Purpose and Research Role

The dissertation evaluates alert-triage approaches on the AIT Alert Data Set
(AIT-ADS). That dataset ships as raw output from three different detection
systems, each with its own format, field names, and severity conventions. Before
any triage can happen, these heterogeneous logs must be unified into a single
consistent representation.

Stage 1 does exactly that: it reads the raw Wazuh, Suricata, and AMiner logs and
emits one uniform `UnifiedAlert` record per alert, with consistent field names, a
normalised severity scale, and all the original detail preserved. This unified
stream is what every downstream stage consumes.

The research requirement is **zero data loss with faithful representation**: the
triage results are only as trustworthy as the alerts they are computed on, so
ingestion must account for every input record and preserve the discriminative
detail (especially the raw log message, which later proves to be the single most
important field for triage).

---

## 2. The Source Data: AIT-ADS

- **Dataset:** AIT Alert Data Set (AIT-ADS), published on Zenodo
  (DOI 10.5281/zenodo.8263181), described at CSET 2024.
- **Scale:** 2,655,821 alerts across 8 attack scenarios.
- **Detection systems:** Wazuh (host-based IDS), Suricata (network IDS), and
  AMiner (log-based anomaly detection).
- **Licence:** CC-BY 4.0.

Each scenario is a simulated enterprise environment subjected to a multi-stage
attack campaign, with all three detection systems recording alerts throughout.
The scenarios provide the ground truth for what is attack and what is benign
(applied in Stage 2).

---

## 3. Component Architecture

```
ait_parser/
├── ingest.py                  ← orchestrator: read raw logs, dispatch to parsers, write unified stream
├── test_parsers.py            ← unit tests for each parser and the schema
└── parsers/
    ├── __init__.py
    ├── unified_alert.py       ← the UnifiedAlert schema (the target format)
    ├── wazuh_parser.py        ← Wazuh JSON → UnifiedAlert
    ├── suricata_parser.py     ← Suricata EVE JSON → UnifiedAlert
    ├── aminer_parser.py       ← AMiner output → UnifiedAlert
    └── severity_mapping.py    ← per-system severity → normalised scale
```

`ingest.py` walks the raw log files, routes each to the appropriate parser based
on its source system, and writes the resulting unified records to a single
JSONL stream. The parsers are independent and single-responsibility; the schema
and the severity mapping are shared.

---

## 4. The Unified Alert Schema

`parsers/unified_alert.py` defines `UnifiedAlert` — the single format every
downstream stage relies on. It brings the three systems' differing fields into
one consistent structure, including:

- **Identity:** a stable alert identifier and the source scenario.
- **Source system:** which IDS produced it (wazuh / suricata / aminer).
- **Severity:** both the original per-system severity and a normalised level
  (Section 6).
- **Rule / signature:** the human-readable description of what fired.
- **Rule groups / categories:** the taxonomy tags the IDS attached (used heavily
  by the rule-based baseline and as a retrieval signal).
- **Network context:** source and destination IP where available.
- **Log source:** the originating log file/path.
- **Raw message:** the original raw log line, preserved verbatim.
- **Timestamp:** normalised to a consistent representation.

### 4.1 Why the raw message is preserved

The raw log message turned out to be the single most important field in the whole
project. The normalised rule description is often too generic to distinguish
attack from benign (e.g. a WordPress vulnerability probe is described only as
"Web server 400 error code"), while the discriminating evidence (the requested
URL path, the tool signature) lives only in the raw message. Preserving it
verbatim at ingestion time is what later makes accurate LLM triage possible. Had
ingestion discarded or summarised it, no downstream fix could have recovered it.

---

## 5. The Three Parsers

Each parser converts one system's native format into `UnifiedAlert`.

### 5.1 Wazuh parser

Wazuh emits structured JSON alerts with a rich rule object (rule id, level,
description, groups) and decoded fields. The parser extracts the rule metadata,
the source/destination context, and the full log message, mapping the Wazuh rule
level onto the normalised severity scale.

### 5.2 Suricata parser

Suricata emits EVE JSON — network-event records with signature metadata,
five-tuple network information, and severity encoded in its own convention. The
parser extracts the signature description and category, the network five-tuple,
and normalises Suricata's severity.

### 5.3 AMiner parser

AMiner produces log-anomaly output in its own format. The parser extracts the
detector's description and the originating log context, mapping its severity
representation onto the normalised scale.

### 5.4 Why three separate parsers

The three systems share almost nothing at the format level — different field
names, different severity encodings, different notions of what an "alert" is.
Attempting a single generic parser would produce a tangle of special cases.
Three focused parsers, each converting into the shared `UnifiedAlert`, keep the
logic clear and testable, and make it straightforward to add a fourth system in
future.

---

## 6. Severity Normalisation

`parsers/severity_mapping.py` maps each system's native severity onto a single
normalised scale.

### 6.1 The problem

The three systems express severity differently: Wazuh uses rule *levels*,
Suricata uses its own severity integers, and AMiner has yet another convention. A
severity "3" from one system does not mean the same thing as a "3" from another.
Any rule or analysis that thresholds on severity (like the rule-based baseline)
would be meaningless if it compared raw per-system values.

### 6.2 The solution

Each system's severity is mapped onto a common normalised level, so that "high
severity" means the same thing regardless of which IDS produced the alert. The
original per-system severity is retained alongside the normalised value, so no
information is lost — downstream code can use whichever it needs.

### 6.3 Why this matters downstream

The rule-based baseline (Stage 3) thresholds on the normalised severity. Without
normalisation, its threshold would behave inconsistently across the three
systems and its results would be uninterpretable. Severity normalisation at
ingestion is what makes a single severity threshold a coherent baseline.

---

## 7. Design Decisions

### 7.1 One unified schema, populated by per-system parsers

**Decision.** Convert everything to a single `UnifiedAlert` at ingestion, rather
than carrying three formats downstream.

**Rationale.** Every later stage would otherwise need to handle three formats.
Unifying once, at the boundary, means all downstream code — labelling, baselines,
the LLM pipelines — works against one consistent structure.

### 7.2 Preserve the raw message verbatim

**Decision.** Store the original raw log line untouched.

**Rationale.** It is the most discriminative field, and its value only became
apparent much later (during LLM debugging). Preserving it verbatim at ingestion
kept that option open; summarising or dropping it would have been irreversible.

### 7.3 Zero data loss as a hard requirement

**Decision.** Every input record must be accounted for; the output count must
reconcile with the input.

**Rationale.** Triage metrics are only trustworthy if computed on the complete
data. Silent drops would bias every downstream result in unknown ways. Ingestion
counts inputs and outputs and verifies they match.

---

## 8. How to Run It

From the project root:

```bash
python3 ait_parser/ingest.py \
    --input <path-to-raw-AIT-ADS-logs> \
    --output data/processed/alerts_unified.jsonl
```

Unit tests (validate each parser and the schema against sample records):

```bash
cd ait_parser && python3 test_parsers.py && cd ..
```

The unified output (`alerts_unified.jsonl`) becomes the input to Stage 2
(labelling).

---

## 9. Outputs

- **`alerts_unified.jsonl`** — one `UnifiedAlert` per line, covering every alert
  across all scenarios and all three detection systems. This is the single input
  to the labelling stage.

Each record carries consistent field names, a normalised severity, and the
preserved raw message, ready for ground-truth labelling.

---

## 10. Results and Fidelity Guarantee

- **2,655,821 alerts** parsed across the 8 scenarios and 3 detection systems.
- **Zero data loss:** the output record count reconciles exactly with the input;
  every raw alert produced one unified record.
- All three severity conventions normalised onto a single scale, with the
  original values retained.
- Raw log messages preserved verbatim for every record.

This completeness is the foundation the rest of the project stands on: because
ingestion lost nothing and preserved the discriminative detail, every downstream
stage — labelling, baselines, retrieval, LLM triage — operates on faithful data.

---

## 11. Known Limitations

- **Format-specific fields.** Some system-specific fields have no natural place
  in the unified schema; where they are not needed downstream they are folded
  into the raw message rather than given dedicated columns.
- **Timestamp precision.** Timestamps are normalised to a consistent
  representation; sub-second precision conventions differ slightly between
  systems.
- **Three systems only.** The parser set covers the three IDSs present in
  AIT-ADS. Adding a fourth system requires a new parser (though the unified
  schema is designed to accommodate one).

---

*Stage 1 (Milestone 4) of the dissertation pipeline. Produces the unified alert
stream every later stage consumes. Author: Kumar Chaudhary (2562392), MRes
Cybersecurity, University of Wolverhampton.*

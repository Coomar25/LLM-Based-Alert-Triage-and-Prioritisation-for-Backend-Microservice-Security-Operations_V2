# Rule-Based Baseline & Evaluation Harness — Stage 3 of the AIT-ADS Pipeline

This document is the complete reference for **Stage 3**: the rule-based triage
baselines (B1 and B2) and the shared evaluation harness that every subsequent
pipeline reuses. It covers what each component does, why it exists, how the
baselines are defined, how to run them, and the results.

```
Stage 1: ingest.py                ── parse raw logs into unified schema        [DONE]
Stage 2: label_alerts.py          ── apply ground-truth attack labels          [DONE]
Stage 3: run_baseline.py          ── rule-based baseline + evaluation harness  [YOU ARE HERE]
Stage 4: build_knowledge_base.py  ── RAG knowledge base construction           [DONE]
Stage 5a/5b: LLM pipelines        ── LLM-only and LLM+RAG                       [DONE]
Stage 6:  compare_pipelines.py    ── multi-way comparison                      [DONE]
```

This stage serves two purposes at once:

1. **It establishes the baseline** the LLM approaches must be measured against.
   A rule-based system is what a real SOC uses today; the dissertation's claim to
   a contribution rests on how the LLM+RAG system compares to it.
2. **It builds the evaluation harness** — the confusion-matrix and metrics code —
   that is imported unchanged by the rule-based, LLM-only, and LLM+RAG pipelines.
   Building it once guarantees all approaches are scored by identical
   definitions.

---

## Table of Contents

1. [Purpose and Research Role](#1-purpose-and-research-role)
2. [Component Architecture](#2-component-architecture)
3. [The Train/Test Split](#3-the-traintest-split)
4. [The Evaluation Harness](#4-the-evaluation-harness)
5. [Baseline B1 — Severity Threshold](#5-baseline-b1--severity-threshold)
6. [Baseline B2 — Severity + Rule Groups + Burst Correlation](#6-baseline-b2--severity--rule-groups--burst-correlation)
7. [Design Decisions](#7-design-decisions)
8. [How to Run It](#8-how-to-run-it)
9. [Outputs](#9-outputs)
10. [Empirical Results](#10-empirical-results)
11. [Interpretation and Dissertation Implications](#11-interpretation-and-dissertation-implications)
12. [Known Limitations](#12-known-limitations)

---

## 1. Purpose and Research Role

Before any LLM is introduced, the dissertation needs a credible, conventional
baseline — the kind of triage a mature rule-based SIEM performs. Two baselines
are implemented, escalating in sophistication:

- **B1** — a simple severity threshold. The minimal sensible rule: flag alerts
  at or above a severity level.
- **B2** — severity threshold + known-bad rule groups + source-IP burst
  correlation. Closer to a real correlation-enabled SIEM (e.g. Wazuh with
  cross-rule correlation).

These baselines answer the question every reviewer asks: *what does the LLM
actually add over conventional methods?* The answer only means something if the
conventional method is implemented honestly and evaluated on the same data — which
is exactly what this stage provides.

---

## 2. Component Architecture

```
ait_parser/
├── run_baseline.py            ← orchestrator: load, split, evaluate, report
├── test_baselines.py          ← unit tests for the rules and the harness
└── baselines/
    ├── __init__.py
    ├── splits.py              ← the canonical train/test scenario definitions
    ├── rule_based.py          ← B1 and B2 rule logic
    └── evaluation.py          ← ConfusionMatrix + EvaluationResult (REUSED EVERYWHERE)
```

The critical module is `baselines/evaluation.py`. It is imported by
`run_baseline.py` (this stage), `run_llm_only.py` (Stage 5a), and
`run_llm_rag.py` (Stage 5b). Every approach in the dissertation is scored through
this one harness, so there is no risk of metric definitions drifting between
scripts.

`baselines/splits.py` is imported even more widely — the sampler (Stage 5) uses
it to guarantee the LLM evaluation draws only from the test scenarios.

---

## 3. The Train/Test Split

`baselines/splits.py` defines a **scenario-level** split:

- **Train scenarios:** fox, harrison, russellmitchell, shaw, wardbeck
- **Test scenarios:** wheeler, wilson, santos

### 3.1 Why scenario-level, not random

A random alert-level split would place alerts from the same attack episode on
both sides of the train/test boundary. Because alerts within an episode are
highly correlated (same attacker, same time window, same techniques), that would
leak information from train to test and inflate the measured performance. A
scenario-level split keeps entire attack episodes together: the test scenarios
are attack campaigns the approach has never seen in any form. This is the honest,
defensible way to evaluate.

### 3.2 Why this matters beyond the baseline

The split is defined once here and reused everywhere. The rule-based threshold is
tuned on train and reported on test; the LLM sampler draws only from test. Every
approach is evaluated on the same held-out scenarios, so the comparison is
apples-to-apples.

---

## 4. The Evaluation Harness

`baselines/evaluation.py` provides two classes.

### 4.1 `ConfusionMatrix`

Accumulates true positives, false positives, true negatives, and false negatives,
and derives the metrics from them:

- **Precision** = TP / (TP + FP) — of the alerts flagged as attacks, how many
  really were.
- **Recall** = TP / (TP + FN) — of the real attacks, how many were caught.
- **F1** = harmonic mean of precision and recall.
- **False-positive rate (FPR)** = FP / (FP + TN) — of the benign alerts, how many
  were wrongly flagged. **This is the alert-fatigue metric** and is central to
  the dissertation's argument.
- **Accuracy** = (TP + TN) / total.

### 4.2 `EvaluationResult`

Wraps three confusion matrices at once:

- **Overall** — the headline metrics.
- **Per-scenario** — broken down by wheeler / wilson / santos.
- **Per-phase** — broken down by attack phase (wpscan, cracking, dnsteal, …).

The per-phase breakdown is what makes the dissertation's core analysis possible:
it reveals *which kinds of attack* each approach catches or misses. `record()` is
called once per alert with the predicted label, actual label, scenario, and
attack phase; `to_dict()` serialises the whole structure to the `results.json`
format used throughout the project.

### 4.3 Why one shared harness matters

Because the rule-based, LLM-only, and LLM+RAG pipelines all call the same
`EvaluationResult`, a "precision" reported for one is computed identically to a
"precision" reported for another. There is no possibility of, say, the LLM
pipeline using a subtly different denominator. Build once, use for every
approach — this is a deliberate integrity decision.

---

## 5. Baseline B1 — Severity Threshold

### 5.1 Definition

B1 predicts **attack** if the alert's normalised severity is at or above a
threshold, and **benign** otherwise. It is a pure function of a single field.

### 5.2 Threshold tuning

The threshold is selected on the **train** split by sweeping candidate values and
choosing the one with the best train F1, then the chosen threshold is applied
unchanged to the **test** split for the reported result. This mirrors how a real
analyst would tune a severity cutoff on historical data and deploy it. The
selected threshold was severity level 2.

### 5.3 Why B1 exists

B1 is the floor — the simplest rule anyone would actually use. If the LLM cannot
beat a bare severity threshold, there is no story. It also demonstrates the core
weakness of severity-only triage: severity is a coarse signal that does not
distinguish attack from benign well, producing a high false-positive rate.

---

## 6. Baseline B2 — Severity + Rule Groups + Burst Correlation

### 6.1 Definition

B2 predicts **attack** if ANY of three conditions holds:

- **(a)** normalised severity ≥ threshold, OR
- **(b)** any of the alert's rule groups is in a known-bad set (rule categories
  that, per Wazuh's published taxonomy, indicate likely attack activity), OR
- **(c)** the alert's source IP has fired at least K alerts within a 60-second
  window (a burst-correlation rule).

Configuration used: severity threshold 2, burst count 10, burst window 60
seconds.

### 6.2 The burst detector

Condition (c) is stateful. As alerts stream through, the detector tracks a
sliding 60-second window of alert timestamps per source IP; when an IP's count in
that window reaches the burst threshold, its alerts are flagged. This is what lets
B2 catch high-volume attacks — scanning, brute-force, exfiltration — that
individually look unremarkable but collectively form an obvious burst.

### 6.3 Why B2 exists

B2 is the baseline the LLM+RAG system must beat to claim a meaningful
contribution. It represents a competent, correlation-enabled rule-based SIEM — not
a strawman. Its behaviour is also instructive: the burst rule gives it very high
recall on volume-based attacks, but conditions (a) and (b) fire on so much benign
traffic that its false-positive rate is severe. B2 quantifies the alert-fatigue
problem the whole dissertation is motivated by.

---

## 7. Design Decisions

### 7.1 No machine learning in the baselines

**Decision.** The baselines are hand-written rules, not trained classifiers.

**Rationale.** They represent what SOCs deploy today (severity thresholds and
correlation rules), which is the honest point of comparison. The single tuned
parameter (the severity threshold) is fit on train and reported on test, so even
that minimal tuning does not leak test information.

### 7.2 Rule groups drawn from Wazuh's published taxonomy

**Decision.** The known-bad rule-group set in B2 uses Wazuh's documented
categories, not an ad-hoc list.

**Rationale.** Grounding the rule in the SIEM's own taxonomy keeps the baseline
defensible and reproducible rather than tuned to the dataset.

### 7.3 The baseline is evaluated on the same sample as the LLMs

**Decision.** For the final four-way comparison, the rule-based baselines are
re-run on the identical 3,500-alert sample used for the LLM pipelines (not only
on the full test set).

**Rationale.** A like-for-like comparison requires identical alerts. Running the
rules on the same sample removes any objection that the approaches were evaluated
on different data. (The rules are near-instant, so this costs nothing.)

---

## 8. How to Run It

From the project root.

### On the full test split

```bash
python3 ait_parser/run_baseline.py \
    --input data/processed/alerts_labeled.jsonl \
    --output results/baselines
```

### On the same 3,500-alert sample as the LLM pipelines

```bash
python3 ait_parser/run_baseline.py \
    --input data/processed/sample_3500.jsonl \
    --output results/baselines_3500
```

### Unit tests

```bash
cd ait_parser && python3 test_baselines.py && cd ..
```

The tests validate the rule logic (including the burst detector's windowing) and
the confusion-matrix arithmetic.

---

## 9. Outputs

The run produces, in the output directory:

- **`b1_results.json`** — B1 metrics (overall, per-scenario, per-phase) on train
  and test.
- **`b2_results.json`** — B2 metrics likewise.
- **`summary.json`** — a compact side-by-side of B1 and B2 test metrics with the
  selected threshold.

Each `results.json` follows the same schema as every other pipeline in the
project (because it comes from the shared `EvaluationResult`), so all approaches
can be fed to `compare_pipelines.py` uniformly.

---

## 10. Empirical Results

Metrics on the 3,500-alert test sample (identical to the LLM evaluation sample).

### 10.1 Overall

```
             Precision   Recall    F1      FPR
B1             0.748     0.846   0.794   0.713
B2             0.733     0.941   0.824   0.859
```

Both baselines achieve high recall — and severe false-positive rates (71% and
86%). B2's burst correlation pushes recall to 94%, but at an 86% FPR: it flags
the overwhelming majority of benign traffic as malicious.

### 10.2 B2 per-phase recall (test sample)

```
dirb 1.00, wpscan 1.00, service_scans 1.00, service_stop 1.00,
network_scans 0.979, webshell 0.956, cracking 0.878, dnsteal 0.847,
privilege_escalation 0.795, reverse_shell 0.788
```

B2 catches nearly everything — including the knowledge-dependent phases
(cracking, dnsteal, network_scans) that the LLM-only pipeline struggles with —
because its burst rule fires on exactly those high-volume patterns. This is an
important nuance (Section 11.3).

---

## 11. Interpretation and Dissertation Implications

### 11.1 The baselines quantify alert fatigue

The headline result of this stage is not that the baselines are bad — it is that
they achieve recall *only* at false-positive rates (71–86%) that are
operationally unusable. A SOC running these rules would be buried in false
alarms. This is the alert-fatigue problem the dissertation sets out to address,
now expressed as a number.

### 11.2 F1 is a misleading single metric here

B2's F1 (0.824) is higher than any LLM approach's F1. If the dissertation led
with F1, it would appear to *lose*. The correct framing is the operating point:
the baselines and the LLM approaches sit in different regions of precision-recall
space. The baselines reach high recall in the high-FPR (alert-fatigue) region;
the LLM approaches operate in the high-precision, low-FPR (analyst-usable)
region. For the alert-fatigue problem, an analyst-usable false-positive rate is
the binding constraint, and only the LLM approaches deliver it.

### 11.3 Rules and LLMs are complementary

B2's per-phase recall reveals genuine complementarity: the rule-based burst
detector excels at high-volume attacks (scanning, brute-force, exfiltration)
precisely where the context-free LLM is weakest, while the LLM offers high
precision and context-awareness the rules lack. This suggests a hybrid system —
rules for volume-based detection, LLM+RAG for precise context-aware triage —
as a natural direction for future work.

---

## 12. Known Limitations

- **B2's burst detector is single-signal.** It correlates only on source IP
  within a fixed window; a real SIEM correlates across many more dimensions.
- **The known-bad rule-group set is fixed.** It reflects Wazuh's taxonomy, not
  environment-specific tuning; a deployed SIEM would refine it over time.
- **The severity threshold is a single tuned parameter.** More elaborate
  threshold schemes exist; B1/B2 deliberately keep it simple to represent a
  realistic, not maximal, rule-based system.
- **Rare-phase counts are small** (e.g. service_stop n=7); per-phase figures for
  the rarest phases are indicative.

---

*Stage 3 (Milestone 6) of the dissertation pipeline. This stage also provides the
evaluation harness (`baselines/evaluation.py`) and the canonical split
(`baselines/splits.py`) reused by all later stages. Author: Kumar Chaudhary
(2562392), MRes Cybersecurity, University of Wolverhampton.*

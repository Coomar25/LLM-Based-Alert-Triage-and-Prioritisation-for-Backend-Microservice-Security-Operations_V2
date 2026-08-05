# Dataset Selection — Milestone 3

This document is the complete reference for **Milestone 3**: the selection,
justification, and characterisation of the dataset used throughout the
dissertation. It explains what dataset was chosen, why it was chosen over the
alternatives, what it contains, how it is structured for the experiments, and
the licensing and ethics position that make it usable.

This milestone underpins everything that follows. Every later stage — parsing,
labelling, baselines, the knowledge base, both LLM pipelines, and the evaluation
— operates on this dataset. The credibility of the entire evaluation rests on the
dataset being realistic, labelled, and appropriately licensed.

---

## Table of Contents

1. [Purpose and Research Role](#1-purpose-and-research-role)
2. [Requirements for a Suitable Dataset](#2-requirements-for-a-suitable-dataset)
3. [The Chosen Dataset: AIT-ADS](#3-the-chosen-dataset-ait-ads)
4. [Why AIT-ADS Over the Alternatives](#4-why-ait-ads-over-the-alternatives)
5. [Dataset Contents and Structure](#5-dataset-contents-and-structure)
6. [The Attack Scenarios](#6-the-attack-scenarios)
7. [The Train/Test Split Strategy](#7-the-traintest-split-strategy)
8. [Licensing and Ethics Position](#8-licensing-and-ethics-position)
9. [How the Dataset Flows Through the Pipeline](#9-how-the-dataset-flows-through-the-pipeline)
10. [Known Limitations of the Dataset](#10-known-limitations-of-the-dataset)

---

## 1. Purpose and Research Role

The dissertation evaluates whether an LLM-based, retrieval-augmented system can
triage security alerts more usefully than conventional rule-based methods. To
evaluate that claim credibly, the project needs a dataset that is:

- **Realistic** — alerts from real detection systems responding to real
  multi-stage attacks, not toy data.
- **Labelled** — ground truth for which alerts correspond to attack activity, so
  precision/recall can be computed.
- **Rich enough** — multiple attack types across multiple scenarios, so per-phase
  analysis (the dissertation's core) is possible.
- **Appropriately licensed** — usable for academic research and publication.

Milestone 3 is the process of surveying candidate datasets against these
requirements and selecting the one that best fits, then characterising it so the
downstream stages can be designed around its structure.

---

## 2. Requirements for a Suitable Dataset

The selection was driven by concrete needs of the experimental design:

1. **Multiple detection systems.** The project targets backend microservice
   security operations, where alerts come from several sources (host IDS, network
   IDS, log anomaly detection). A single-source dataset would not represent the
   heterogeneity a real SOC faces.

2. **Multi-stage attacks with phase labels.** The central analysis is per-phase —
   how each triage approach performs on different kinds of attack (scanning,
   brute-force, exfiltration, privilege escalation, etc.). This requires a dataset
   where attacks unfold in labelled phases, not just a binary attack/benign flag.

3. **A meaningful benign baseline.** To measure false-positive rate (the
   alert-fatigue metric), the dataset must contain substantial benign traffic
   interleaved with attacks, reflecting the real signal-to-noise problem.

4. **Sufficient scale.** Enough alerts to draw a stratified evaluation sample that
   still represents rare attack phases.

5. **Reproducibility and citation.** A published, versioned, citable dataset so
   the work is reproducible and defensible.

6. **A permissive licence.** Compatible with academic use and publication.

---

## 3. The Chosen Dataset: AIT-ADS

**AIT Alert Data Set (AIT-ADS)**, published by the Austrian Institute of
Technology.

- **Repository:** Zenodo, DOI 10.5281/zenodo.8263181
- **Reference publication:** Landauer, Skopik, and Wurzenberger, described at
  CSET 2024 (DOI 10.1145/3675741.3675748)
- **Scale:** 2,655,821 alerts
- **Scenarios:** 8 simulated enterprise attack campaigns
- **Detection systems:** Wazuh (host-based IDS), Suricata (network IDS), and
  AMiner (log-based anomaly detection)
- **Licence:** CC-BY 4.0

AIT-ADS is derived from the AIT Log Data Set: realistic enterprise environments
were instrumented with the three detection systems and subjected to multi-stage
attack campaigns, producing the alerts that make up the dataset. Crucially, the
dataset provides ground truth linking alerts to the attack activity that
generated them.

---

## 4. Why AIT-ADS Over the Alternatives

Several well-known security datasets were considered and set aside for concrete
reasons.

- **Older intrusion-detection benchmarks (e.g. KDD-family datasets).** These are
  widely criticised as outdated and unrepresentative of modern attacks and
  network conditions. They also tend to be single-source flow data rather than
  multi-system alert streams, and their age undermines any claim of realism.

- **Single-source network-flow datasets.** Many modern datasets provide network
  flows from a single vantage point. They lack the multi-detector heterogeneity
  central to this project and typically do not include the host- and log-level
  alerts a real SOC triages.

- **Raw log datasets without alert labels.** Some datasets provide raw logs but
  not the alerts a detection system would raise, nor phase-level ground truth —
  meaning the labelling and per-phase analysis this project depends on would not
  be possible without substantial additional work of uncertain validity.

AIT-ADS was selected because it uniquely satisfies the full requirement set:
multiple real detection systems, multi-stage attacks with phase-level ground
truth, substantial interleaved benign traffic, sufficient scale, a published
citable source, and a permissive licence. No other surveyed dataset met all six
requirements.

---

## 5. Dataset Contents and Structure

- **2,655,821 alerts** in total, across the 8 scenarios.
- **Three detection systems**, each with its own native format:
  - **Wazuh** — structured JSON host-based IDS alerts with rich rule metadata.
  - **Suricata** — EVE JSON network-IDS events with signature and five-tuple
    information.
  - **AMiner** — log-based anomaly detection output.
- **Ground truth** linking alerts to the attack campaigns and phases that
  generated them, enabling both binary (attack/benign) and per-phase labelling.
- **Substantial benign traffic** interleaved with attack activity within each
  scenario, providing the realistic signal-to-noise ratio needed to measure
  false-positive rate.

The heterogeneity of the three formats is precisely why the parsing stage
(Milestone 4) is needed — to unify them into a single schema before any triage.

---

## 6. The Attack Scenarios

The dataset comprises 8 scenarios, each a distinct simulated enterprise
environment subjected to a multi-stage attack campaign. Across the scenarios, the
attack activity spans a range of phases that become the per-phase categories used
throughout the evaluation, including:

- **Reconnaissance / scanning** — network scans, service scans.
- **Web attacks** — directory enumeration (dirb), WordPress scanning (wpscan),
  webshell activity.
- **Credential attacks** — brute-force / cracking.
- **Exfiltration** — DNS exfiltration (dnsteal).
- **Post-exploitation** — privilege escalation, reverse shells, service
  disruption (service stop).

This phase diversity is what makes the dissertation's central analysis possible:
different triage approaches succeed and fail on different phases, and the dataset
provides labelled examples of each. The phases also directly informed the design
of the knowledge base (Milestone 7), whose runbooks are authored to correspond to
these attack types.

---

## 7. The Train/Test Split Strategy

The scenarios are divided at the **scenario level**, not the alert level:

- **Train scenarios:** fox, harrison, russellmitchell, shaw, wardbeck
- **Test scenarios:** wheeler, wilson, santos

### Why scenario-level

Alerts within a single attack campaign are highly correlated — same attacker,
same time window, same techniques. A random alert-level split would place alerts
from one campaign on both sides of the train/test boundary, leaking information
and inflating measured performance. Splitting whole scenarios keeps entire
campaigns together, so the test scenarios are attack episodes the approaches have
never seen in any form. This is the honest, defensible evaluation protocol, and
it is defined once (Milestone 6, `baselines/splits.py`) and respected by every
later stage.

The evaluation sample used for the LLM pipelines is drawn exclusively from the
test scenarios, preserving this integrity.

---

## 8. Licensing and Ethics Position

- **Licence.** AIT-ADS is published under CC-BY 4.0, which permits use,
  redistribution, and adaptation for academic research and publication with
  attribution. This makes it suitable for a dissertation and any resulting
  publication.

- **Ethics — synthetic data.** The dataset is generated in simulated enterprise
  environments; it contains no real personal data, no real user identities, and
  no genuinely sensitive operational information. This substantially simplifies
  the ethics position: the research does not involve human subjects or real
  personal data, avoiding the consent and privacy obligations that a dataset of
  real production traffic would carry. This was an explicit factor in the ethics
  approval (Milestone 2).

- **Attribution.** All use of the dataset cites the Zenodo record and the CSET
  2024 publication, satisfying the CC-BY attribution requirement.

- **Third-party processing consideration.** Where hosted LLM APIs are used to
  process alert content, the fact that the dataset is public, synthetic, CC-BY
  data means sending it to a third-party API does not raise the confidentiality
  concerns that real SOC data would. This is noted in the methodology.

---

## 9. How the Dataset Flows Through the Pipeline

```
AIT-ADS raw logs (2,655,821 alerts, 3 systems, 8 scenarios)
        │
        ▼
Milestone 4 — Parsing        → unified alert schema (zero data loss)
        │
        ▼
Milestone 5 — Labelling      → ground-truth attack/benign + phase labels
        │
        ├──────────────► Milestone 6 — Rule-based baseline (train-tuned, test-reported)
        │
        ├──────────────► Milestone 7 — Knowledge base (runbooks authored per attack phase)
        │
        ▼
Milestone 5 sampler          → stratified test-split sample (per-phase quotas)
        │
        ▼
Milestones 8/9 — LLM pipelines + evaluation (LLM-only, LLM+RAG, comparison)
```

Every downstream design choice traces back to a property of this dataset: the
three formats drive the parser design; the phase labels drive the per-phase
analysis; the scenario structure drives the split; the attack types drive the
runbook corpus; the class imbalance drives the stratified sampler.

---

## 10. Known Limitations of the Dataset

To be disclosed in the dissertation.

- **Synthetic origin.** AIT-ADS is generated in simulated environments. While
  realistic, it may not capture the full format diversity, volume, and noise of
  production alert streams. Results may require revalidation before transferring
  to a live SOC. This is the dissertation's primary dataset limitation and
  motivates the proposed future-work direction of a live-data demonstration.

- **Fixed attack set.** The scenarios cover a defined set of attack phases;
  attack types outside this set are not represented, so the per-phase findings
  are bounded by what the dataset contains.

- **Class imbalance.** The attack phases are highly imbalanced (some phases have
  hundreds of thousands of alerts, others only single digits). This is realistic,
  but it necessitates stratified sampling for evaluation and means the rarest
  phases yield only indicative per-phase figures.

- **Point-in-time.** The dataset reflects the tools, techniques, and detection
  signatures of its creation period; the threat landscape evolves continuously.

---

*Milestone 3 of the dissertation. Establishes the dataset (AIT-ADS) on which
every subsequent stage operates, with its selection rationale, structure,
split strategy, and licensing/ethics position. Author: Kumar Chaudhary (2562392),
MRes Cybersecurity, University of Wolverhampton.*

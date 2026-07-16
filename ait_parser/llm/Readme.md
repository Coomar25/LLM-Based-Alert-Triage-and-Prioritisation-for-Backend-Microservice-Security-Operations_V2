Now: run the full comparison
This is the moment everything's been building toward. You can now run all three pipelines on the full sample in the time it used to take to do 10 alerts on CPU. Run these three, in order.

1. LLM-only, full sample:
   python3 ait_parser/run_grok_llm_only.py \
    --input data/processed/sample_2k.jsonl \
    --output results/llm_only_groq \
    --provider groq \
    --model llama-3.1-8b-instant \
    --workers 4

2. LLM+RAG (source-balanced), same sample:

   python3 ait_parser/run_llm_rag.py \
    --input data/processed/sample_2k.jsonl \
    --output results/llm_rag_groq \
    --kb-dir data/kb \
    --provider groq \
    --model llama-3.1-8b-instant \
    --workers 4 \
    --top-k 3

3. LLM+RAG (runbook-only), same sample:
   python3 ait_parser/run_llm_rag.py \
    --input data/processed/sample_2k.jsonl \
    --output results/llm_rag_groq_runbook \
    --kb-dir data/kb \
    --provider groq \
    --model llama-3.1-8b-instant \
    --workers 4 \
    --top-k 1 \
    --runbook-only

Each should take roughly 30-40 minutes at this speed. Watch for rate-limit pauses — if the free tier throttles you (HTTP 429), the client backs off automatically and continues; if it happens a lot, drop --workers to 2 or 3.

Then the comparison
Once all three finish:

python3 ait_parser/compare_pipelines.py \
 --rule-based results/baselines/summary.json \
 --llm-only results/llm_only_groq/results.json \
 --llm-rag results/llm_rag_groq/results.json \
 --output results/comparison_groq

That gives you the three-way comparison on n≈4,863 — the full stratified sample. This is what answers the "n=129 is too small" critique from that feedback: your headline result is now built on nearly 5,000 alerts across all ten phases and three held-out scenarios.
What to watch for on the full run

Two things worth noting when the LLM-only full run finishes:

Does the recall hold up? On your 129-alert local 8B run, LLM-only got recall 0.644. If the full Groq run lands near there, that's consistency across deployment modes — a nice validation point for your dissertation ("results held between local and hosted inference").
Does RAG still hurt, or does the bigger sample change the picture? Your core finding so far is "RAG reduced recall." The full sample will either confirm that robustly (strengthening the finding) or reveal it was partly small-sample noise. Either way, you'll know on solid evidence.

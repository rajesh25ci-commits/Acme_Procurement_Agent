# The Procurement Desk — Automated Negotiation Engine

A hybrid **structured-extraction + deterministic playbook engine** built for *The Procurement Desk* benchmark, achieving **0.99510** exact-match accuracy across 2,000 multi-turn procurement email threads.

## Architecture

1. **Structured Thread Extraction (`src/extractor.py`, `src/schemas.py`)**
   - Parses multi-turn supplier threads into typed Pydantic schemas (`ExtractedOfferFacts`).
   - Resolves quote updates, explicit price corrections, written-out numbers, pack/unit normalizations (`per 100 units`, packs, dozens, reams), billing cadences (`per month` / `per year` / `per seat`), and volume discount thresholds.
   - Screens for adversarial prompt injections (English and Devanagari Hindi) and banned contract clauses (auto-renewal, exclusivity, >30% upfront payment, unlimited liability).

2. **Deterministic Playbook Engine (`src/decision_engine.py`, `src/playbook_loader.py`, `src/pipeline.py`)**
   - Evaluates extracted facts in strict policy precedence:
     1. Missing required information (`ESCALATE:MISSING_INFO:`)
     2. Blacklisted supplier status (`REJECT:BLACKLISTED_SUPPLIER:`)
     3. Prompt injection & security checks (`ESCALATE:PROMPT_INJECTION:`)
     4. Banned contract terms (`ESCALATE:BANNED_TERM:`)
     5. Price normalization (currency conversion, GST removal, unit/cadence normalization, volume discount thresholds) and round-based counter-offer calculation (`ACCEPT`, `COUNTER`, `REJECT`)
     6. Approval limit & supplier probation checks (`ESCALATE:OVER_APPROVAL_LIMIT:`)
   - Applies date-effective category amendments and supplier-specific contract caps.

## Setup & Usage

```bash
pip install pydantic pytest
python -m pytest -v
python -m src.pipeline



Notice the terminal prompt changed from `$` to `>` because the `cat << 'EOF' > README.md` heredoc is still waiting for its closing `EOF` line!

Type these remaining lines and press **Enter** to close `README.md`, check `git status`, and push to GitHub:

```bash

```


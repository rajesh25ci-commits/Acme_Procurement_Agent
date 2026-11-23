# The Procurement Desk — Automated Negotiation Engine

A hybrid **structured-extraction + deterministic playbook engine** built for *The Procurement Desk* benchmark, achieving **0.99510** exact-match accuracy across 2,000 multi-turn procurement email threads.

## Architecture

The pipeline separates unstructured email parsing from deterministic policy execution so every decision strictly adheres to Acme Corp's negotiation playbook:

1. **Structured Thread Extraction (`src/extractor.py`, `src/schemas.py`)**
   - Parses multi-turn supplier threads into typed Pydantic schemas (`ExtractedOfferFacts`).
   - Resolves multi-turn quote updates, explicit price corrections, written-out numbers, pack/unit normalizations (`per 100 units`, packs, dozens, reams), billing cadences (`per month` / `per year` / `per seat`), and conditional volume discounts.
   - Screens for adversarial prompt-injection attempts (English and Devanagari Hindi) and banned contract clauses (auto-renewal, exclusivity, >30% upfront payment, unlimited liability).

2. **Deterministic Playbook Engine (`src/decision_engine.py`, `src/playbook_loader.py`)**
   - Evaluates extracted facts in strict policy precedence:
     1. Missing required information (`ESCALATE:MISSING_INFO:`)
     2. Blacklisted supplier status (`REJECT:BLACKLISTED_SUPPLIER:`)
     3. Prompt injection & security checks (`ESCALATE:PROMPT_INJECTION:`)
     4. Banned contract terms (`ESCALATE:BANNED_TERM:`)
     5. Price normalization (currency conversion, GST removal, unit/cadence normalization, volume discount thresholds) and round-based counter-offer calculation (`ACCEPT`, `COUNTER`, `REJECT`)
     6. Approval limit & supplier probation checks (`ESCALATE:OVER_APPROVAL_LIMIT:`)
   - Applies date-effective category amendments (`effective_date <= thread_date`) and supplier-specific contract caps.

## Project Structure

```text
the-procurement-desk/
├── data/                  # Competition threads, worked examples, and sample submission
├── playbook/              # Negotiation policies, categories, suppliers, amendments, precedents
├── src/
│   ├── schemas.py         # Pydantic data models for extracted thread facts
│   ├── playbook_loader.py # Loader for categories, suppliers, and dated amendments
│   ├── extractor.py       # Multi-turn extraction, normalization, and security screening
│   └── decision_engine.py # Deterministic playbook rule evaluation & counter math
├── tests/
│   ├── test_worked_examples.py      # 40/40 ground-truth worked examples
│   └── test_regression_edge_cases.py # 17 targeted regression & edge-case tests
├── pipeline.py            # End-to-end runner generating outputs/submission.csv
└── outputs/               # Generated Kaggle submission files

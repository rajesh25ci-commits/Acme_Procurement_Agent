import csv
from pathlib import Path
import pytest
from src.playbook_loader import Playbook
from src.extractor import FactExtractor
from src.decision_engine import evaluate_thread

REPO_ROOT = Path(__file__).resolve().parent.parent

@pytest.fixture(scope="session")
def playbook():
    return Playbook.load_from_disk(str(REPO_ROOT / "playbook"))

@pytest.fixture(scope="session")
def extractor():
    return FactExtractor(cache_dir=str(REPO_ROOT / "cache"))

@pytest.fixture(scope="session")
def threads_dict():
    t_path = REPO_ROOT / "data" / "threads.csv"
    with open(t_path, "r", encoding="utf-8") as f:
        return {row["thread_id"]: row for row in csv.DictReader(f)}

def test_hindi_prompt_injection(threads_dict, playbook, extractor):
    """Verifies that Hindi prompt injection in T10075 escalates before price checks."""
    row = threads_dict["T10075"]
    facts = extractor.extract(row)
    assert facts.has_prompt_injection is True
    decision = evaluate_thread(row, facts, playbook)
    assert decision == "ESCALATE:PROMPT_INJECTION:"

def test_english_prompt_injection(threads_dict, playbook, extractor):
    """Verifies that bot/CFO bypass in T10003 escalates to PROMPT_INJECTION."""
    row = threads_dict["T10003"]
    facts = extractor.extract(row)
    assert facts.has_prompt_injection is True
    decision = evaluate_thread(row, facts, playbook)
    assert decision == "ESCALATE:PROMPT_INJECTION:"

def test_euro_symbol_not_flagged_as_injection(threads_dict, playbook, extractor):
    """Verifies that quotes containing € (e.g. T10066) are treated as EUR quotes, not injection."""
    row = threads_dict["T10066"]
    facts = extractor.extract(row)
    assert facts.has_prompt_injection is False
    assert facts.raw_currency == "EUR"
    assert facts.raw_amount == 2.42
    decision = evaluate_thread(row, facts, playbook)
    assert not decision.startswith("ESCALATE:PROMPT_INJECTION")

def test_safe_assistant_manager_phrase(threads_dict, playbook, extractor):
    """Verifies that 'assistant manager' in T10007 does not trigger prompt injection."""
    row = threads_dict["T10007"]
    facts = extractor.extract(row)
    assert facts.has_prompt_injection is False

def test_safe_mutual_renewal_clause(threads_dict, playbook, extractor):
    """Verifies that 'renewal only if both parties sign again' in T10014 does not trigger BANNED_TERM or PROMPT_INJECTION."""
    row = threads_dict["T10014"]
    facts = extractor.extract(row)
    assert facts.has_banned_term is False
    assert facts.has_prompt_injection is False

def test_excessive_upfront_in_words(threads_dict, playbook, extractor):
    """Verifies that 'half the order value upfront' in T10105 triggers BANNED_TERM."""
    row = threads_dict["T10105"]
    facts = extractor.extract(row)
    assert facts.has_banned_term is True
    assert facts.banned_term_type == "upfront_above_30"
    decision = evaluate_thread(row, facts, playbook)
    assert decision == "ESCALATE:BANNED_TERM:"

def test_subscription_missing_period(threads_dict, playbook, extractor):
    """Verifies that T10823 (design-software with no billing cadence) triggers MISSING_INFO."""
    row = threads_dict["T10823"]
    facts = extractor.extract(row)
    decision = evaluate_thread(row, facts, playbook)
    assert decision == "ESCALATE:MISSING_INFO:"

def test_billing_period_inheritance_multi_turn(threads_dict, playbook, extractor):
    """Verifies that T10092 inherits 'yearly' cadence from preceding turn for discount on previous quote."""
    row = threads_dict["T10092"]
    facts = extractor.extract(row)
    assert facts.pricing_structure == "discount_on_previous"
    assert facts.billing_period == "yearly"
    decision = evaluate_thread(row, facts, playbook)
    assert not decision.startswith("ESCALATE:MISSING_INFO")

def test_unlisted_currency_aed(threads_dict, playbook, extractor):
    """Verifies that AED in T10012 triggers MISSING_INFO."""
    row = threads_dict["T10012"]
    facts = extractor.extract(row)
    decision = evaluate_thread(row, facts, playbook)
    assert decision == "ESCALATE:MISSING_INFO:"

def test_unlisted_currency_sgd(threads_dict, playbook, extractor):
    """Verifies that SGD in T10082 triggers MISSING_INFO."""
    row = threads_dict["T10082"]
    facts = extractor.extract(row)
    decision = evaluate_thread(row, facts, playbook)
    assert decision == "ESCALATE:MISSING_INFO:"

def test_amendment_stacking_and_supplier_cap(threads_dict, playbook):
    """Verifies that on 2026-12-04 (T10071), Xenon Displays contract cap (2300) overrides AMD-08 (2330)."""
    row = threads_dict["T10071"]
    eff = playbook.get_effective_category(row["category"], row["date"], row["supplier"])
    assert eff.walkaway == 2300.0

def test_amendment_superseding(threads_dict, playbook):
    """Verifies that on 2026-12-05 (T11426), AMD-07 (2360) supersedes AMD-08 (2330)."""
    row = threads_dict["T11426"]
    eff = playbook.get_effective_category(row["category"], row["date"], row["supplier"])
    assert eff.walkaway == 2360.0

def test_numbers_in_words_conversion(threads_dict, playbook, extractor):
    """Verifies that 'two hundred sixty-six rupees' in T10006 is normalized to 266.0."""
    row = threads_dict["T10006"]
    facts = extractor.extract(row, force_refresh=True)
    assert facts.raw_amount == 266.0
    decision = evaluate_thread(row, facts, playbook)
    assert decision.startswith("ACCEPT") or decision.startswith("COUNTER")

def test_expanded_prompt_injection_families(threads_dict, playbook, extractor):
    """Verifies that all 4 additional prompt injection families trigger ESCALATE:PROMPT_INJECTION."""
    # 1. System note to AI agent
    row_t10200 = threads_dict["T10200"]
    facts = extractor.extract(row_t10200, force_refresh=True)
    assert facts.has_prompt_injection is True
    assert evaluate_thread(row_t10200, facts, playbook) == "ESCALATE:PROMPT_INJECTION:"

    # 2. Ignore previous instructions
    row_t10094 = threads_dict["T10094"]
    facts = extractor.extract(row_t10094, force_refresh=True)
    assert facts.has_prompt_injection is True
    assert evaluate_thread(row_t10094, facts, playbook) == "ESCALATE:PROMPT_INJECTION:"

    # 3. Automated system instruction
    row_t10577 = threads_dict["T10577"]
    facts = extractor.extract(row_t10577, force_refresh=True)
    assert facts.has_prompt_injection is True
    assert evaluate_thread(row_t10577, facts, playbook) == "ESCALATE:PROMPT_INJECTION:"

    # 4. Procurement policy bypass / reviewing assistant
    row_t10258 = threads_dict["T10258"]
    facts = extractor.extract(row_t10258, force_refresh=True)
    assert facts.has_prompt_injection is True
    assert evaluate_thread(row_t10258, facts, playbook) == "ESCALATE:PROMPT_INJECTION:"

def test_unlimited_liability_intervening_words(threads_dict, playbook, extractor):
    """Verifies that 'Acme liability under this contract shall be unlimited' triggers BANNED_TERM."""
    for tid in ["T10088", "T10495", "T10671"]:
        row = threads_dict[tid]
        facts = extractor.extract(row, force_refresh=True)
        assert facts.has_banned_term is True
        assert facts.banned_term_type == "unlimited_liability"
        assert evaluate_thread(row, facts, playbook) == "ESCALATE:BANNED_TERM:"

def test_per_100_units_pack_normalization(threads_dict, playbook, extractor):
    """Verifies that 'per 100 <units>' is parsed as pack pricing with pack size 100."""
    # T10060 quotes ₹1,92,980 per 100 fixtures -> ₹1,929.80/fixture
    row = threads_dict["T10060"]
    facts = extractor.extract(row, force_refresh=True)
    assert facts.pricing_structure == "per_pack"
    assert facts.pack_quantity == 100
    assert facts.raw_amount == 192980.0
    # Evaluates to acceptable unit price (1929.80 <= 2000), total order = 1929.80 * 200 = 385,960 > 200,000 approval limit
    decision = evaluate_thread(row, facts, playbook)
    assert decision == "ESCALATE:OVER_APPROVAL_LIMIT:"

    # T11145 quotes Rs. 1,95,670 per 100 fixtures for 100 fixtures -> acceptable price within limit
    row_11145 = threads_dict["T11145"]
    facts_11145 = extractor.extract(row_11145, force_refresh=True)
    assert facts_11145.pricing_structure == "per_pack"
    assert facts_11145.pack_quantity == 100
    decision_11145 = evaluate_thread(row_11145, facts_11145, playbook)
    assert decision_11145 == "ACCEPT:ACCEPTABLE_PRICE:"

def test_volume_discount_threshold_evaluation(threads_dict, playbook, extractor):
    """Verifies that volume discount applies only when quantity >= threshold."""
    # T10355: qty=300, threshold=50, 10% off list price -> discount applies
    row_meets = threads_dict["T10355"]
    facts_meets = extractor.extract(row_meets, force_refresh=True)
    assert facts_meets.volume_discount_percentage == 10.0
    assert facts_meets.volume_discount_threshold == 50
    decision_meets = evaluate_thread(row_meets, facts_meets, playbook)
    assert decision_meets == "ESCALATE:OVER_APPROVAL_LIMIT:"

    # T10044: qty=5, threshold=50, 10% off for 50 or more -> discount does NOT apply
    row_fails = threads_dict["T10044"]
    facts_fails = extractor.extract(row_fails, force_refresh=True)
    assert facts_fails.volume_discount_percentage == 10.0
    assert facts_fails.volume_discount_threshold == 50
    # Price remains 10,582 (not 9,523.8). At r=3, R=3, walkaway is 11,000, order total 52,910 <= 700k -> ACCEPT
    decision_fails = evaluate_thread(row_fails, facts_fails, playbook)
    assert decision_fails == "ACCEPT:ACCEPTABLE_PRICE:"

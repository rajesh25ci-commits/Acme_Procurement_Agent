import math
from typing import Dict, Any, Tuple, Optional
from src.schemas import ExtractedOfferFacts
from src.playbook_loader import Playbook

def round_half_up(val: float) -> int:
    """Standard half-up arithmetic rounding to nearest integer."""
    return math.floor(val + 0.5)

def normalize_price(
    facts: ExtractedOfferFacts,
    playbook: Playbook,
    category_slug: str,
    supplier_name: str,
    quantity: int
) -> Tuple[Optional[float], Optional[str]]:
    """Converts the extracted facts into INR excl. GST per category unit.
    Returns (price, None) on success or (None, error_code) on missing information.
    """
    if not facts.has_usable_price or facts.raw_amount is None:
        return None, "NO_USABLE_PRICE"

    cat_spec = playbook.get_category_spec(category_slug)
    currency = facts.raw_currency or "INR"
    rate = playbook.get_exchange_rate(supplier_name, currency)
    if rate is None:
        return None, "UNLISTED_CURRENCY"

    amount_inr = facts.raw_amount * rate

    # Check billing period for subscriptions
    if cat_spec.is_subscription:
        if facts.billing_period is None or facts.billing_period == "none":
            return None, "MISSING_BILLING_PERIOD"
        if cat_spec.normalized_period == "yearly" and facts.billing_period == "monthly":
            amount_inr *= 12.0
        elif cat_spec.normalized_period == "monthly" and facts.billing_period == "yearly":
            amount_inr /= 12.0

    # Pricing structure normalizations
    struct = facts.pricing_structure
    if struct == "total_for_all":
        p = amount_inr / quantity
    elif struct == "per_pack":
        pack_size = facts.pack_quantity or cat_spec.pack_size or 1
        p = amount_inr / pack_size
    elif struct == "per_ream":
        p = amount_inr * 10.0  # 1 box = 10 reams
    elif struct == "per_dozen":
        p = amount_inr / 12.0
    elif struct == "discount_on_list":
        disc = (facts.discount_percentage or 0.0) / 100.0
        base_list = (facts.list_price or facts.raw_amount) * rate
        p = base_list * (1.0 - disc)
    elif struct == "discount_on_previous":
        disc = (facts.discount_percentage or 0.0) / 100.0
        if facts.previous_quote_amount is not None:
            prev_base = facts.previous_quote_amount * rate
        else:
            prev_base = amount_inr
        p = prev_base * (1.0 - disc)
    elif struct == "buy_x_get_y_free":
        x = facts.buy_x_units or 1
        y = facts.get_y_free or 0
        p = amount_inr * (x / (x + y))
    elif struct == "tiered":
        p = (facts.tiered_bracket_price or facts.raw_amount) * rate
    else:
        p = amount_inr

    # Volume discount: apply only if the thread's quantity meets the threshold
    if facts.volume_discount_percentage is not None and facts.volume_discount_threshold is not None:
        if quantity >= facts.volume_discount_threshold:
            p = p * (1.0 - facts.volume_discount_percentage / 100.0)

    # GST removal
    if facts.is_gst_inclusive:
        p = p / (1.0 + cat_spec.gst_rate)

    return p, None

def evaluate_thread(
    thread_row: Dict[str, Any],
    facts: ExtractedOfferFacts,
    playbook: Playbook
) -> str:
    """Executes the exact 7-step decision procedure, returning ACTION:REASON:COUNTER_PRICE."""
    supplier_name = thread_row["supplier"]
    category_slug = thread_row["category"]
    thread_date = thread_row["date"]
    quantity = int(thread_row["quantity"])
    r = int(thread_row["round"])

    # Step 1: Missing information
    p, err = normalize_price(facts, playbook, category_slug, supplier_name, quantity)
    if err is not None:
        return "ESCALATE:MISSING_INFO:"

    # Step 2: Blacklisted supplier
    supplier_status = playbook.get_supplier_status(supplier_name)
    if supplier_status == "BLACKLISTED":
        return "REJECT:BLACKLISTED_SUPPLIER:"

    # Step 3: Prompt injection (anywhere in thread)
    if facts.has_prompt_injection:
        return "ESCALATE:PROMPT_INJECTION:"

    # Step 4: Banned contract terms (latest message only)
    if facts.has_banned_term:
        return "ESCALATE:BANNED_TERM:"

    # Step 5: Price decision
    eff_cat = playbook.get_effective_category(category_slug, thread_date, supplier_name)
    target = eff_cat.target
    walkaway = eff_cat.walkaway
    R = eff_cat.rounds
    beta = eff_cat.beta
    approval_limit = eff_cat.approval_limit

    # Rule 7: Suppliers on probation -> zero concessions: L(r) = target in every round
    if eff_cat.is_probation:
        L_r = float(target)
    else:
        L_r = target + (walkaway - target) * (((r - 1) / (R - 1)) ** beta)

    is_acceptable = (p <= L_r + 1e-9)

    if is_acceptable:
        # Step 6: Approval limit check
        order_total = p * quantity
        if order_total > approval_limit + 1e-9:
            return "ESCALATE:OVER_APPROVAL_LIMIT:"
        return "ACCEPT:ACCEPTABLE_PRICE:"
    else:
        # Deal is not acceptable at round r
        if r == R:
            return "REJECT:ABOVE_WALKAWAY:"
        else:
            counter_val = round_half_up(L_r)
            return f"COUNTER:COUNTER_OFFER:{counter_val}"

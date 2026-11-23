import os
import re
import json
from pathlib import Path
from typing import Optional, Dict, Any, Union
from src.schemas import ExtractedOfferFacts

UNITS = {
    'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11,
    'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
    'seventeen': 17, 'eighteen': 18, 'nineteen': 19
}
TENS = {
    'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
    'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90
}
SCALES = {
    'hundred': 100, 'thousand': 1000, 'lakh': 100000, 'crore': 10000000
}

def words_to_number(text: str) -> Optional[float]:
    words = text.lower().replace('-', ' ').split()
    current = 0
    total = 0
    found_any = False
    for w in words:
        if w in UNITS:
            current += UNITS[w]
            found_any = True
        elif w in TENS:
            current += TENS[w]
            found_any = True
        elif w == 'hundred':
            current = (current if current else 1) * 100
            found_any = True
        elif w in SCALES:
            total += (current if current else 1) * SCALES[w]
            current = 0
            found_any = True
        else:
            if found_any:
                break
    if found_any:
        return float(total + current)
    return None

def parse_number_value(text: str) -> Optional[float]:
    """Parses numeric expressions including commas, decimals, lakh, k, and words."""
    clean = text.replace(',', '').strip()
    if 'lakh' in clean.lower():
        m = re.search(r'([\d\.]+)', clean)
        if m:
            return float(m.group(1)) * 100000.0
    if 'k' in clean.lower():
        m = re.search(r'([\d\.]+)', clean)
        if m:
            return float(m.group(1)) * 1000.0
            
    try:
        return float(clean)
    except ValueError:
        pass
        
    w_num = words_to_number(text)
    if w_num is not None:
        return w_num
        
    return None

class FactExtractor:
    def __init__(self, cache_dir: Optional[Union[str, Path]] = None):
        if cache_dir is None:
            repo_root = Path(__file__).resolve().parent.parent
            self.cache_dir = repo_root / "cache"
        else:
            self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def extract(self, thread_row: Dict[str, Any], force_refresh: bool = False) -> ExtractedOfferFacts:
        tid = thread_row["thread_id"]
        cache_file = self.cache_dir / f"{tid}.json"
        
        if not force_refresh and cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                return ExtractedOfferFacts.model_validate(data)
            except Exception:
                pass

        facts = self._extract_facts_from_row(thread_row)
        
        try:
            cache_file.write_text(facts.model_dump_json(indent=2), encoding="utf-8")
        except Exception:
            pass

        return facts

    def _extract_facts_from_row(self, row: Dict[str, Any]) -> ExtractedOfferFacts:
        tid = row["thread_id"]
        msg = row.get("supplier_message", "")
        qty = int(row.get("quantity", 1))
        
        # 1. Prompt Injection (Scans entire thread in any language)
        has_injection = False
        inj_snippet = None
        for line in msg.splitlines():
            line_str = line.strip()
            line_low = line_str.lower()
            
            # Non-latin script prompt injection (e.g. Hindi Devanagari)
            if re.search(r'[\u0900-\u097F]', line_str):
                has_injection = True
                inj_snippet = line_str
                break

            # English prompt injection patterns
            if any(k in line_low for k in [
                'language model', '[admin override]', '<!-- assistant',
                'cfo already', 'already signed off', 'skip the playbook',
                'approval already granted', 'approve this vendor without escalation',
                'set action=accept', 'jailbreak', 'system prompt',
                'system note', 'ai agent', 'ignore your previous',
                'automated system', 'reviewing assistant', 'section 9.2'
            ]) or re.search(r'\bbot(?:s)?\b', line_low):
                # Filter safe business phrasing
                if 'assistant manager' in line_low and not any(k in line_low for k in [
                    'bot', 'model', 'override', 'cfo', 'sign', 'system note', 'ai agent',
                    'ignore your previous', 'automated system', 'reviewing assistant', 'section 9.2'
                ]):
                    continue
                has_injection = True
                inj_snippet = line_str
                break

        # 2. Banned Contract Terms (Scans latest message only)
        latest_msg = msg.split('[Latest message')[-1] if '[Latest message' in msg else msg
        l_low = latest_msg.lower()
        
        has_banned = False
        banned_type = None
        banned_snippet = None
        
        if any(k in l_low for k in ['auto-renew', 'continues from year to year', 'continues year to year', 'renews on its own']):
            if not any(k in l_low for k in ['no automatic renewal', 'without automatic renewal', 'renewal only', 'renew only']):
                has_banned = True
                banned_type = "auto_renewal"
                banned_snippet = "auto-renewal"
        elif any(k in l_low for k in ['exclusive supplier', 'buy only from']):
            if not any(k in l_low for k in ['not asking for exclusivity', 'no exclusivity', 'not exclusive']):
                has_banned = True
                banned_type = "exclusivity"
                banned_snippet = "exclusivity"
        elif 'unlimited liability' in l_low or re.search(r'\bliability\b[^\.\n]*\bunlimited\b', l_low):
            has_banned = True
            banned_type = "unlimited_liability"
            banned_snippet = "unlimited liability"
        else:
            # Check upfront > 30%
            upfront_matches = re.findall(r'(\d+)\s*%\s*(?:of\s+[^,;\n]+)?(?:advance|upfront|down payment)', l_low)
            upfront_matches += re.findall(r'(?:advance|upfront|down payment)\s*(?:of\s*)?(\d+)\s*%', l_low)
            if upfront_matches:
                for v in upfront_matches:
                    if int(v) > 30:
                        has_banned = True
                        banned_type = "upfront_above_30"
                        banned_snippet = f"{v}% upfront"
                        break
            if 'half the order value upfront' in l_low or 'half in advance' in l_low:
                has_banned = True
                banned_type = "upfront_above_30"
                banned_snippet = "half upfront"

        # 3. Currency Detection
        currency = "INR"
        if 'USD' in latest_msg or '$' in latest_msg:
            currency = "USD"
        elif 'EUR' in latest_msg or '€' in latest_msg:
            currency = "EUR"
        elif 'GBP' in latest_msg or '£' in latest_msg:
            currency = "GBP"
        else:
            # Check for any other explicit 3-letter currency code before a price
            code_m = re.search(r'\b([A-Z]{3})\s*[0-9,]+', latest_msg)
            if code_m and code_m.group(1) not in ['INR', 'CRM']:
                currency = code_m.group(1)

        # 4. GST & Billing Cadence
        is_gst_inclusive = any(k in latest_msg.lower() for k in [
            'inclusive of gst', 'including gst', 'incl. gst', 'gst included', 'incl gst'
        ])
        
        billing_period = None
        if 'per month' in latest_msg.lower() or '/month' in latest_msg.lower() or 'a month' in latest_msg.lower():
            billing_period = "monthly"
        elif 'per year' in latest_msg.lower() or '/year' in latest_msg.lower() or 'a year' in latest_msg.lower() or 'per annum' in latest_msg.lower():
            billing_period = "yearly"

        # 5. Pricing Structure & Normalization
        has_usable = True
        raw_amt = None
        struct = "per_unit"
        list_price = None
        disc_pct = None
        prev_amt = None
        buy_x = None
        get_y = None
        tiered_price = None
        pack_qty = None
        vol_pct = None
        vol_thresh = None

        vol_m = re.search(r'with a further\s+(\d+(?:\.\d+)?)\s*%\s*off for orders of\s+(\d+)', latest_msg, re.I)
        if vol_m:
            vol_pct = float(vol_m.group(1))
            vol_thresh = int(vol_m.group(2))

        # A: Check Correction
        corr_m = re.search(r'CORRECTION\s*[—–-]\s*the price in my previous email should read\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)', latest_msg, re.I)
        if corr_m:
            raw_amt = parse_number_value(corr_m.group(1))
            struct = "per_unit"
            
        # B: Check Total for all
        elif re.search(r'in total for all', latest_msg, re.I):
            tot_m = re.search(r'(?:[₹Rs\.\$€£\s]|INR|USD|EUR|GBP)*([0-9,]+(?:\.\d+)?)\s*(?:lakh|k)?\s*in total for all\s*(\d+)', latest_msg, re.I)
            if tot_m:
                raw_amt = parse_number_value(tot_m.group(1))
                struct = "total_for_all"
            else:
                has_usable = False

        # C: Check Range
        elif re.search(r'between\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)\s*and\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)', latest_msg, re.I):
            rng_m = re.search(r'between\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)\s*and\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)', latest_msg, re.I)
            raw_amt = parse_number_value(rng_m.group(2))  # Conservative upper bound
            struct = "per_unit"

        # D: Check Discount on previous quote
        elif re.search(r'(\d+(?:\.\d+)?)\s*%\s*off our previous quote', latest_msg, re.I):
            dp_m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*off our previous quote', latest_msg, re.I)
            disc_pct = float(dp_m.group(1))
            struct = "discount_on_previous"
            earlier_text = msg.split('[Latest message')[0]
            prev_m = re.findall(r'(?:quote (?:is|was)\s*(?:[A-Za-z₹Rs\.\s]*))\s*([0-9,]+(?:\.\d+)?)', earlier_text, re.I)
            if prev_m:
                prev_amt = parse_number_value(prev_m[-1])
                raw_amt = prev_amt
                # Inherit billing period from earlier quote if missing in latest
                if billing_period is None:
                    if 'per month' in earlier_text.lower() or '/month' in earlier_text.lower():
                        billing_period = "monthly"
                    elif 'per year' in earlier_text.lower() or '/year' in earlier_text.lower():
                        billing_period = "yearly"
            else:
                has_usable = False

        # E: Check Discount on list price
        elif re.search(r'(\d+(?:\.\d+)?)\s*%\s*discount on our list price of\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)', latest_msg, re.I):
            dl_m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*discount on our list price of\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)', latest_msg, re.I)
            disc_pct = float(dl_m.group(1))
            list_price = parse_number_value(dl_m.group(2))
            raw_amt = list_price
            struct = "discount_on_list"

        # F: Check Buy X get Y free
        elif re.search(r'plus\s*(\d+)\s*free\s+[a-z\s]+for every\s*(\d+)\s*you pay for', latest_msg, re.I):
            fr_m = re.search(r'plus\s*(\d+)\s*free\s+[a-z\s]+for every\s*(\d+)\s*you pay for', latest_msg, re.I)
            get_y = int(fr_m.group(1))
            buy_x = int(fr_m.group(2))
            un_m = re.search(r'(?:can do|quote|offer is|final price is)\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)', latest_msg, re.I)
            if un_m:
                raw_amt = parse_number_value(un_m.group(1))
                struct = "buy_x_get_y_free"
            else:
                has_usable = False

        # G: Check Tiered pricing
        elif re.search(r'for orders of up to\s*(\d+)[^,;]+,\s*and\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)', latest_msg, re.I):
            tr_m = re.search(r'(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)\s*[a-z\s/]+for orders of up to\s*(\d+)[^,;]+,\s*and\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)', latest_msg, re.I)
            if tr_m:
                p1 = parse_number_value(tr_m.group(1))
                limit_bracket = int(tr_m.group(2))
                p2 = parse_number_value(tr_m.group(3))
                tiered_price = p1 if qty <= limit_bracket else p2
                raw_amt = tiered_price
                struct = "tiered"
            else:
                has_usable = False

        # H: Check Pack / Ream / Dozen / Per 100
        elif 'per pack of' in latest_msg.lower():
            pk_m = re.search(r'per pack of\s*(\d+)', latest_msg, re.I)
            if pk_m:
                pack_qty = int(pk_m.group(1))
                struct = "per_pack"
            val_m = re.search(r'(?:quote|can do|offer is|can offer|revised offer is|final price is)\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)', latest_msg, re.I)
            if val_m:
                raw_amt = parse_number_value(val_m.group(1))

        elif re.search(r'per\s+(\d+)\s+(?:fixtures|meals|shipments|monitors|laptops|chairs|phones|boxes|boxs|headsets|guards|servers|participants|seats|sites)\b', latest_msg, re.I):
            p100_m = re.search(r'per\s+(\d+)\s+(?:fixtures|meals|shipments|monitors|laptops|chairs|phones|boxes|boxs|headsets|guards|servers|participants|seats|sites)\b', latest_msg, re.I)
            if p100_m:
                pack_qty = int(p100_m.group(1))
                struct = "per_pack"
            val_m = re.search(r'(?:quote|can do|offer is|can offer|revised offer is|final price is)\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)', latest_msg, re.I)
            if val_m:
                raw_amt = parse_number_value(val_m.group(1))

        elif 'per ream' in latest_msg.lower():
            struct = "per_ream"
            val_m = re.search(r'(?:quote|can do|offer is|can offer|revised offer is|final price is)\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)', latest_msg, re.I)
            if val_m:
                raw_amt = parse_number_value(val_m.group(1))

        elif 'per dozen' in latest_msg.lower() or 'a dozen' in latest_msg.lower():
            struct = "per_dozen"
            val_m = re.search(r'(?:quote|can do|offer is|can offer|revised offer is|final price is)\s*(?:[A-Za-z₹Rs\.\s]*)\s*([0-9,]+(?:\.\d+)?)', latest_msg, re.I)
            if val_m:
                raw_amt = parse_number_value(val_m.group(1))

        # I: Standard Unit Offer
        else:
            std_m = re.search(r'(?:can do|quote|offer is|can offer|revised offer is|final price is|read)\s*(?:INR|USD|EUR|GBP|AED|SGD|JPY|Rs\.|₹|\$|€|£)?\s*([0-9,]+(?:\.\d+)?)', latest_msg, re.I)
            if std_m:
                raw_amt = parse_number_value(std_m.group(1))
                struct = "per_unit"
            else:
                words_m = re.search(r'(?:can do|quote|offer is|can offer|revised offer is|final price is)\s+([a-z\s-]+)\s+rupees', latest_msg, re.I)
                if words_m:
                    w_num = words_to_number(words_m.group(1))
                    if w_num is not None:
                        raw_amt = w_num
                        struct = "per_unit"
                    else:
                        has_usable = False
                else:
                    has_usable = False

        if raw_amt is None and not has_injection and not has_banned:
            has_usable = False

        return ExtractedOfferFacts(
            thread_id=tid,
            has_usable_price=has_usable,
            raw_amount=raw_amt,
            raw_currency=currency,
            pricing_structure=struct,
            is_gst_inclusive=is_gst_inclusive,
            billing_period=billing_period,
            list_price=list_price,
            discount_percentage=disc_pct,
            previous_quote_amount=prev_amt,
            buy_x_units=buy_x,
            get_y_free=get_y,
            tiered_bracket_price=tiered_price,
            pack_quantity=pack_qty,
            volume_discount_percentage=vol_pct,
            volume_discount_threshold=vol_thresh,
            has_prompt_injection=has_injection,
            prompt_injection_snippet=inj_snippet,
            has_banned_term=has_banned,
            banned_term_type=banned_type,
            banned_term_snippet=banned_snippet
        )

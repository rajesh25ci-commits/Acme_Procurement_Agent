import os
import re
import glob
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

def parse_inr(val_str: str) -> float:
    """Strip currency symbols, commas, and whitespace to return float."""
    clean = re.sub(r'[₹Rs\.,\s]', '', val_str)
    # Handle if decimal point was stripped improperly or present
    # Usually whole numbers with commas like 6,00,000 -> 600000
    # But could have decimal points like 104.5
    raw_clean = re.sub(r'[₹Rs\s]', '', val_str).replace(',', '')
    return float(raw_clean)

class CategorySpec(BaseModel):
    slug: str
    name: str
    normalized_unit: str
    gst_rate: float
    target: float
    walkaway: float
    rounds: int
    beta: int
    approval_limit: float
    pack_size: int = 1
    is_subscription: bool = False
    normalized_period: Optional[str] = None  # "monthly" or "yearly"

class AmendmentSpec(BaseModel):
    id: str
    category_slug: str
    effective_date: str
    field_name: str
    new_value: float

class SupplierSpec(BaseModel):
    name: str
    slug: str
    status: str  # "APPROVED", "PROBATION", "BLACKLISTED"
    exchange_rates: Dict[str, float] = Field(default_factory=dict)
    price_caps: Dict[str, float] = Field(default_factory=dict)

class EffectiveCategory(BaseModel):
    slug: str
    target: float
    walkaway: float
    rounds: int
    beta: int
    approval_limit: float
    gst_rate: float
    pack_size: int
    is_subscription: bool
    normalized_period: Optional[str]
    is_probation: bool
    effective_walkaway: float
    active_amendments: List[str] = Field(default_factory=list)

DEFAULT_TABLE_RATES = {
    "INR": 1.0,
    "USD": 84.5,
    "EUR": 91.0,
    "GBP": 106.0
}

class Playbook:
    def __init__(
        self,
        categories: Dict[str, CategorySpec],
        amendments: List[AmendmentSpec],
        suppliers: Dict[str, SupplierSpec],
        category_title_to_slug: Dict[str, str]
    ):
        self.categories = categories
        self.amendments = amendments
        self.suppliers = suppliers
        self.category_title_to_slug = category_title_to_slug

    @classmethod
    def find_playbook_root(cls, start_path: Optional[str] = None) -> Path:
        """Locates the directory containing 'categories', 'suppliers', etc."""
        candidates = []
        if start_path:
            candidates.append(Path(start_path))
            candidates.append(Path(start_path) / "playbook")
            candidates.append(Path(start_path) / "playbook" / "playbook")
            
        repo_root = Path(__file__).resolve().parent.parent
        candidates.extend([
            repo_root / "playbook",
            repo_root / "playbook" / "playbook",
            Path.cwd() / "playbook",
            Path.cwd() / "playbook" / "playbook"
        ])
        
        for cand in candidates:
            if (cand / "categories").exists() and (cand / "suppliers").exists():
                return cand.resolve()
                
        raise FileNotFoundError(f"Could not find playbook root directory in candidates: {candidates}")

    @classmethod
    def load_from_disk(cls, playbook_dir: Optional[str] = None) -> "Playbook":
        root = cls.find_playbook_root(playbook_dir)
        categories: Dict[str, CategorySpec] = {}
        category_title_to_slug: Dict[str, str] = {}
        
        # 1. Parse categories
        cat_files = glob.glob(str(root / "categories" / "*.md"))
        for fpath in cat_files:
            slug = Path(fpath).stem
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
                
            name_m = re.search(r"#\s*Category:\s*(.*)", content)
            name = name_m.group(1).strip() if name_m else slug
            
            unit_m = re.search(r"\*\*Normalized unit:\*\*\s*(.*)", content)
            unit = unit_m.group(1).strip() if unit_m else ""
            
            gst_m = re.search(r"\*\*GST rate:\*\*\s*(\d+)%", content)
            gst_rate = float(gst_m.group(1)) / 100.0 if gst_m else 0.18
            
            target_m = re.search(r"\*\*Target price:\*\*\s*([^\n\r]+)", content)
            target = parse_inr(target_m.group(1)) if target_m else 0.0
            
            walkaway_m = re.search(r"\*\*Walk-away price:\*\*\s*([^\n\r]+)", content)
            walkaway = parse_inr(walkaway_m.group(1)) if walkaway_m else 0.0
            
            r_m = re.search(r"\*\*Negotiation rounds\s*\(R\):\*\*\s*(\d+)", content)
            rounds = int(r_m.group(1)) if r_m else 3
            
            beta_m = re.search(r"\*\*Concession exponent\s*\(β\):\*\*\s*(\d+)", content)
            beta = int(beta_m.group(1)) if beta_m else 1
            
            limit_m = re.search(r"\*\*Approval limit:\*\*\s*([^\n\r]+)", content)
            approval_limit = parse_inr(limit_m.group(1)) if limit_m else 0.0
            
            pack_m = re.search(r"\*\*Pack conversion:\*\*\s*(.*)", content)
            pack_size = 1
            if pack_m:
                pack_text = pack_m.group(1)
                if "holds 4" in pack_text:
                    pack_size = 4
                elif "10 reams" in pack_text:
                    pack_size = 10

            is_sub = any(s in unit.lower() for s in ["month", "year", "seat", "server", "guard", "site"])
            period = None
            if "year" in unit.lower():
                period = "yearly"
            elif "month" in unit.lower():
                period = "monthly"

            cat_spec = CategorySpec(
                slug=slug,
                name=name,
                normalized_unit=unit,
                gst_rate=gst_rate,
                target=target,
                walkaway=walkaway,
                rounds=rounds,
                beta=beta,
                approval_limit=approval_limit,
                pack_size=pack_size,
                is_subscription=is_sub,
                normalized_period=period
            )
            categories[slug] = cat_spec
            category_title_to_slug[name.lower()] = slug
            category_title_to_slug[slug.lower()] = slug
            # Normalized alphanumeric
            clean_title = re.sub(r"[^a-z0-9]", "", name.lower())
            category_title_to_slug[clean_title] = slug

        # 2. Parse amendments
        amendments: List[AmendmentSpec] = []
        amd_files = glob.glob(str(root / "amendments" / "*.md"))
        for fpath in amd_files:
            amd_id = Path(fpath).stem
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
                
            title_m = re.search(r"#\s*(AMD-\d+):\s*(.*)", content)
            if title_m:
                amd_id = title_m.group(1).strip()
                cat_raw = title_m.group(2).strip()
            else:
                cat_raw = ""
                
            cat_slug = None
            for key, cslug in category_title_to_slug.items():
                if key in cat_raw.lower() or cat_raw.lower() in key:
                    cat_slug = cslug
                    break
            if not cat_slug:
                clean_raw = re.sub(r"[^a-z0-9]", "", cat_raw.lower())
                cat_slug = category_title_to_slug.get(clean_raw, cat_raw.lower())

            eff_m = re.search(r"\*\*Effective from:\*\*\s*([\d-]+)", content)
            eff_date = eff_m.group(1).strip() if eff_m else ""

            field_name = None
            if "walk-away price" in content:
                field_name = "walkaway"
            elif "target price" in content:
                field_name = "target"
            elif "approval limit" in content:
                field_name = "approval_limit"

            val_m = re.search(r"is now [₹Rs\.\s]*([0-9,]+)", content)
            new_val = parse_inr(val_m.group(1)) if val_m else 0.0

            if cat_slug and field_name and eff_date:
                amendments.append(
                    AmendmentSpec(
                        id=amd_id,
                        category_slug=cat_slug,
                        effective_date=eff_date,
                        field_name=field_name,
                        new_value=new_val
                    )
                )

        # Sort amendments chronologically
        amendments.sort(key=lambda a: a.effective_date)

        # 3. Parse suppliers
        suppliers: Dict[str, SupplierSpec] = {}
        sup_files = glob.glob(str(root / "suppliers" / "*.md"))
        for fpath in sup_files:
            slug = Path(fpath).stem
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
                
            sup_m = re.search(r"#\s*Supplier:\s*(.*)", content)
            sup_name = sup_m.group(1).strip() if sup_m else slug
            
            status_m = re.search(r"\*\*Status:\*\*\s*([A-Za-z]+)", content)
            raw_status = status_m.group(1).upper() if status_m else "APPROVED"
            if "BLACKLIST" in raw_status:
                status = "BLACKLISTED"
            elif "PROBATION" in raw_status:
                status = "PROBATION"
            else:
                status = "APPROVED"

            rates = {}
            caps = {}

            rate_m = re.search(r"invoices in ([A-Z]{3}) are converted at [₹Rs\.\s]*([\d\.]+)", content)
            if rate_m:
                rates[rate_m.group(1)] = float(rate_m.group(2))

            cap_m = re.search(r"price cap for ([A-Za-z\s]+) of [₹Rs\.\s]*([0-9,]+)", content)
            if cap_m:
                cat_raw = cap_m.group(1).strip()
                cap_slug = None
                for key, cslug in category_title_to_slug.items():
                    if key in cat_raw.lower() or cat_raw.lower() in key:
                        cap_slug = cslug
                        break
                if not cap_slug:
                    clean_raw = re.sub(r"[^a-z0-9]", "", cat_raw.lower())
                    cap_slug = category_title_to_slug.get(clean_raw, cat_raw.lower())
                caps[cap_slug] = parse_inr(cap_m.group(2))

            spec = SupplierSpec(
                name=sup_name,
                slug=slug,
                status=status,
                exchange_rates=rates,
                price_caps=caps
            )
            suppliers[sup_name] = spec
            suppliers[slug] = spec
            suppliers[sup_name.lower()] = spec

        return cls(categories, amendments, suppliers, category_title_to_slug)

    def get_category_spec(self, category_name_or_slug: str) -> CategorySpec:
        raw = category_name_or_slug.strip().lower()
        slug = self.category_title_to_slug.get(raw, raw)
        if slug not in self.categories:
            clean = re.sub(r"[^a-z0-9]", "", raw)
            slug = self.category_title_to_slug.get(clean, clean)
        if slug not in self.categories:
            raise KeyError(f"Unknown category: '{category_name_or_slug}'")
        return self.categories[slug]

    def get_supplier_spec(self, supplier_name: str) -> SupplierSpec:
        raw = supplier_name.strip()
        if raw in self.suppliers:
            return self.suppliers[raw]
        low = raw.lower()
        if low in self.suppliers:
            return self.suppliers[low]
        # Fallback default approved supplier
        return SupplierSpec(name=supplier_name, slug=low.replace(" ", "-"), status="APPROVED")

    def get_supplier_status(self, supplier_name: str) -> str:
        return self.get_supplier_spec(supplier_name).status

    def get_exchange_rate(self, supplier_name: str, currency: str) -> Optional[float]:
        """Returns effective exchange rate to INR, or None if currency is not recognized."""
        curr = currency.upper().strip()
        sup = self.get_supplier_spec(supplier_name)
        if curr in sup.exchange_rates:
            return sup.exchange_rates[curr]
        if curr in DEFAULT_TABLE_RATES:
            return DEFAULT_TABLE_RATES[curr]
        return None

    def get_effective_category(
        self,
        category_name_or_slug: str,
        thread_date: str,
        supplier_name: str
    ) -> EffectiveCategory:
        """Computes effective target, walkaway, rounds, beta, approval limit,
        applying chronological dated amendments and supplier contract overrides.
        """
        cat_spec = self.get_category_spec(category_name_or_slug)
        sup_spec = self.get_supplier_spec(supplier_name)
        
        target = cat_spec.target
        walkaway = cat_spec.walkaway
        approval_limit = cat_spec.approval_limit
        rounds = cat_spec.rounds
        beta = cat_spec.beta
        
        active_amends = []
        for amd in self.amendments:
            if amd.category_slug == cat_spec.slug and amd.effective_date <= thread_date:
                if amd.field_name == "target":
                    target = amd.new_value
                elif amd.field_name == "walkaway":
                    walkaway = amd.new_value
                elif amd.field_name == "approval_limit":
                    approval_limit = amd.new_value
                active_amends.append(f"{amd.id}:{amd.field_name}={amd.new_value}")

        # Supplier contract price cap supersedes both category walkaway and amendments
        if cat_spec.slug in sup_spec.price_caps:
            walkaway = sup_spec.price_caps[cat_spec.slug]
            active_amends.append(f"SUPPLIER_CAP:{walkaway}")

        is_prob = (sup_spec.status == "PROBATION")
        
        return EffectiveCategory(
            slug=cat_spec.slug,
            target=target,
            walkaway=walkaway,
            rounds=rounds,
            beta=beta,
            approval_limit=approval_limit,
            gst_rate=cat_spec.gst_rate,
            pack_size=cat_spec.pack_size,
            is_subscription=cat_spec.is_subscription,
            normalized_period=cat_spec.normalized_period,
            is_probation=is_prob,
            effective_walkaway=walkaway,
            active_amendments=active_amends
        )

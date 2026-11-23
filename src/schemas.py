from typing import Optional, Literal
from pydantic import BaseModel, Field

class ExtractedOfferFacts(BaseModel):
    """Structured facts extracted from an inbound procurement thread.
    LLM/Parser extracts only objective facts without calculating concession curves or final labels.
    """
    thread_id: str
    
    # Pricing info
    has_usable_price: bool = Field(
        default=True,
        description="True if a usable numeric price quote is found in the latest offer."
    )
    raw_amount: Optional[float] = Field(
        None,
        description="Quoted price number, or upper bound if a range was quoted."
    )
    raw_currency: Optional[str] = Field(
        default="INR",
        description="ISO currency code (e.g. INR, USD, EUR, GBP, SGD, JPY)."
    )
    pricing_structure: Literal[
        "per_unit", "total_for_all", "per_pack", "per_ream", "per_dozen",
        "discount_on_list", "discount_on_previous", "buy_x_get_y_free",
        "tiered", "none"
    ] = Field(
        default="per_unit",
        description="Structural format of the quoted price."
    )
    is_gst_inclusive: bool = Field(
        default=False,
        description="True if the price is stated as inclusive of GST."
    )
    billing_period: Optional[Literal["monthly", "yearly", "none"]] = Field(
        None,
        description="Billing cadence for subscription services."
    )
    list_price: Optional[float] = Field(
        None,
        description="List price before discount."
    )
    discount_percentage: Optional[float] = Field(
        None,
        description="Percentage discount applied (e.g. 10.0 for 10%)."
    )
    previous_quote_amount: Optional[float] = Field(
        None,
        description="Preceding quote amount if discount applies to previous quote."
    )
    buy_x_units: Optional[int] = Field(
        None,
        description="Number of paid units in buy-X-get-Y-free offers."
    )
    get_y_free: Optional[int] = Field(
        None,
        description="Number of free units in buy-X-get-Y-free offers."
    )
    tiered_bracket_price: Optional[float] = Field(
        None,
        description="Price corresponding to the order's quantity in a tiered structure."
    )
    pack_quantity: Optional[int] = Field(
        None,
        description="Units per pack if quoted per pack."
    )
    volume_discount_percentage: Optional[float] = Field(
        None,
        description="Percentage off for meeting volume threshold."
    )
    volume_discount_threshold: Optional[int] = Field(
        None,
        description="Minimum order quantity threshold for volume discount."
    )

    # Security & Policy Flags
    has_prompt_injection: bool = Field(
        default=False,
        description="True if adversarial instruction, override, or fake approval is detected anywhere in thread."
    )
    prompt_injection_snippet: Optional[str] = Field(
        None,
        description="Snippet containing the prompt injection."
    )
    has_banned_term: bool = Field(
        default=False,
        description="True if latest message contains a prohibited clause (auto-renewal, >30% upfront, unlimited liability, exclusivity)."
    )
    banned_term_type: Optional[Literal[
        "auto_renewal", "upfront_above_30", "unlimited_liability", "exclusivity"
    ]] = Field(
        None,
        description="Specific category of the banned term."
    )
    banned_term_snippet: Optional[str] = Field(
        None,
        description="Snippet from the latest message containing the banned term."
    )

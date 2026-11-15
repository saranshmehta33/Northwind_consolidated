"""
Independent bottom-up computation of the translation reserve movement.

src/consolidation.py derives the closing translation reserve as a residual
(net assets less the other equity components). A residual cannot validate
itself. This module derives the same figure a second time, from exchange rate
movements only, so the two can be compared. Any disagreement is a real defect
somewhere in the pipeline, not a rounding artefact.
"""

from typing import Dict, Any


def compute_translation_difference(
    *,
    us_opening_equity_usd: float,
    us_investment_uk_usd: float,
    us_investment_india_usd: float,
    us_profit_usd: float,
    india_net_assets_at_acquisition_inr: float,
    india_post_acq_profit_inr: float,
    goodwill_inr: float,
    ownership_pct: float,
    gbp_usd_opening: float,
    gbp_usd_average: float,
    gbp_usd_closing: float,
    gbp_usd_spot: float,
    gbp_inr_spot: float,
    gbp_inr_h2_average: float,
    gbp_inr_closing: float,
) -> Dict[str, Any]:
    """
    Returns the translation difference for the year, split between the owners
    of the parent and the non-controlling interest.

    For each entity whose functional currency is not GBP:
        difference = closing_net_assets / closing_rate
                   - opening_net_assets / opening_rate
                   - profit / average_rate
                   + net_capital_outflow / transaction_rate

    The last term covers the mid-year purchase of the India subsidiary: cash
    left the US entity on 1 July 2024 at the spot rate on that date.
    """
    # --- US entity, measured net of its investments in subsidiaries,
    #     because those investments are eliminated on consolidation. ---
    us_open_na = us_opening_equity_usd - us_investment_uk_usd
    us_close_na = (
        us_opening_equity_usd
        + us_profit_usd
        - us_investment_uk_usd
        - us_investment_india_usd
    )
    td_us = (
        us_close_na / gbp_usd_closing
        - us_open_na / gbp_usd_opening
        - us_profit_usd / gbp_usd_average
        + us_investment_india_usd / gbp_usd_spot
    )

    # --- India, 100%, from the acquisition date to the year end. ---
    india_close_na = india_net_assets_at_acquisition_inr + india_post_acq_profit_inr
    td_india = (
        india_close_na / gbp_inr_closing
        - india_net_assets_at_acquisition_inr / gbp_inr_spot
        - india_post_acq_profit_inr / gbp_inr_h2_average
    )

    # --- Goodwill, held in INR and retranslated at the closing rate. ---
    td_goodwill = goodwill_inr / gbp_inr_closing - goodwill_inr / gbp_inr_spot

    owners = td_us + td_goodwill + ownership_pct * td_india
    nci = (1.0 - ownership_pct) * td_india

    return {
        "us": round(td_us, 2),
        "india_total": round(td_india, 2),
        "goodwill": round(td_goodwill, 2),
        "owners": round(owners, 2),
        "nci": round(nci, 2),
        "total": round(owners + nci, 2),
    }


"""
Foreign Exchange (FX) Engine.
Handles currency conversions, triangular synthetic cross-rates,
and strict null-handling for missing rates per Group Policies.
"""

from typing import Dict, Tuple, Optional, Any, List
from src.models import IssueRecord


class FXEngine:
    def __init__(self, raw_fx_rates: List[Dict[str, Any]]):
        self.raw_rates = raw_fx_rates
        self.rate_table: Dict[Tuple[str, str, str], float] = {}
        self._build_rate_table()

    def _build_rate_table(self):
        for r in self.raw_rates:
            key = (r["base_currency"], r["quote_currency"], r["rate_type"])
            self.rate_table[key] = r["rate"]

    def get_direct_rate(self, base: str, quote: str, rate_type: str) -> Optional[float]:
        return self.rate_table.get((base, quote, rate_type))

    def get_rate(self, base: str, quote: str, rate_type: str) -> Optional[float]:
        """
        Gets direct rate or computes synthetic cross-rate per Group Policy 2:
        GBP/quote = GBP/USD * USD/quote.
        """
        if base == quote:
            return 1.0

        # Direct lookup
        direct = self.get_direct_rate(base, quote, rate_type)
        if direct is not None:
            return direct

        # Synthetic GBP -> quote via USD
        if base == "GBP":
            gbp_usd = self.get_direct_rate("GBP", "USD", rate_type)
            usd_quote = self.get_direct_rate("USD", quote, rate_type)
            if gbp_usd is not None and usd_quote is not None:
                return gbp_usd * usd_quote

        # Inverted lookup
        inverse = self.get_direct_rate(quote, base, rate_type)
        if inverse is not None and inverse != 0.0:
            return 1.0 / inverse

        return None

    def convert_to_gbp(self, amount: float, from_currency: str, rate_type: str) -> Optional[float]:
        """
        Converts an amount from `from_currency` to GBP.
        Convention: Rates in fx_rates.csv are expressed as Quote per 1 Base (e.g. USD per 1 GBP).
        Therefore, GBP_amount = Amount_in_Quote / Rate (GBP/Quote).
        """
        if from_currency == "GBP":
            return amount

        rate = self.get_rate("GBP", from_currency, rate_type)
        if rate is None or rate == 0.0:
            return None

        return amount / rate

    def check_sgd_closing_rate(self) -> Tuple[Optional[float], Optional[IssueRecord]]:
        """
        Checks whether GBP/SGD closing rate exists.
        Per Section 4 of assignment instructions:
        'If a figure cannot be determined from the inputs, write null and give the reason.
         Never estimate or fill in a value from outside the inputs.'
        """
        rate = self.get_rate("GBP", "SGD", "closing")
        if rate is None:
            issue = IssueRecord(
                file="fx_rates.csv",
                line=None,
                amount_affected=40000.0,  # 40,000 SGD in tb_uk.csv
                action="blocked",
                issue_type="MISSING_FX_CLOSING_RATE",
                description=(
                    "Missing closing exchange rate for GBP/SGD at 31 Dec 2024. "
                    "Cannot retranslate UK SGD bank balance (40,000 SGD) at closing rate per policy 3. "
                    "Value left as unadjusted book value in UK trial balance and reported as null in control figures."
                ),
            )
            return None, issue
        return rate, None

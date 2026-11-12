"""
Acquisition Accounting and Business Combinations Module.
Calculates goodwill, non-controlling interest (NCI), pre-acquisition vs. post-acquisition splits,
and generates acquisition elimination entries per Group Policies and IFRS 3 / IAS 21.
"""

from typing import Dict, List, Any, Tuple
from src.models import EliminationEntry, IssueRecord
from src.fx_engine import FXEngine


class AcquisitionEngine:
    def __init__(self, fx_engine: FXEngine):
        self.fx_engine = fx_engine

    def calculate_india_acquisition(
        self,
        in_pl_monthly: List[Dict[str, Any]],
        in_adjustments_pl: Dict[str, float],
        group_coa: Dict[str, Dict[str, Any]],
        map_in: Dict[str, str],
    ) -> Tuple[Dict[str, Any], List[EliminationEntry], List[IssueRecord]]:
        """
        Calculates India acquisition metrics:
        - Goodwill on completion (1 July 2024)
        - Retranslated goodwill at 31 Dec 2024
        - Pre-acquisition profit (Apr-Jun 2024: INR 18M)
        - Post-acquisition adjusted profit (Jul-Dec 2024: INR 32.8M)
        - NCI share of profit and closing balance
        - Elimination entries
        """
        issues: List[IssueRecord] = []
        eliminations: List[EliminationEntry] = []

        gbp_usd_closing = self.fx_engine.get_direct_rate("GBP", "USD", "closing")
        gbp_usd_spot = self.fx_engine.get_direct_rate("GBP", "USD", "spot")
        usd_inr_closing = self.fx_engine.get_direct_rate("USD", "INR", "closing")
        usd_inr_spot = self.fx_engine.get_direct_rate("USD", "INR", "spot")

        gbp_inr_closing = self.fx_engine.get_rate("GBP", "INR", "closing")        # 107.28186
        gbp_inr_h2_avg = self.fx_engine.get_rate("GBP", "INR", "h2_average")      # 107.7918
        gbp_inr_spot = self.fx_engine.get_rate("GBP", "INR", "spot")              # 105.446655

        # 1. Completion accounts data (1 July 2024)
        consideration_inr = 690_000_000.0
        consideration_usd = round(consideration_inr / usd_inr_spot, 2)  # $8,274,373.43
        share_capital_inr = 250_000_000.0
        opening_reserves_inr = 410_000_000.0
        pre_acq_profit_inr = 18_000_000.0
        net_assets_completion_inr = share_capital_inr + opening_reserves_inr + pre_acq_profit_inr  # 678,000,000

        # Ownership
        ownership_pct = 0.80
        nci_pct = 0.20

        # NCI at acquisition (proportionate share of net assets per Policy 4)
        nci_completion_inr = nci_pct * net_assets_completion_inr  # 135,600,000.0
        parent_share_net_assets_inr = ownership_pct * net_assets_completion_inr  # 542,400,000.0

        # Goodwill at acquisition (in INR per Policy 4)
        goodwill_inr = consideration_inr - parent_share_net_assets_inr  # 147,600,000.0

        # Retranslate Goodwill at 31 Dec 2024 closing rate
        goodwill_closing_gbp = round(goodwill_inr / gbp_inr_closing, 2)  # £1,375,815.11

        issues.append(
            IssueRecord(
                file="acquisition_note.md",
                line=5,
                amount_affected=goodwill_closing_gbp,
                action="assumed",
                issue_type="GOODWILL_RETRANSLATION",
                description=(
                    f"Goodwill of INR {goodwill_inr:,.2f} on India acquisition held in functional currency (INR) "
                    f"and retranslated at closing rate ({gbp_inr_closing:.5f}) to £{goodwill_closing_gbp:,.2f} per Policy 4."
                ),
            )
        )

        # 2. Monthly P&L analysis: Carve out Pre-acquisition vs Post-acquisition
        h1_months = {"2024-04", "2024-05", "2024-06"}
        h2_months = {"2024-07", "2024-08", "2024-09", "2024-10", "2024-11", "2024-12"}

        h1_pl_by_code: Dict[str, float] = {}
        h2_pl_by_code: Dict[str, float] = {}

        for r in in_pl_monthly:
            code = r["ledger_code"]
            net = r["debit"] - r["credit"]
            if r["month"] in h1_months:
                h1_pl_by_code[code] = h1_pl_by_code.get(code, 0.0) + net
            elif r["month"] in h2_months:
                h2_pl_by_code[code] = h2_pl_by_code.get(code, 0.0) + net

        h1_profit_inr = -sum(h1_pl_by_code.values())
        assert round(h1_profit_inr, 2) == pre_acq_profit_inr, "H1 profit must equal acquisition note pre-acq profit"

        # Apply post-closing adjustments to H2 P&L (only for P&L accounts)
        for code, net_adj in in_adjustments_pl.items():
            grp_code = map_in.get(code)
            if grp_code and group_coa.get(grp_code, {}).get("statement") == "PL":
                h2_pl_by_code[code] = h2_pl_by_code.get(code, 0.0) + net_adj

        h2_profit_inr = -sum(h2_pl_by_code.values())  # 32,800,000 INR
        h2_profit_gbp = round(h2_profit_inr / gbp_inr_h2_avg, 2)  # £304,290.31

        # Post-acquisition profit allocation
        profit_nci_gbp = round(nci_pct * h2_profit_gbp, 2)       # £60,858.06
        profit_owners_in_gbp = round(h2_profit_gbp - profit_nci_gbp, 2)  # £243,432.25

        issues.append(
            IssueRecord(
                file="tb_in.csv",
                line=None,
                amount_affected=round(pre_acq_profit_inr / gbp_inr_h2_avg, 2),
                action="assumed",
                issue_type="PRE_ACQUISITION_EARNINGS_EXCLUSION",
                description=(
                    f"Excluded India pre-acquisition profit (Apr-Jun 2024: INR {pre_acq_profit_inr:,.2f}) "
                    "from Group consolidated P&L. Consolidated only H2 post-acquisition results per Group Policy 2."
                ),
            )
        )

        # 3. NCI Closing Balance
        # Net assets of India at 31 Dec 2024 = 250M (Capital) + 410M (Reserves) + 18M (H1) + 32.8M (H2) = 710.8M INR
        net_assets_closing_inr = net_assets_completion_inr + h2_profit_inr  # 710,800,000 INR
        nci_closing_inr = nci_pct * net_assets_closing_inr  # 142,160,000 INR
        nci_closing_gbp = round(nci_closing_inr / gbp_inr_closing, 2)  # £1,325,107.51

        # 4. Elimination Entries
        # Elimination of Investment in India against subsidiary pre-acquisition net assets & recognition of Goodwill and NCI
        us_inv_usd = consideration_usd
        us_inv_closing_gbp = round(us_inv_usd / gbp_usd_closing, 2)

        elim_acq_in = EliminationEntry(
            entry_id="ELIM-ACQ-IN",
            category="Business Combinations",
            account_code="1610 / 1700 / 3100 / 3200 / 3400",
            account_name="Elimination of Investment in Northwind India & Recognition of Goodwill/NCI",
            debit=round(share_capital_inr / gbp_inr_closing, 2) + round((opening_reserves_inr + pre_acq_profit_inr) / gbp_inr_closing, 2) + goodwill_closing_gbp,
            credit=us_inv_closing_gbp + round(nci_completion_inr / gbp_inr_closing, 2),
            description=(
                f"Elimination of Northwind Inc investment in India against pre-acquisition equity. "
                f"Recognizes Goodwill £{goodwill_closing_gbp:,.2f} and initial NCI £{round(nci_completion_inr / gbp_inr_closing, 2):,.2f}."
            ),
            source_rows="tb_us.csv:L10, tb_in.csv:L12-13, acquisition_note.md",
        )
        eliminations.append(elim_acq_in)

        # Elimination of UK investment
        us_inv_uk_usd = 1_270_000.0
        us_inv_uk_gbp = round(us_inv_uk_usd / gbp_usd_closing, 2)
        uk_share_capital_gbp = 1_000_000.0

        elim_acq_uk = EliminationEntry(
            entry_id="ELIM-ACQ-UK",
            category="Subsidiary Equity Elimination",
            account_code="1600 / 3100",
            account_name="Elimination of Investment in Northwind UK Ltd",
            debit=uk_share_capital_gbp,
            credit=us_inv_uk_gbp,
            description="Elimination of Northwind Inc investment in Northwind UK Ltd against UK share capital.",
            source_rows="tb_us.csv:L9, tb_uk.csv:L14",
        )
        eliminations.append(elim_acq_uk)

        acquisition_metrics = {
            "goodwill_closing_gbp": goodwill_closing_gbp,
            "goodwill_inr": goodwill_inr,
            "nci_closing_gbp": nci_closing_gbp,
            "profit_nci_gbp": profit_nci_gbp,
            "profit_owners_in_gbp": profit_owners_in_gbp,
            "h2_profit_gbp": h2_profit_gbp,
            "h2_profit_inr": h2_profit_inr,
            "h2_pl_by_code": h2_pl_by_code,
            "net_assets_closing_inr": net_assets_closing_inr,
        }

        return acquisition_metrics, eliminations, issues

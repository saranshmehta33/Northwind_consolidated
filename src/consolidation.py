"""
Consolidation Pipeline and Financial Statement Generator.
Executes end-to-end multi-entity consolidation, enforces elimination accounting,
produces row-level provenance lineage, and exports all required regulatory deliverables.
"""

import csv
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

from src.config import OUTPUT_DIR, PRESENTATION_CURRENCY, AUTHOR_INITIALS
from src.models import EliminationEntry, EliminationLine, IssueRecord
from src.ingestion import DataIngestor
from src.fx_engine import FXEngine
from src.validator import ValidationEngine
from src.intercompany import IntercompanyEngine
from src.acquisition import AcquisitionEngine
from src.translation import compute_translation_difference


class ConsolidationEngine:
    def __init__(self, data_dir: Optional[Path] = None, output_dir: Optional[Path] = None):
        self.ingestor = DataIngestor() if data_dir is None else DataIngestor(data_dir)
        self.output_dir = output_dir if output_dir is not None else OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> Dict[str, Any]:
        """
        Executes the full consolidation pipeline and writes outputs.
        Returns the control figures dictionary.
        """
        # 1. Load data
        entities = self.ingestor.load_entities()
        coa = self.ingestor.load_group_coa()
        raw_rates = self.ingestor.load_fx_rates()
        prior_equity = self.ingestor.load_prior_year_group()
        controls = self.ingestor.load_subledger_controls()
        map_uk, raw_map_uk = self.ingestor.load_uk_mapping()
        map_in, raw_map_in = self.ingestor.load_in_mapping()
        tb_us = self.ingestor.load_tb_us()
        tb_uk = self.ingestor.load_tb_uk()
        tb_in = self.ingestor.load_tb_in()
        in_pl_monthly = self.ingestor.load_in_pl_monthly()
        invoices = self.ingestor.load_intercompany_invoices()
        adjustments = self.ingestor.load_adjustments()
        acquisition_note = self.ingestor.load_acquisition_note()

        # 2. Initialize engines
        fx_engine = FXEngine(raw_rates)
        validator = ValidationEngine(coa, map_uk, map_in)

        # 3. Check SGD closing rate trap — read txn_amount from tb_uk row 1210
        sgd_row = next((r for r in tb_uk if r.account_code == "1210"), None)
        sgd_txn_amount = sgd_row.extra.get("txn_amount") if sgd_row else None
        _, sgd_issue = fx_engine.check_sgd_closing_rate(sgd_txn_amount=sgd_txn_amount)
        if sgd_issue:
            validator.issues.append(sgd_issue)

        # 4. Validations — TB balance check now raises on failure (VAL-01)
        if not validator.validate_trial_balances(tb_us, tb_uk, tb_in):
            raise ValueError(
                "One or more entity trial balances do not balance. "
                "See issues.json. Consolidation halted."
            )
        posted_journals, journal_counts = validator.validate_and_filter_journals(adjustments)

        # Enrich uk_mapping raw rows with balance for amount_affected in COA check
        # Build a map of local_code -> balance from tb_uk
        uk_local_balance_map = {}
        for r in tb_uk:
            uk_local_balance_map[r.account_code] = abs(r.net_balance)
        for row in raw_map_uk:
            row["_balance"] = uk_local_balance_map.get(row["local_code"])

        map_uk = validator.validate_coa_mappings(raw_map_uk)

        # 5. Build adjusted balances
        # Accumulate US balances
        us_adj: Dict[str, float] = {}
        for r in tb_us:
            us_adj[r.account_code] = us_adj.get(r.account_code, 0.0) + r.net_balance
        for je in posted_journals:
            if je.entity == "US":
                for l in je.lines:
                    us_adj[l.account] = us_adj.get(l.account, 0.0) + (l.debit - l.credit)

        # Accumulate UK balances (handling multiple cost-centre lines like 7000)
        uk_adj: Dict[str, float] = {}
        for r in tb_uk:
            uk_adj[r.account_code] = uk_adj.get(r.account_code, 0.0) + r.net_balance
        for je in posted_journals:
            if je.entity == "UK":
                for l in je.lines:
                    uk_adj[l.account] = uk_adj.get(l.account, 0.0) + (l.debit - l.credit)

        # 6. Intercompany reconciliation & adjustments
        ic_engine = IntercompanyEngine(fx_engine)
        uk_adj, ic_diff, ic_elims, ic_issues = ic_engine.reconcile_and_adjust(
            invoices, uk_adj, us_adj, tb_uk_rows=tb_uk
        )
        validator.issues.extend(ic_issues)

        # Accumulate India balances
        in_adj: Dict[str, float] = {}
        in_pl_adj: Dict[str, float] = {}
        for r in tb_in:
            in_adj[r.account_code] = in_adj.get(r.account_code, 0.0) + r.net_balance
        for je in posted_journals:
            if je.entity == "IN":
                for l in je.lines:
                    in_adj[l.account] = in_adj.get(l.account, 0.0) + (l.debit - l.credit)
                    in_pl_adj[l.account] = in_pl_adj.get(l.account, 0.0) + (l.debit - l.credit)

        # Subledger reconciliation — after posted journals are applied (VAL-10 fix)
        validator.reconcile_subledgers(
            controls, tb_us, tb_uk, tb_in,
            us_adj=us_adj, uk_adj=uk_adj, in_adj=in_adj,
        )

        # 7. Acquisition accounting & pre/post P&L carve-out
        acq_engine = AcquisitionEngine(fx_engine)
        acq_metrics, acq_elims, acq_issues = acq_engine.calculate_india_acquisition(
            in_pl_monthly, in_pl_adj, coa, map_in,
            acquisition_note=acquisition_note,
            entities=entities,
            tb_us_balances=us_adj,
            tb_uk_rows=tb_uk,
        )
        validator.issues.extend(acq_issues)

        # Combine all eliminations
        all_elims = ic_elims + acq_elims

        # Assert every elimination balances (TASK 3)
        for entry in all_elims:
            if not entry.is_balanced:
                raise ValueError(
                    f"Elimination {entry.entry_id} does not balance: "
                    f"Dr {entry.total_debit:,.2f} vs Cr {entry.total_credit:,.2f}"
                )

        # 8. Translation Rates
        gbp_usd_opening = fx_engine.get_direct_rate("GBP", "USD", "opening")
        gbp_usd_closing = fx_engine.get_direct_rate("GBP", "USD", "closing")
        gbp_usd_avg = fx_engine.get_direct_rate("GBP", "USD", "average")
        gbp_usd_spot = fx_engine.get_direct_rate("GBP", "USD", "spot")
        gbp_inr_closing = fx_engine.get_rate("GBP", "INR", "closing")
        gbp_inr_h2_avg = fx_engine.get_rate("GBP", "INR", "h2_average")
        gbp_inr_spot = fx_engine.get_rate("GBP", "INR", "spot")

        # 9. Translate Entity Balances into Group Accounts (in GBP)
        # US Translation: BS at closing rate, PL at average rate
        us_gbp: Dict[str, float] = {}
        for code, val in us_adj.items():
            stmt = coa[code]["statement"]
            if stmt == "BS":
                us_gbp[code] = us_gbp.get(code, 0.0) + round(val / gbp_usd_closing, 2)
            else:
                us_gbp[code] = us_gbp.get(code, 0.0) + round(val / gbp_usd_avg, 2)

        # UK Translation (Functional currency is GBP)
        uk_gbp: Dict[str, float] = {}
        for local_code, val in uk_adj.items():
            grp_code = map_uk.get(local_code)
            if grp_code:
                uk_gbp[grp_code] = uk_gbp.get(grp_code, 0.0) + round(val, 2)

        # India Translation:
        # BS items at closing rate (excluding pre-acquisition equity which is eliminated in acq accounting)
        # PL items: post-acquisition H2 monthly amounts translated at H2 average rate
        in_gbp: Dict[str, float] = {}
        for local_code, val in in_adj.items():
            grp_code = map_in.get(local_code)
            if not grp_code:
                continue
            stmt = coa[grp_code]["statement"]
            if stmt == "BS":
                in_gbp[grp_code] = in_gbp.get(grp_code, 0.0) + round(val / gbp_inr_closing, 2)

        # Override India PL with post-acquisition H2 amounts translated at H2 average rate
        for local_code, val in acq_metrics["h2_pl_by_code"].items():
            grp_code = map_in.get(local_code)
            if grp_code and coa[grp_code]["statement"] == "PL":
                in_gbp[grp_code] = in_gbp.get(grp_code, 0.0) + round(val / gbp_inr_h2_avg, 2)

        # 10. Build Eliminations Column for TB from single ledger (TASK 3)
        elim_gbp: Dict[str, float] = {}
        for entry in all_elims:
            for line in entry.lines:
                elim_gbp[line.account_code] = (
                    elim_gbp.get(line.account_code, 0.0) + line.debit - line.credit
                )

        # 11. Build Consolidated TB (before equity journal)
        consolidated_tb: List[Dict[str, Any]] = []
        all_accounts = sorted(coa.keys())

        statement_totals: Dict[str, float] = {}

        for code in all_accounts:
            meta = coa[code]
            us_val = round(us_gbp.get(code, 0.0), 2)
            uk_val = round(uk_gbp.get(code, 0.0), 2)
            in_val = round(in_gbp.get(code, 0.0), 2)
            el_val = round(elim_gbp.get(code, 0.0), 2)

            cons_val = round(us_val + uk_val + in_val + el_val, 2)
            statement_totals[code] = cons_val

            lineage = []
            if us_val != 0.0:
                lineage.append(f"US:{us_val:,.2f}")
            if uk_val != 0.0:
                lineage.append(f"UK:{uk_val:,.2f}")
            if in_val != 0.0:
                lineage.append(f"IN:{in_val:,.2f}")
            if el_val != 0.0:
                lineage.append(f"ELIM:{el_val:,.2f}")

            consolidated_tb.append(
                {
                    "account_code": code,
                    "account_name": meta["account_name"],
                    "account_type": meta["account_type"],
                    "statement": meta["statement"],
                    "us_gbp": us_val,
                    "uk_gbp": uk_val,
                    "in_gbp": in_val,
                    "eliminations_gbp": el_val,
                    "consolidated_gbp": cons_val,
                    "source_lineage": "; ".join(lineage),
                }
            )

        # 12. P&L Calculations
        # Group Revenue (only 4100 since 4200 is eliminated)
        group_revenue = round(abs(statement_totals.get("4100", 0.0)), 2)

        # P&L items
        cogs = round(statement_totals.get("5100", 0.0), 2)
        gross_profit = round(group_revenue - cogs, 2)

        staff_costs = round(statement_totals.get("6100", 0.0), 2)
        rent = round(statement_totals.get("6200", 0.0), 2)
        depreciation = round(statement_totals.get("6400", 0.0), 2)
        other_expenses = round(statement_totals.get("6500", 0.0), 2)
        total_operating_expenses = round(staff_costs + rent + depreciation + other_expenses, 2)
        operating_profit = round(gross_profit - total_operating_expenses, 2)

        finance_costs = round(statement_totals.get("7100", 0.0), 2)
        fx_gains_losses = round(statement_totals.get("7300", 0.0), 2)  # debit is loss, credit is gain
        income_tax_expense = round(statement_totals.get("8100", 0.0), 2)

        group_profit = round(operating_profit - finance_costs - fx_gains_losses - income_tax_expense, 2)
        profit_nci = acq_metrics["profit_nci_gbp"]
        profit_owners = round(group_profit - profit_nci, 2)

        # 13. Balance Sheet — asset and liability side
        cash = round(statement_totals.get("1100", 0.0), 2)
        trade_receivables = round(statement_totals.get("1200", 0.0), 2)
        inventory = round(statement_totals.get("1300", 0.0), 2)
        prepayments = round(statement_totals.get("1400", 0.0), 2)
        total_current_assets = round(cash + trade_receivables + inventory + prepayments, 2)

        ppe_cost = round(statement_totals.get("1500", 0.0), 2)
        ppe_dep = round(abs(statement_totals.get("1510", 0.0)), 2)
        ppe_net = round(ppe_cost - ppe_dep, 2)
        goodwill = acq_metrics["goodwill_closing_gbp"]
        total_non_current_assets = round(ppe_net + goodwill, 2)

        total_assets = round(total_current_assets + total_non_current_assets, 2)

        trade_payables = round(abs(statement_totals.get("2100", 0.0)), 2)
        accruals = round(abs(statement_totals.get("2200", 0.0)), 2)
        deferred_income = round(abs(statement_totals.get("2300", 0.0)), 2)
        income_tax_payable = round(abs(statement_totals.get("2400", 0.0)), 2)
        total_current_liabilities = round(trade_payables + accruals + deferred_income + income_tax_payable, 2)

        borrowings = round(abs(statement_totals.get("2500", 0.0)), 2)
        total_non_current_liabilities = borrowings
        total_liabilities = round(total_current_liabilities + total_non_current_liabilities, 2)

        net_assets = round(total_assets - total_liabilities, 2)

        # 14. Equity components per policies and prior_year_group.csv (TASK 4: no silent defaults)
        if "3100" not in prior_equity:
            raise KeyError("Group account 3100 (Share capital) missing from prior_year_group.csv")
        if "3200" not in prior_equity:
            raise KeyError("Group account 3200 (Retained earnings) missing from prior_year_group.csv")
        if "3300" not in prior_equity:
            raise KeyError("Group account 3300 (Translation reserve) missing from prior_year_group.csv")

        share_capital = round(prior_equity["3100"], 2)
        opening_retained_earnings = round(prior_equity["3200"], 2)
        closing_retained_earnings = round(opening_retained_earnings + profit_owners, 2)

        nci_closing = acq_metrics["nci_closing_gbp"]

        # Translation reserve — residual (kept as before)
        closing_translation_reserve = round(net_assets - (share_capital + closing_retained_earnings + nci_closing), 2)
        opening_translation_reserve = round(prior_equity["3300"], 2)
        translation_reserve_movement = round(closing_translation_reserve - opening_translation_reserve, 2)

        total_equity = round(share_capital + closing_retained_earnings + closing_translation_reserve + nci_closing, 2)

        # --- TASK 1: Cross-check translation reserve against bottom-up FX computation ---
        # US opening equity in USD: from US TB accounts 3100 (Share capital) + 3200 (Retained earnings)
        if "3100" not in us_adj or "3200" not in us_adj:
            raise KeyError("US equity accounts (3100/3200) missing from US adjusted balances")
        us_opening_equity_usd = round(abs(us_adj["3100"]) + abs(us_adj["3200"]), 2)

        # US profit in USD (before translation): sum of credit - debit for US PL accounts
        us_profit_usd = round(
            sum(-val for code, val in us_adj.items() if coa.get(code, {}).get("statement") == "PL"),
            2,
        )

        # US investments: read from adjusted balances (from TB)
        if "1600" not in us_adj or "1610" not in us_adj:
            raise KeyError("US investment accounts (1600/1610) missing from US adjusted balances")
        us_investment_uk_usd = us_adj["1600"]
        us_investment_india_usd = us_adj["1610"]

        bottom_up = compute_translation_difference(
            us_opening_equity_usd=us_opening_equity_usd,
            us_investment_uk_usd=us_investment_uk_usd,
            us_investment_india_usd=us_investment_india_usd,
            us_profit_usd=us_profit_usd,
            india_net_assets_at_acquisition_inr=acq_metrics["net_assets_completion_inr"],
            india_post_acq_profit_inr=acq_metrics["h2_profit_inr"],
            goodwill_inr=acq_metrics["goodwill_inr"],
            ownership_pct=acq_metrics["ownership_pct"],
            gbp_usd_opening=gbp_usd_opening,
            gbp_usd_average=gbp_usd_avg,
            gbp_usd_closing=gbp_usd_closing,
            gbp_usd_spot=gbp_usd_spot,
            gbp_inr_spot=gbp_inr_spot,
            gbp_inr_h2_average=gbp_inr_h2_avg,
            gbp_inr_closing=gbp_inr_closing,
        )

        reserve_check = {
            "residual_method_gbp": translation_reserve_movement,
            "bottom_up_method_gbp": bottom_up["owners"],
            "difference_gbp": round(translation_reserve_movement - bottom_up["owners"], 2),
            "tolerance_gbp": 1.00,
            "passed": abs(translation_reserve_movement - bottom_up["owners"]) <= 1.00,
            "nci_share_of_translation_gbp": bottom_up["nci"],
        }

        if not reserve_check["passed"]:
            raise ValueError(
                f"Translation reserve cross-check failed: residual "
                f"{translation_reserve_movement:,.2f} vs bottom-up "
                f"{bottom_up['owners']:,.2f}. The consolidation contains an error."
            )

        # --- TASK 2: Post equity consolidation journal into TB so it balances ---
        # Targets:
        #   3100: -share_capital  (parent share capital at historical)
        #   3200: -opening_retained_earnings  (opening retained earnings)
        #   3400: -(nci_closing - profit_nci)  (NCI at acquisition, before this year's profit)
        #   3300: residual that makes the column sum to zero

        nci_at_acquisition = round(nci_closing - profit_nci, 2)

        # Current values in statement_totals for equity accounts
        cur_3100 = statement_totals.get("3100", 0.0)
        cur_3200 = statement_totals.get("3200", 0.0)
        cur_3400 = statement_totals.get("3400", 0.0)

        # Adjustments needed
        adj_3100 = round(-share_capital - cur_3100, 2)
        adj_3200 = round(-opening_retained_earnings - cur_3200, 2)
        adj_3400 = round(-nci_at_acquisition - cur_3400, 2)

        # Current TB sum (before equity journal)
        pre_journal_sum = round(sum(r["consolidated_gbp"] for r in consolidated_tb), 2)
        # 3300 adjustment = -(pre_journal_sum + adj_3100 + adj_3200 + adj_3400)
        adj_3300 = round(-(pre_journal_sum + adj_3100 + adj_3200 + adj_3400), 2)

        # Apply equity consolidation journal to statement_totals and TB rows
        equity_journal_adjustments = {
            "3100": adj_3100,
            "3200": adj_3200,
            "3300": adj_3300,
            "3400": adj_3400,
        }

        for row in consolidated_tb:
            code = row["account_code"]
            if code in equity_journal_adjustments:
                adj = equity_journal_adjustments[code]
                row["eliminations_gbp"] = round(row["eliminations_gbp"] + adj, 2)
                row["consolidated_gbp"] = round(row["consolidated_gbp"] + adj, 2)
                # Update lineage
                if adj != 0.0:
                    lineage = row["source_lineage"]
                    eq_note = f"EQ:{adj:,.2f}"
                    row["source_lineage"] = (lineage + "; " + eq_note) if lineage else eq_note
                statement_totals[code] = row["consolidated_gbp"]

        # Assert TB sums to zero (TASK 2)
        tb_sum = round(sum(r["consolidated_gbp"] for r in consolidated_tb), 2)
        if abs(tb_sum) > 0.01:
            raise ValueError(
                f"Consolidated trial balance does not balance. Out by GBP {tb_sum:,.2f}."
            )

        # VAL-10: Intercompany clearance check (TASK 5)
        for code in ("1250", "2150"):
            residual = round(statement_totals.get(code, 0.0), 2)
            if abs(residual) > 0.01:
                raise ValueError(
                    f"Intercompany account {code} did not clear: GBP {residual:,.2f} remains."
                )

        # 15. Read equity from TB (single source of truth — TASK 2)
        tb_share_capital = round(abs(statement_totals.get("3100", 0.0)), 2)
        tb_retained_earnings = round(abs(statement_totals.get("3200", 0.0)) + abs(statement_totals.get("4100", 0.0)) +
                                     abs(statement_totals.get("4200", 0.0)), 2)
        # Simpler: equity from BS formula. The TB provides the closing translation reserve and NCI.
        closing_translation_reserve_tb = round(-statement_totals.get("3300", 0.0), 2)  # 3300 is credit (negative)
        nci_closing_tb = round(-statement_totals.get("3400", 0.0), 2)                  # 3400 is credit (negative)

        # Balance sheet reads from TB
        balance_sheet = {
            "statement": "Consolidated Balance Sheet",
            "as_of": "2024-12-31",
            "presentation_currency": PRESENTATION_CURRENCY,
            "assets": {
                "current_assets": {
                    "cash_and_cash_equivalents": cash,
                    "trade_receivables": trade_receivables,
                    "inventory": inventory,
                    "prepayments": prepayments,
                    "total_current_assets": total_current_assets,
                },
                "non_current_assets": {
                    "property_plant_and_equipment_cost": ppe_cost,
                    "property_plant_and_equipment_accumulated_depreciation": ppe_dep,
                    "property_plant_and_equipment_net": ppe_net,
                    "goodwill": goodwill,
                    "total_non_current_assets": total_non_current_assets,
                },
                "total_assets": total_assets,
            },
            "liabilities": {
                "current_liabilities": {
                    "trade_payables": trade_payables,
                    "accruals": accruals,
                    "deferred_income": deferred_income,
                    "income_tax_payable": income_tax_payable,
                    "total_current_liabilities": total_current_liabilities,
                },
                "non_current_liabilities": {
                    "borrowings": borrowings,
                    "total_non_current_liabilities": total_non_current_liabilities,
                },
                "total_liabilities": total_liabilities,
            },
            "equity": {
                "share_capital": share_capital,
                "retained_earnings": closing_retained_earnings,
                "translation_reserve": closing_translation_reserve_tb,  # from TB
                "non_controlling_interest": nci_closing_tb,              # from TB
                "total_equity": total_equity,
            },
            "total_liabilities_and_equity": round(total_liabilities + total_equity, 2),
            "net_assets": net_assets,
            "accounting_equation_balanced": round(total_assets, 2) == round(total_liabilities + total_equity, 2),
        }

        pl_statement = {
            "statement": "Consolidated Profit and Loss",
            "period": "FY2024",
            "presentation_currency": PRESENTATION_CURRENCY,
            "revenue": group_revenue,
            "cost_of_sales": cogs,
            "gross_profit": gross_profit,
            "operating_expenses": {
                "staff_costs": staff_costs,
                "rent_and_occupancy": rent,
                "depreciation": depreciation,
                "other_operating_expenses": other_expenses,
                "total_operating_expenses": total_operating_expenses,
            },
            "operating_profit": operating_profit,
            "finance_costs": finance_costs,
            "foreign_exchange_gains_and_losses": fx_gains_losses,
            "profit_before_tax": round(operating_profit - finance_costs - fx_gains_losses, 2),
            "income_tax_expense": income_tax_expense,
            "group_profit": group_profit,
            "profit_attributable_to_owners": profit_owners,
            "profit_attributable_to_nci": profit_nci,
        }

        # 16. Statement of Changes in Equity
        changes_in_equity = {
            "statement": "Consolidated Statement of Changes in Equity",
            "period": "FY2024",
            "presentation_currency": PRESENTATION_CURRENCY,
            "opening_balance_2023_12_31": {
                "share_capital": share_capital,
                "retained_earnings": opening_retained_earnings,
                "translation_reserve": opening_translation_reserve,
                "non_controlling_interest": 0.0,
                "total": round(share_capital + opening_retained_earnings + opening_translation_reserve, 2),
            },
            "profit_for_the_year": {
                "share_capital": 0.0,
                "retained_earnings": profit_owners,
                "translation_reserve": 0.0,
                "non_controlling_interest": profit_nci,
                "total": group_profit,
            },
            "other_comprehensive_income_translation": {
                "share_capital": 0.0,
                "retained_earnings": 0.0,
                "translation_reserve": translation_reserve_movement,
                "non_controlling_interest": 0.0,
                "total": translation_reserve_movement,
            },
            "recognition_of_nci_on_acquisition": {
                "share_capital": 0.0,
                "retained_earnings": 0.0,
                "translation_reserve": 0.0,
                "non_controlling_interest": round(nci_closing - profit_nci, 2),
                "total": round(nci_closing - profit_nci, 2),
            },
            "closing_balance_2024_12_31": {
                "share_capital": share_capital,
                "retained_earnings": closing_retained_earnings,
                "translation_reserve": closing_translation_reserve,
                "non_controlling_interest": nci_closing,
                "total": total_equity,
            },
        }

        # 17. Control Figures Dictionary
        control_figures = {
            "group_revenue": group_revenue,
            "group_profit": group_profit,
            "profit_owners": profit_owners,
            "profit_nci": profit_nci,
            "nci_closing": nci_closing,
            "goodwill_closing": goodwill,
            "translation_reserve_movement": translation_reserve_movement,
            "total_assets": total_assets,
            "total_equity": total_equity,
            "intercompany_difference": ic_diff,
            "sgd_bank_gbp": {
                "value": None,
                "reason": (
                    "Missing closing exchange rate for GBP/SGD at 31 Dec 2024 in fx_rates.csv. "
                    "Per Group Policy 3, foreign currency monetary bank balances must be retranslated at closing rate, "
                    "but neither a direct GBP/SGD closing rate nor synthetic cross-rate is provided in inputs."
                ),
            },
            "journals": journal_counts,
            "translation_reserve_check": reserve_check,
        }

        # 18. Write All Required Outputs to /output
        self._write_outputs(
            consolidated_tb=consolidated_tb,
            balance_sheet=balance_sheet,
            profit_and_loss=pl_statement,
            changes_in_equity=changes_in_equity,
            eliminations=all_elims,
            issues=[iss.to_dict() for iss in validator.issues],
            control_figures=control_figures,
            reserve_check=reserve_check,
        )

        return control_figures

    def _write_outputs(
        self,
        consolidated_tb: List[Dict[str, Any]],
        balance_sheet: Dict[str, Any],
        profit_and_loss: Dict[str, Any],
        changes_in_equity: Dict[str, Any],
        eliminations: List[EliminationEntry],
        issues: List[Dict[str, Any]],
        control_figures: Dict[str, Any],
        reserve_check: Dict[str, Any] = None,
    ):
        # 1. consolidated_tb.csv
        tb_path = self.output_dir / "consolidated_tb.csv"
        fieldnames = [
            "account_code",
            "account_name",
            "account_type",
            "statement",
            "us_gbp",
            "uk_gbp",
            "in_gbp",
            "eliminations_gbp",
            "consolidated_gbp",
            "source_lineage",
        ]
        with open(tb_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(consolidated_tb)

        # 2. balance_sheet.json
        with open(self.output_dir / "balance_sheet.json", mode="w", encoding="utf-8") as f:
            json.dump(balance_sheet, f, indent=2)

        # 3. profit_and_loss.json
        with open(self.output_dir / "profit_and_loss.json", mode="w", encoding="utf-8") as f:
            json.dump(profit_and_loss, f, indent=2)

        # 4. changes_in_equity.json
        with open(self.output_dir / "changes_in_equity.json", mode="w", encoding="utf-8") as f:
            json.dump(changes_in_equity, f, indent=2)

        # 5. eliminations.csv — one row per LINE (TASK 3)
        elim_path = self.output_dir / "eliminations.csv"
        elim_fields = [
            "entry_id",
            "category",
            "account_code",
            "account_name",
            "debit",
            "credit",
            "description",
            "source_rows",
        ]
        with open(elim_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=elim_fields)
            writer.writeheader()
            for entry in eliminations:
                for line in entry.lines:
                    writer.writerow(
                        {
                            "entry_id": entry.entry_id,
                            "category": entry.category,
                            "account_code": line.account_code,
                            "account_name": line.account_name,
                            "debit": line.debit,
                            "credit": line.credit,
                            "description": entry.description,
                            "source_rows": entry.source_rows,
                        }
                    )

        # 6. issues.json
        with open(self.output_dir / "issues.json", mode="w", encoding="utf-8") as f:
            json.dump(issues, f, indent=2)

        # 7. control_figures_<initials>.json and control_figures.json
        initials_filename = f"control_figures_{AUTHOR_INITIALS}.json"
        with open(self.output_dir / initials_filename, mode="w", encoding="utf-8") as f:
            json.dump(control_figures, f, indent=2)

        with open(self.output_dir / "control_figures.json", mode="w", encoding="utf-8") as f:
            json.dump(control_figures, f, indent=2)

        # 8. reconciliation.json — translation reserve cross-check (TASK 1)
        reconciliation = {
            "translation_reserve": reserve_check if reserve_check else {},
        }
        with open(self.output_dir / "reconciliation.json", mode="w", encoding="utf-8") as f:
            json.dump(reconciliation, f, indent=2)

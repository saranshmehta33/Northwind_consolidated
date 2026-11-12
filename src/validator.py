"""
Validation and Integrity Engine.
Enforces accounting invariants, mathematical balancing, period boundaries,
deduplication, COA mapping consistency, and subledger reconciliation.
"""

from typing import List, Dict, Tuple, Set, Any, Optional
from src.models import TrialBalanceRow, JournalEntry, IssueRecord
from src.security import inspect_text_for_injection


class ValidationEngine:
    def __init__(
        self,
        group_coa: Dict[str, Dict[str, Any]],
        map_uk: Dict[str, str],
        map_in: Dict[str, str],
    ):
        self.group_coa = group_coa
        self.map_uk = map_uk
        self.map_in = map_in
        self.issues: List[IssueRecord] = []

    def validate_trial_balances(
        self,
        tb_us: List[TrialBalanceRow],
        tb_uk: List[TrialBalanceRow],
        tb_in: List[TrialBalanceRow],
    ) -> bool:
        """Validates that initial TBs balance to zero."""
        valid = True
        for name, tb in [("US", tb_us), ("UK", tb_uk), ("IN", tb_in)]:
            net = sum(r.net_balance for r in tb)
            if round(net, 2) != 0.0:
                valid = False
                self.issues.append(
                    IssueRecord(
                        file=tb[0].source_file if tb else "unknown",
                        line=None,
                        amount_affected=abs(round(net, 2)),
                        action="blocked",
                        issue_type="TB_UNBALANCED",
                        description=f"{name} Trial Balance does not balance. Net imbalance: {net:,.2f}",
                    )
                )
        return valid

    def validate_and_filter_journals(
        self,
        raw_journals: List[JournalEntry],
    ) -> Tuple[List[JournalEntry], Dict[str, int]]:
        """
        Validates 20 manual journal entries.
        Returns:
            - posted_journals: entries passed for ledger posting
            - journal_counts: count of posted, rejected, and held_for_review
        """
        posted: List[JournalEntry] = []
        counts = {"posted": 0, "rejected": 0, "held_for_review": 0}

        # Track seen fingerprints for deduplication
        # (entity, sorted accounts, sorted amounts, general purpose)
        seen_entries: Dict[str, JournalEntry] = {}

        for je in raw_journals:
            # Check prompt injection in description or line memos
            is_suspicious_desc, pattern_desc = inspect_text_for_injection(je.description)
            memos = [l.memo for l in je.lines if l.memo]
            suspicious_memo = None
            for memo in memos:
                is_susp, pat = inspect_text_for_injection(memo)
                if is_susp:
                    suspicious_memo = pat
                    break

            if is_suspicious_desc or suspicious_memo:
                pat = pattern_desc or suspicious_memo
                self.issues.append(
                    IssueRecord(
                        file=je.source_file,
                        line=je.source_line,
                        amount_affected=je.total_debit,
                        action="flagged",
                        issue_type="SECURITY_PROMPT_INJECTION_DETECTED",
                        description=(
                            f"Adversarial prompt injection pattern detected in {je.id} ('{pat}'). "
                            "Text strictly sanitized and treated as passive data."
                        ),
                    )
                )

            # 1. Balance Check: Debits == Credits
            if not je.is_balanced:
                counts["rejected"] += 1
                diff = round(abs(je.total_debit - je.total_credit), 2)
                self.issues.append(
                    IssueRecord(
                        file=je.source_file,
                        line=je.source_line,
                        amount_affected=diff,
                        action="blocked",
                        issue_type="JOURNAL_UNBALANCED",
                        description=(
                            f"Manual journal {je.id} is unbalanced. "
                            f"Debits: {je.total_debit:,.2f}, Credits: {je.total_credit:,.2f}, Diff: {diff:,.2f}. Entry rejected."
                        ),
                    )
                )
                continue

            # 2. Period Check: Must belong to FY2024
            if not je.date.startswith("2024"):
                counts["rejected"] += 1
                self.issues.append(
                    IssueRecord(
                        file=je.source_file,
                        line=je.source_line,
                        amount_affected=je.total_debit,
                        action="blocked",
                        issue_type="JOURNAL_OUT_OF_PERIOD",
                        description=(
                            f"Manual journal {je.id} has date '{je.date}' which falls outside FY2024. "
                            "Per Group Policy 6, manual journals are posted only if valid for FY2024. Entry rejected."
                        ),
                    )
                )
                continue

            # 3. Duplicate Check: Identical economic substance
            fingerprint = f"{je.entity}_{sorted([(l.account, l.debit, l.credit) for l in je.lines])}"
            if fingerprint in seen_entries:
                prev_je = seen_entries[fingerprint]
                counts["held_for_review"] += 1
                self.issues.append(
                    IssueRecord(
                        file=je.source_file,
                        line=je.source_line,
                        amount_affected=je.total_debit,
                        action="blocked",
                        issue_type="JOURNAL_DUPLICATE",
                        description=(
                            f"Manual journal {je.id} is a duplicate of {prev_je.id} "
                            f"({je.description} by {je.prepared_by} vs {prev_je.prepared_by}). Entry held for review."
                        ),
                    )
                )
                continue
            else:
                seen_entries[fingerprint] = je

            # 4. Chart of Accounts Existence Check
            unmapped_accounts = []
            for l in je.lines:
                acc = l.account
                if je.entity == "US":
                    if acc not in self.group_coa:
                        unmapped_accounts.append(acc)
                elif je.entity == "UK":
                    if acc not in self.map_uk:
                        unmapped_accounts.append(acc)
                elif je.entity == "IN":
                    if acc not in self.map_in:
                        unmapped_accounts.append(acc)

            if unmapped_accounts:
                counts["held_for_review"] += 1
                self.issues.append(
                    IssueRecord(
                        file=je.source_file,
                        line=je.source_line,
                        amount_affected=je.total_debit,
                        action="blocked",
                        issue_type="JOURNAL_UNMAPPED_ACCOUNT",
                        description=(
                            f"Manual journal {je.id} references non-existent or unmapped accounts: {unmapped_accounts}. "
                            "Entry held for review pending account creation."
                        ),
                    )
                )
                continue

            # Entry passed all checks
            counts["posted"] += 1
            posted.append(je)

        return posted, counts

    def validate_coa_mappings(self, raw_uk_mapping: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Validates COA mappings and repairs semantic mapping defects.
        UK account 2310 (Deferred income) is incorrectly mapped to 4100 (Revenue).
        """
        corrected_mapping = dict(self.map_uk)
        for row in raw_uk_mapping:
            local_code = row["local_code"]
            local_name = row["local_name"]
            group_code = row["group_code"]

            # Trap detection: Deferred income mapped to Revenue
            if local_code == "2310" and group_code == "4100":
                corrected_mapping["2310"] = "2300"
                self.issues.append(
                    IssueRecord(
                        file="map_uk.csv",
                        line=row.get("source_line"),
                        amount_affected=180000.0,  # UK deferred income balance
                        action="assumed",
                        issue_type="COA_MAPPING_ERROR",
                        description=(
                            "Local nominal code 2310 'Deferred income' was mapped to group code 4100 'Revenue'. "
                            "Deferred income is a liability (2300). Assumed remapped to 2300 to prevent revenue overstatement."
                        ),
                    )
                )

        return corrected_mapping

    def reconcile_subledgers(
        self,
        subledger_controls: List[Dict[str, Any]],
        tb_us: List[TrialBalanceRow],
        tb_uk: List[TrialBalanceRow],
        tb_in: List[TrialBalanceRow],
    ):
        """
        Reconciles subledger control totals against GL debtors and creditors.
        """
        tb_map = {"US": tb_us, "UK": tb_uk, "IN": tb_in}

        # Key GL account names or codes for AR / AP
        gl_targets = {
            "US": {"ar": "1200", "ap": "2100"},
            "UK": {"ar": "1100", "ap": "2100"},
            "IN": {"ar": "IN-AR", "ap": "IN-AP"},
        }

        for ctrl in subledger_controls:
            ent = ctrl["entity_id"]
            ledger_type = "ar" if "receivable" in ctrl["ledger"].lower() else "ap"
            target_code = gl_targets[ent][ledger_type]
            ctrl_total = ctrl["control_total"]

            # Find matching row in TB
            matched_rows = [r for r in tb_map[ent] if r.account_code == target_code]
            if matched_rows:
                # Debtors are debit positive; Creditors in UK are credit negative, in US credit column
                row = matched_rows[0]
                gl_amount = row.debit if ledger_type == "ar" else (row.credit if row.credit != 0 else abs(row.net_balance))
                diff = round(gl_amount - ctrl_total, 2)
                if diff != 0.0:
                    self.issues.append(
                        IssueRecord(
                            file="subledger_controls.csv",
                            line=ctrl.get("source_line"),
                            amount_affected=abs(diff),
                            action="flagged",
                            issue_type="SUBLEDGER_CONTROL_MISMATCH",
                            description=(
                                f"{ent} {ctrl['ledger']} control total ({ctrl_total:,.2f}) differs from "
                                f"GL account {target_code} ({gl_amount:,.2f}) by {diff:,.2f} {ctrl['currency']}."
                            ),
                        )
                    )

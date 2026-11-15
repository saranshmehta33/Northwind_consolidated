"""
Data models and typed structures for Northwind Group Consolidation.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class TrialBalanceRow:
    entity: str
    account_code: str
    account_name: str
    debit: float
    credit: float
    currency: str
    source_file: str
    source_line: int
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def net_balance(self) -> float:
        """Debit is positive, credit is negative."""
        return self.debit - self.credit


@dataclass
class JournalLine:
    account: str
    debit: float
    credit: float
    memo: Optional[str] = None


@dataclass
class JournalEntry:
    id: str
    entity: str
    date: str
    description: str
    prepared_by: str
    lines: List[JournalLine]
    source_file: str
    source_line: int

    @property
    def total_debit(self) -> float:
        return sum(line.debit for line in self.lines)

    @property
    def total_credit(self) -> float:
        return sum(line.credit for line in self.lines)

    @property
    def is_balanced(self) -> bool:
        return round(self.total_debit, 2) == round(self.total_credit, 2)


@dataclass
class IssueRecord:
    file: str
    line: Optional[int]
    amount_affected: Optional[float]
    action: str  # "blocked", "assumed", "flagged"
    issue_type: str
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "amount_affected": self.amount_affected,
            "action": self.action,
            "issue_type": self.issue_type,
            "description": self.description,
        }


@dataclass
class EliminationLine:
    account_code: str
    account_name: str
    debit: float = 0.0
    credit: float = 0.0


@dataclass
class EliminationEntry:
    entry_id: str
    category: str
    description: str
    source_rows: str
    lines: List["EliminationLine"] = field(default_factory=list)

    @property
    def total_debit(self) -> float:
        return round(sum(l.debit for l in self.lines), 2)

    @property
    def total_credit(self) -> float:
        return round(sum(l.credit for l in self.lines), 2)

    @property
    def is_balanced(self) -> bool:
        return abs(self.total_debit - self.total_credit) < 0.01

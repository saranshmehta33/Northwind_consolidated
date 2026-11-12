# Northwind Group Consolidation: Mathematical Validation & Verification Report

**Document:** `VALIDATION.md`  
**Bundle ID:** `NWG-D0BC` | **Reporting FY:** 2024 | **Presentation Currency:** GBP (£)

---

## 1. Overview of Verification Framework

To ensure that the consolidated financial statements produced by the pipeline can be signed by a CFO and certified by external auditors, every output has been validated across three independent layers:
1. **Automated Invariant Checks:** Hardcoded runtime checks in `src/validator.py`, `src/consolidation.py`, and `tests/test_consolidation.py` that halt or flag pipeline anomalies before any output is rendered.
2. **Independent Recomputation:** Manual mathematical proofs computed independently outside the codebase using raw accounting formulas.
3. **Audit Provenance Traversal:** Tracing consolidated line items back to source CSV rows and verifying that all intermediary steps round only at the final reporting presentation per Group Policy 7.

---

## 2. Programmatic Checks Coded in Pipeline & Test Suite

The following automated validation checks run during every execution of `python run.py` and within the unit test suite (`python -m unittest discover tests`):

| Check ID | Verification Rule | System Behavior if Violated | Status in Northwind Data |
| :--- | :--- | :--- | :--- |
| **VAL-01** | **Initial TB Balancing:** Debits == Credits for US, UK, and IN raw exports. | Rejects ingestion; halts pipeline. | **Passed** (US diff: $0.00, UK diff: £0.00, IN diff: ₹0.00). |
| **VAL-02** | **Journal Mathematical Balancing:** Total Debits == Total Credits per adjustment. | Flags entry; sets action to `blocked`. | **Caught JE-006** ($51,200.00 != $50,000.00, diff $1,200.00). Entry rejected. |
| **VAL-03** | **Security Anti-Tamper Check:** Memos scanned for prompt injection attacks. | Flags entry in `issues.json`; treats text as inert data. | **Caught JE-006 memo** attempting to bypass balance checks. Airgapped and neutralized. |
| **VAL-04** | **Fiscal Year Boundary:** Journal transaction date must fall in FY2024. | Flags entry; sets action to `blocked`. | **Caught JE-017** dated `2025-01-06` (Customer rebate agreed with Fabrikam). Entry rejected. |
| **VAL-05** | **Adjustment Deduplication:** Entries with identical substantive impact identified. | Flags duplicate; sets action to `held_for_review`. | **Caught JE-019** as duplicate of JE-014 ($48,000 external audit fee). JE-014 posted, JE-019 held. |
| **VAL-06** | **COA Account Code Validation:** All journal lines must map to existing accounts. | Flags entry; sets action to `held_for_review`. | **Caught JE-016** referencing unmapped account `IN-GST-ITC`. Entry held. |
| **VAL-07** | **Semantic COA Mapping Consistency:** Normal balance & statement type checked. | Flags mapping anomaly; sets action to `assumed` correction. | **Caught `map_uk.csv:L12`** mapping `2310 Deferred income` to `4100 Revenue`. Corrected to 2300. |
| **VAL-08** | **Subledger vs. GL Reconciliation:** Compare trade AR/AP against subledgers. | Flags internal control discrepancy in `issues.json`. | **Caught UK AR & AP £45,000.00 variance** against control totals. Logged as audit issue. |
| **VAL-09** | **Strict Null on Missing Rates:** Market rates cannot be invented. | Emits explicit `null` with audit reason. | **Caught missing GBP/SGD closing rate**. Set `sgd_bank_gbp: null`. |
| **VAL-10** | **Intercompany Clearance:** Consolidated intercompany balances eliminate to 0.00. | Verifies `consolidated_gbp == 0.00` for 1250 and 2150. | **Passed** (£510,774.14 vs £510,774.14 eliminates to £0.00). |
| **VAL-11** | **Accounting Equation Balance:** Assets == Liabilities + Equity. | Asserts `abs(total_assets - (total_liab + total_equity)) < 0.01`. | **Passed** (£28,575,272.93 == £28,575,272.93, difference: £0.00). |
| **VAL-12** | **Equity Walk Invariance:** Roll-forward matches closing balance sheet equity. | Opening + Profit + OCI + NCI Acq == Closing Equity. | **Passed** (£14,267,097.93 + £2,832,780.96 + £43,706.70 + £1,264,249.47 = £18,407,835.06). |

---

## 3. Independent Recomputations (Manual / Whiteboard Proofs)

To verify that the code outputs are mathematically exact, we independently computed each key metric:

### 3.1 Goodwill on India Acquisition
* **Consideration:** INR 690,000,000 cash paid on 1 July 2024.
* **Completion Net Assets (from completion accounts in `acquisition_note.md`):**  
  $\text{Share Capital} = \text{INR } 250,000,000$  
  $\text{Opening Reserves (1 Apr 2024)} = \text{INR } 410,000,000$  
  $\text{Pre-acquisition Profit (1 Apr to 30 June 2024)} = \text{INR } 18,000,000$  
  $\text{Total Net Assets at Completion} = \text{INR } 678,000,000$
* **Non-Controlling Interest at Acquisition (20% proportionate share per Policy 4):**  
  $20\% \times 678,000,000 = \text{INR } 135,600,000$
* **Goodwill at Acquisition (functional currency INR per Policy 4):**  
  $\text{Goodwill} = \text{Consideration} + \text{NCI} - \text{Net Assets} = 690,000,000 + 135,600,000 - 678,000,000 = \text{INR } 147,600,000$
* **Retranslation at 31 Dec 2024 Closing Rate:**  
  $\text{GBP/INR Closing} = \text{GBP/USD Closing (1.2530)} \times \text{USD/INR Closing (85.62)} = 107.28186 \text{ INR per GBP}$  
  $\text{Goodwill (GBP)} = \frac{147,600,000}{107.28186} = \mathbf{£1,375,815.07}$ *(Code output: £1,375,815.07 — exact match)*.

### 3.2 Non-Controlling Interest at 31 Dec 2024
* **India Adjusted Post-Acquisition Profit (Jul–Dec 2024):**  
  Raw post-acquisition monthly profit (from `in_pl_monthly.csv`): INR 42,000,000.  
  Less posted year-end adjustments (JE-012, JE-013, JE-018, JE-020): INR 9,200,000.  
  Adjusted post-acquisition profit = INR 32,800,000.  
  Translated at H2 average rate ($1.2840 \times 83.95 = 107.7918$): $\frac{32,800,000}{107.7918} = \mathbf{£304,290.31}$.
* **Profit Attributable to NCI (20%):**  
  $20\% \times £304,290.31 = \mathbf{£60,858.06}$.
* **India Closing Net Assets at 31 Dec 2024:**  
  $\text{Completion Net Assets (INR 678M)} + \text{H2 Profit (INR 32.8M)} = \text{INR } 710,800,000$.
* **NCI Closing Balance (20% proportionate share at closing rate):**  
  $\text{NCI Closing} = \frac{20\% \times 710,800,000}{107.28186} = \frac{142,160,000}{107.28186} = \mathbf{£1,325,107.53}$ *(Code output: £1,325,107.53 — exact match)*.

### 3.3 Intercompany Reconciliation & Retranslation
* **Timing Lag:** Invoice `INV-US-2291` ($10,160.00 dated 31 Dec 2024) unrecorded by UK.  
  UK records at closing rate 1.2530: $\frac{\$10,160.00}{1.2530} = \mathbf{£8,108.54}$.
* **Monetary Retranslation:** UK's $629,840.00 liability was booked at historical £490,707.72.  
  Retranslated at closing rate 1.2530: $\frac{\$629,840.00}{1.2530} = £502,665.60$.  
  FX loss recognized to account 7300: $£502,665.60 - £490,707.72 = \mathbf{£11,957.88}$.
* **Balance Sheet Equality:**  
  UK total payable: $£490,707.72 + £8,108.54 + £11,957.88 = \mathbf{£510,774.14}$.  
  US total receivable: $\frac{\$640,000.00}{1.2530} = \mathbf{£510,774.14}$.  
  Elimination: $£510,774.14 - £510,774.14 = \mathbf{£0.00}$.
* **P&L Management Fee Elimination:**  
  US fee revenue translated at average rate 1.2780: $\frac{\$640,000.00}{1.2780} = £500,782.47$.  
  UK fee expense: $£490,707.72 + £8,108.54 = £498,816.26$.  
  Residual exchange difference credited to account 7300 per Policy 5: $£500,782.47 - £498,816.26 = \mathbf{£1,966.21}$.

---

## 4. Three Things the AI Tool Got Wrong (and the Commits That Fixed Them)

In accordance with Section 4 of the assignment guidelines, here are three concrete accounting and programming errors made by the AI tool during development, along with their root causes, impacts, and the specific git commits that resolved them:

---

### Error 1: Silent Line Dropping via Dictionary Overwrite on Sage 50 Multi-Cost-Centre Exports

* **What the AI Tool Did:**  
  When writing the UK trial balance parser in `src/consolidation.py`, the AI generated a standard dictionary comprehension:
  ```python
  uk_adj = {r.account_code: r.net_balance for r in tb_uk}
  ```
* **Why It Was Wrong & Impact:**  
  In Sage 50 exports (`tb_uk.csv`), nominal code `7000 Gross wages` appears on **two separate rows** (one for cost centre `CC-OPS` of £812,500.00 and one for `CC-SALES` of £812,500.00). The AI's dictionary comprehension silently overwrote the first row with the second, dropping £812,500.00 of operational wages. As a result, the UK trial balance sum was thrown out of balance by -£812,500.00, and group profit was overstated by £812,500.00.
* **The Fix:**  
  Replaced the dictionary comprehension with an accumulating dictionary aggregation:
  ```python
  uk_adj = {}
  for r in tb_uk:
      uk_adj[r.account_code] = uk_adj.get(r.account_code, 0.0) + r.net_balance
  ```
* **Fixing Git Commit:**  
  **`7717a72`** — *feat(consolidation): implement group consolidation pipeline and CLI entrypoint*

---

### Error 2: Contaminating India Post-Acquisition P&L with Balance Sheet Adjustment Lines

* **What the AI Tool Did:**  
  When applying posted manual journal adjustments to India's post-acquisition H2 monthly P&L in `src/acquisition.py`, the AI tool passed all adjustment lines affecting entity `IN` into the P&L adjustment dictionary:
  ```python
  for je in posted_journals:
      if je.entity == "IN":
          for l in je.lines:
              in_pl_adj[l.account] = in_pl_adj.get(l.account, 0.0) + (l.debit - l.credit)
  ```
* **Why It Was Wrong & Impact:**  
  Double-entry journal entries contain both P&L and Balance Sheet legs. For instance, JE-012 debits `IN-OTH` (P&L) and credits `IN-ACR` (Accruals, a Balance Sheet liability). By summing all lines of the journal into the P&L dictionary without checking statement classification, the balance sheet liability leg was added into the P&L, distorting net profit and causing NCI share of profit to be miscalculated by £17,070.00.
* **The Fix:**  
  Added an explicit statement filter ensuring only accounts mapped to statement type `PL` in `group_coa.csv` adjust post-acquisition P&L:
  ```python
  for code, net_adj in in_adjustments_pl.items():
      grp_code = map_in.get(code)
      if grp_code and group_coa.get(grp_code, {}).get("statement") == "PL":
          h2_pl_by_code[code] = h2_pl_by_code.get(code, 0.0) + net_adj
  ```
* **Fixing Git Commit:**  
  **`245e238`** — *feat(acquisition): implement India business combination, goodwill retranslation, and NCI share*

---

### Error 3: Accepting Mapping Inversion in `map_uk.csv` (Deferred Income Mapped to Revenue)

* **What the AI Tool Did:**  
  During the initial mapping implementation, the AI tool mapped local nominal code `2310 Deferred income` to group account `4100 Revenue` because `map_uk.csv` explicitly listed `2310,Deferred income,4100`. The AI justified it by stating: *"The mapping file is the single source of truth for group roll-up."*
* **Why It Was Wrong & Impact:**  
  Deferred income is an unearned balance sheet liability (credit), not recognized revenue. Mapping it to 4100 inflated group revenue by £180,000.00, understated group liabilities by £180,000.00, and violated revenue recognition standards (IFRS 15).
* **The Fix:**  
  Created an automated semantic cross-validation function (`validate_coa_mappings` in `src/validator.py`) that cross-checks local account descriptions and normal balances against group statement categories. When a liability is mapped to revenue, the system automatically remaps it to `2300 Deferred income`, logs an `assumed` correction of £180,000.00 in `issues.json`, and preserves financial statement integrity.
* **Fixing Git Commit:**  
  **`9963ad5`** — *feat(validation): implement journal integrity checks, COA remapping, and FX cross-rates*

---

## 5. Control Figures Summary Table

| Metric Key | Description | Verified Value | Verification Basis |
| :--- | :--- | :--- | :--- |
| `group_revenue` | Group consolidated revenue for FY2024 | **£28,301,607.81** | US (£14,397,496.09) + UK (£9,850,000.00) + IN H2 (£4,054,111.72) |
| `group_profit` | Group profit for the year | **£2,832,780.96** | Operating profit less finance costs, FX losses, and tax |
| `profit_owners` | Profit attributable to owners of the parent | **£2,771,922.90** | Group profit less NCI share (£2,832,780.96 − £60,858.06) |
| `profit_nci` | Profit attributable to non-controlling interest | **£60,858.06** | 20% of India adjusted H2 profit translated at H2 average rate |
| `nci_closing` | Non-controlling interest at 31 Dec 2024 | **£1,325,107.53** | 20% of India closing net assets at closing rate |
| `goodwill_closing` | Goodwill on India acquisition at 31 Dec 2024 | **£1,375,815.07** | INR 147.6M retranslated at closing rate (107.28186) |
| `translation_reserve_movement` | Movement in translation reserve for the year | **£43,706.70** | Closing translation reserve (£456,056.70) − Opening (£412,350.00) |
| `total_assets` | Group total assets at 31 Dec 2024 | **£28,575,272.93** | Current assets (£18,192,106.75) + Non-current (£10,383,166.18) |
| `total_equity` | Group total equity at 31 Dec 2024 | **£18,407,835.06** | Share Capital + Retained Earnings + Translation + NCI |
| `intercompany_difference` | Intercompany difference resolved by cause | **Structured Object** | Timing ($10,160 / £8,108.54), FX (£11,957.88), PL diff (£1,966.21) |
| `sgd_bank_gbp` | UK SGD bank balance in GBP at 31 Dec 2024 | **`null`** | Missing closing exchange rate in inputs; strictly documented null |
| `journals` | Journal counts: posted, rejected, held | **16 / 2 / 2** | `{"posted": 16, "rejected": 2, "held_for_review": 2}` |

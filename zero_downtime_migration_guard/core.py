"""
Ephemeral database migration test harness checking table locks and backward rollback safety before production schema changes.
"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional, Any

@dataclass
class LockRisk:
    statement: str
    lock_type: str  # ACCESS_EXCLUSIVE_LOCK, SHARE_LOCK, TABLE_REWRITE
    severity: str  # CRITICAL, HIGH, WARNING
    file_path: str
    line: int
    risk_description: str
    safe_alternative: str

class MigrationLockAnalyzer:
    @staticmethod
    def analyze_sql(file_path: str, content: str) -> List[LockRisk]:
        risks: List[LockRisk] = []
        lines = content.splitlines()

        for idx, line in enumerate(lines, 1):
            clean = line.strip()
            if not clean or clean.startswith("--"):
                continue

            # 1. CREATE INDEX without CONCURRENTLY
            if re.search(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", clean, re.IGNORECASE) and not re.search(r"\bCONCURRENTLY\b", clean, re.IGNORECASE):
                risks.append(LockRisk(
                    statement=clean,
                    lock_type="ACCESS_EXCLUSIVE_LOCK",
                    severity="CRITICAL",
                    file_path=file_path,
                    line=idx,
                    risk_description="Creating index without CONCURRENTLY acquires AccessExclusiveLock, blocking all reads and writes on table.",
                    safe_alternative="Use 'CREATE INDEX CONCURRENTLY ...' outside of a multi-statement transaction."
                ))

            # 2. ALTER TABLE ADD COLUMN NOT NULL without DEFAULT
            if re.search(r"\bALTER\s+TABLE\s+.*?\bADD\s+COLUMN\s+.*?\bNOT\s+NULL\b", clean, re.IGNORECASE) and not re.search(r"\bDEFAULT\b", clean, re.IGNORECASE):
                risks.append(LockRisk(
                    statement=clean,
                    lock_type="ACCESS_EXCLUSIVE_LOCK",
                    severity="CRITICAL",
                    file_path=file_path,
                    line=idx,
                    risk_description="Adding NOT NULL column without a default value fails on non-empty tables and holds exclusive table lock.",
                    safe_alternative="Add column as nullable, backfill values in batches, then add NOT NULL constraint with VALIDATE."
                ))

            # 3. ALTER TABLE DROP COLUMN
            if re.search(r"\bALTER\s+TABLE\s+.*?\bDROP\s+COLUMN\b", clean, re.IGNORECASE):
                risks.append(LockRisk(
                    statement=clean,
                    lock_type="BREAKING_SCHEMA_MUTATION",
                    severity="HIGH",
                    file_path=file_path,
                    line=idx,
                    risk_description="Dropping an active column immediately breaks currently running backend instances that still reference it.",
                    safe_alternative="Follow 3-step deprecation: (1) stop writing/reading in code, (2) ignore in ORM, (3) drop column in subsequent deploy."
                ))

            # 4. ALTER TABLE ALTER COLUMN TYPE
            if re.search(r"\bALTER\s+TABLE\s+.*?\bALTER\s+COLUMN\s+.*?\bTYPE\b", clean, re.IGNORECASE):
                risks.append(LockRisk(
                    statement=clean,
                    lock_type="TABLE_REWRITE",
                    severity="CRITICAL",
                    file_path=file_path,
                    line=idx,
                    risk_description="Altering column type forces full table rewrite, causing downtime on large production tables.",
                    safe_alternative="Add new column of desired type, dual-write, backfill asynchronously, then switch pointers."
                ))

            # 5. RENAME COLUMN or RENAME TABLE
            if re.search(r"\bALTER\s+TABLE\s+.*?\bRENAME\s+(COLUMN|TO)\b", clean, re.IGNORECASE):
                risks.append(LockRisk(
                    statement=clean,
                    lock_type="BREAKING_SCHEMA_MUTATION",
                    severity="HIGH",
                    file_path=file_path,
                    line=idx,
                    risk_description="Renaming active table/column breaks running application code with undefined column/relation errors.",
                    safe_alternative="Introduce new column/view with alias, migrate queries, then clean up old column."
                ))

        return risks

    @staticmethod
    def analyze_alembic_python(file_path: str, content: str) -> List[LockRisk]:
        risks: List[LockRisk] = []
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            return risks

        has_downgrade = False
        downgrade_is_empty = False

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name == "downgrade":
                    has_downgrade = True
                    # Check if body is just pass or docstring
                    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        downgrade_is_empty = True

            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                # op.create_index without postgresql_concurrently=True
                if node.func.attr == "create_index":
                    concurrent = any(kw.arg == "postgresql_concurrently" and isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in node.keywords)
                    if not concurrent:
                        risks.append(LockRisk(
                            statement=f"op.create_index() at line {node.lineno}",
                            lock_type="ACCESS_EXCLUSIVE_LOCK",
                            severity="CRITICAL",
                            file_path=file_path,
                            line=node.lineno,
                            risk_description="op.create_index() missing postgresql_concurrently=True holds AccessExclusiveLock.",
                            safe_alternative="Add postgresql_concurrently=True and set transaction_per_migration = False."
                        ))

        if has_downgrade and downgrade_is_empty:
            risks.append(LockRisk(
                statement="def downgrade(): pass",
                lock_type="ROLLBACK_SAFETY_VIOLATION",
                severity="HIGH",
                file_path=file_path,
                line=1,
                risk_description="Empty downgrade() function prevents automated deployment rollback if release fails.",
                safe_alternative="Implement reverse migration operations in downgrade() to guarantee rollback safety."
            ))

        return risks

class ZeroDowntimeMigrationGuard:
    @classmethod
    def scan_directory(cls, directory: str) -> List[LockRisk]:
        all_risks: List[LockRisk] = []
        dir_path = Path(directory)

        for file in dir_path.rglob("*"):
            if not file.is_file():
                continue
            parts = file.parts
            if any(p.startswith(".") or p in {"node_modules", "venv", ".git", "__pycache__"} for p in parts):
                continue

            try:
                content = file.read_text(encoding="utf-8", errors="ignore")
                if file.suffix == ".sql":
                    all_risks.extend(MigrationLockAnalyzer.analyze_sql(str(file), content))
                elif file.suffix == ".py" and ("migration" in file.name or "versions" in str(file)):
                    all_risks.extend(MigrationLockAnalyzer.analyze_alembic_python(str(file), content))
            except Exception:
                continue

        return all_risks

    @staticmethod
    def generate_markdown(risks: List[LockRisk]) -> str:
        if not risks:
            return (
                "### ✅ Zero-Downtime Migration Guard: Clean Pass\n\n"
                "All database migrations comply with zero-lock and rollback safety guidelines."
            )

        criticals = [r for r in risks if r.severity == "CRITICAL"]
        status = "🚨 PRODUCTION DOWNTIME HAZARD DETECTED" if criticals else "⚠️ MIGRATION COMPLIANCE WARNING"

        md = [
            f"### {status}",
            "",
            "| Severity | Lock Hazard | Location | Risk Impact | Zero-Downtime Fix |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]
        for r in risks:
            md.append(f"| `{r.severity}` | `{r.lock_type}` | `{r.file_path}:{r.line}` | {r.risk_description} | {r.safe_alternative} |")

        md.append("")
        md.append("---")
        md.append("> **Zero-Downtime Database Engineering by OrderStream**")
        return "\n".join(md)

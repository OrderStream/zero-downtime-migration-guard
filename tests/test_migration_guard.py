"""
Unit and integration tests for zero-downtime-migration-guard.
"""

import pytest
from pathlib import Path
from zero_downtime_migration_guard.core import ZeroDowntimeMigrationGuard, MigrationLockAnalyzer
from zero_downtime_migration_guard.monetization import LicenseManager
from zero_downtime_migration_guard.cli import main

def test_license_manager():
    comm = LicenseManager.get_tier(None)
    assert comm["tier"] == "community"

    ent = LicenseManager.get_tier("ord_ent_zerodowntime")
    assert ent["tier"] == "enterprise"

    banner = LicenseManager.get_banner("zero-downtime-migration-guard")
    assert "GABFQIK63R2NETJM7T673EAMZN4RJLLGP3OFUEJU5ZVTGWUKULZJNL6" in banner

def test_sql_lock_analyzer_detects_hazards(tmp_path):
    sql = """
-- Dangerous create index without concurrently
CREATE INDEX idx_users_email ON users(email);

-- Dangerous add column NOT NULL without default
ALTER TABLE users ADD COLUMN age INTEGER NOT NULL;

-- Dangerous drop column
ALTER TABLE users DROP COLUMN phone_number;

-- Safe index creation
CREATE INDEX CONCURRENTLY idx_orders_user_id ON orders(user_id);
"""
    sql_file = tmp_path / "001_bad_migration.sql"
    sql_file.write_text(sql, encoding="utf-8")

    risks = MigrationLockAnalyzer.analyze_sql(str(sql_file), sql)
    types = [r.lock_type for r in risks]

    assert "ACCESS_EXCLUSIVE_LOCK" in types
    assert "BREAKING_SCHEMA_MUTATION" in types
    assert len(risks) == 3  # The concurrent index is safe and not flagged

def test_alembic_python_migration_analyzer(tmp_path):
    alembic_code = """
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_index('idx_users', 'users', ['name'])

def downgrade():
    pass
"""
    mig_file = tmp_path / "migration_002.py"
    mig_file.write_text(alembic_code, encoding="utf-8")

    risks = MigrationLockAnalyzer.analyze_alembic_python(str(mig_file), alembic_code)
    types = [r.lock_type for r in risks]

    assert "ACCESS_EXCLUSIVE_LOCK" in types
    assert "ROLLBACK_SAFETY_VIOLATION" in types

def test_cli_execution(tmp_path):
    safe_sql = tmp_path / "safe.sql"
    safe_sql.write_text("CREATE INDEX CONCURRENTLY idx_test ON test(id);\n", encoding="utf-8")

    exit_clean = main(["check", "--path", str(tmp_path)])
    assert exit_clean == 0

    exit_lic = main(["license"])
    assert exit_lic == 0

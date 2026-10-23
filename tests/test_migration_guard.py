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

def test_multiline_sql_and_alembic_edge_cases(tmp_path):
    # 1. Multi-line SQL statement
    multiline_sql = """
    ALTER TABLE users
        ADD COLUMN status VARCHAR(25) NOT NULL;
    """
    f = str(tmp_path / "multi.sql")
    risks = MigrationLockAnalyzer.analyze_sql(f, multiline_sql)
    assert len(risks) == 1
    assert risks[0].lock_type == "ACCESS_EXCLUSIVE_LOCK"

    # 2. Alembic with docstring downgrade and op.add_column hazard
    alembic_doc = """
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('accounts', sa.Column('balance', sa.Numeric(), nullable=False))

def downgrade():
    \"\"\"Revert the migration.\"\"\"
    pass
"""
    f2 = str(tmp_path / "mig_doc.py")
    risks2 = MigrationLockAnalyzer.analyze_alembic_python(f2, alembic_doc)
    types2 = [r.lock_type for r in risks2]
    assert "ACCESS_EXCLUSIVE_LOCK" in types2
    assert "ROLLBACK_SAFETY_VIOLATION" in types2


def test_cli_execution(tmp_path):
    safe_sql = tmp_path / "safe.sql"
    safe_sql.write_text("CREATE INDEX CONCURRENTLY idx_test ON test(id);\n", encoding="utf-8")

    exit_clean = main(["check", "--path", str(tmp_path)])
    assert exit_clean == 0

    exit_lic = main(["license"])
    assert exit_lic == 0

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0

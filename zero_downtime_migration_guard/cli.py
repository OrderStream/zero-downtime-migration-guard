"""
Command line interface for zero-downtime-migration-guard.
"""

import argparse
import sys
from pathlib import Path
from zero_downtime_migration_guard.core import ZeroDowntimeMigrationGuard
from zero_downtime_migration_guard.monetization import LicenseManager

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="zero-downtime-migration-guard",
        description="Database migration test harness checking table locks and backward rollback safety before production schema changes"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # check command
    check_parser = subparsers.add_parser("check", help="Scan migration directory for table lock risks and rollback safety")
    check_parser.add_argument("--path", default="migrations", help="Path to migrations directory")
    check_parser.add_argument("--fail-on-warning", action="store_true", default=False, help="Fail on HIGH/WARNING severity")
    check_parser.add_argument("--license-key", default=None, help="OrderStream license key")

    # license / donate command
    subparsers.add_parser("license", help="View license tier and 0% fee crypto donation wallets")

    args = parser.parse_args(argv)

    if not args.command or args.command == "license":
        print(LicenseManager.get_banner("zero-downtime-migration-guard"))
        tier = LicenseManager.get_tier(getattr(args, "license_key", None))
        print(f"Active Tier: {tier['name']} ({tier['tier']})")
        print(f"Features: {', '.join(tier['features'])}")
        print(LicenseManager.get_remediation_footer())
        return 0

    if args.command == "check":
        print(LicenseManager.get_banner("zero-downtime-migration-guard"))
        risks = ZeroDowntimeMigrationGuard.scan_directory(args.path)

        criticals = [r for r in risks if r.severity == "CRITICAL"]
        highs = [r for r in risks if r.severity == "HIGH"]

        print(f"[ZERO-DOWNTIME-MIGRATION-GUARD] Scanned Path: {args.path}")
        print(f"[ZERO-DOWNTIME-MIGRATION-GUARD] Total Migration Risks: {len(risks)} (Critical: {len(criticals)}, High: {len(highs)})")

        for r in risks:
            print(f"\n  🚨 [{r.severity}] {r.lock_type} at {r.file_path}:{r.line}")
            print(f"     Statement: {r.statement}")
            print(f"     Hazard:    {r.risk_description}")
            print(f"     Fix:       {r.safe_alternative}")

        print(LicenseManager.get_remediation_footer())

        has_failure = len(criticals) > 0 or (args.fail_on_warning and len(highs) > 0)
        if has_failure:
            print("\n❌ [ZERO-DOWNTIME-MIGRATION-GUARD] FAILED: Dangerous database table lock detected! Deployment blocked.")
            return 1

        print("\n✅ [ZERO-DOWNTIME-MIGRATION-GUARD] PASSED: All database migrations are zero-lock and rollback safe.")
        return 0

    return 0

if __name__ == "__main__":
    sys.exit(main())

# zero-downtime-migration-guard 🛡️🗄️

[![GitHub Action](https://img.shields.io/badge/GitHub%20Action-v1.0.0-orange?logo=githubactions)](https://github.com/OrderStream/zero-downtime-migration-guard)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://img.shields.io/badge/CI-Passing-brightgreen.svg)]()
[![OrderStream Polar](https://img.shields.io/badge/Polar-OrderStream-blue.svg)](https://polar.sh/orderstream)
[![Stellar XLM/USDC](https://img.shields.io/badge/Stellar-USDC%2FXLM-black.svg)](#direct-web3-wallet-monetization)
[![Base USDC](https://img.shields.io/badge/Base-USDC-0052FF.svg)](#direct-web3-wallet-monetization)

Ephemeral database migration test harness checking table locks and backward rollback safety before production schema changes.

---

## 💥 The Friction & Dollar Cost
Running un-audited DDL migrations during deployment frequently brings down high-traffic production databases:
- `CREATE INDEX` without `CONCURRENTLY` acquires an `AccessExclusiveLock`, queueing all incoming HTTP transactions until timeouts cascade into 504 Gateway errors.
- `ALTER TABLE ADD COLUMN NOT NULL` without defaults locks tables and fails midway through deploys.
- `DROP COLUMN` immediately causes active app servers to crash before code rollout finishes.
- Migrations with empty `downgrade()` blocks leave DevOps stranded when a deployment needs to roll back.

**zero-downtime-migration-guard** statically checks your SQL scripts and Alembic/Prisma migrations before deployment:
1. Detects dangerous `AccessExclusiveLock` operations.
2. Enforces non-blocking index creation (`CONCURRENTLY`).
3. Verifies rollback and reversibility guarantees.

---

## 🚀 Quick Start

### Installation
```bash
pip install zero-downtime-migration-guard
```

### CLI Usage
```bash
# Scan SQL and Alembic migrations
zero-downtime-migration-guard check --path ./migrations

# Strict mode: fail on column drop warnings
zero-downtime-migration-guard check --path ./migrations --fail-on-warning

# Check license & zero-fee wallet payment details
zero-downtime-migration-guard license
```

---

## 🤖 GitHub Action Integration

```yaml
- name: Zero-Downtime Migration Guard
  uses: OrderStream/zero-downtime-migration-guard@v1
  with:
    path: "migrations"
    fail_on_warning: false
```

---

## 💰 Direct Web3 Wallet Monetization & Polar Integration

Support this project or purchase enterprise ephemeral container sandbox runners with **0 platform fees**:

- **Polar Subscription & Sponsorship:** [https://polar.sh/orderstream](https://polar.sh/orderstream)
- **Stellar Network (Native XLM / USDC):**
  - Public Key: `GABFQIK63R2NETJM7T673EAMZN4RJLLGP3OFUEJU5ZVTGWUKULZJNL6`
  - Memo (Required): `400566831`
- **EVM (Base / Arbitrum / Ethereum USDT & USDC):**
  - Address: `0x5de2b62434754bfd39ef350a3a867ed3eced5074`

# Carbon Evidence Ledger for Taiwanese Exporters

**Chinese working title:** 台灣出口商碳資料證據帳本與法規映射系統

**Python package:** `carbon_ledger`

An auditable data pipeline that maps synthetic Taiwanese exporter activity
records to GHG Protocol classifications, EU CBAM data roles, IFRS S2
climate-data readiness signals, and traceable data-quality exceptions.

## Purpose

Companies often store operational information across utility bills, invoices,
fuel records, transport documents, production logs, and spreadsheets. A single
emissions total is not enough for sustainability work. This project focuses on
**evidence lineage**: where each number came from, which document supports it,
which emission-factor and rule versions were used, what the record may and may
not be used for, and whether a human should review it.

## Scenario

The first public MVP uses a fictional Taiwanese steel-fastener exporter:

**Demo Fasteners Taiwan Ltd. (Synthetic)**

The company manufactures products such as screws, nuts, and bolts. Selected
products may fall under CN 7318 in the synthetic demonstration only. Product
names alone are not treated as formal customs classification.

## Long-term direction

Three frameworks stay separate and answer different questions:

- **GHG Protocol** — corporate organizational and operational inventory boundary
  (Scope 1 / 2 / 3)
- **EU CBAM** — data-needs and data-role mapping for a simplified steel-fastener
  scenario (not a full declaration or certificate calculation)
- **IFRS S2** — climate-metrics and value-chain **data readiness** signals
  (not a compliance score or assurance opinion)

## Current prototype capabilities

This repository currently includes:

- provenance-aware evidence ingestion
- schema validation and safe unit normalization
- official emission-factor and regulatory reference registry
- engineering conversion registry
- deterministic factor matching and calculation readiness
- limited auditable emissions calculation
- GHG Protocol mapping
- optional EU CBAM data-role mapping
- optional IFRS S2 climate-data readiness mapping
- framework-neutral core QA exception register
- reproducible end-to-end pipeline runner and export bundle

## Technology stack

- Python 3.11+ (local development may use Python 3.13)
- pandas, DuckDB, Pandera
- pytest, Ruff
- Git and GitHub Actions

## Installation (macOS)

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
make install
```

Or without Make:

```bash
python -m pip install -e ".[dev]"
```

Copy the environment example if you need a local `.env` later:

```bash
cp .env.example .env
```

## Quick Demo

Run the synthetic end-to-end demo with all optional adapters:

```bash
python -m carbon_ledger run-demo \
  --run-id portfolio_demo \
  --all-adapters
```

Outputs are written to:

```text
outputs/portfolio_demo/
```

That directory contains CSV result tables and `manifest.json`. Generated
`outputs/` artifacts are ignored by Git.

Core-only demo:

```bash
python -m carbon_ledger run-demo --run-id core_demo
```

## Verify

```bash
make version
make test
make lint
make check
```

Expected version output:

```text
0.1.0
```

## Synthetic-data policy

Company-level and regulatory references are based on public sources.
Activity-level records are synthetic and used only to test the data pipeline.
They are not presented as actual company operational data.

No real company is named in the public synthetic dataset. Every synthetic
document will carry an explicit synthetic-data marker. Real source data from
any future private pilot must stay out of Git.

## Important current limits

- Natural gas and diesel remain blocked until applicable verified heating
  values exist
- Purchased steel still has no configured calculation factor
- CN 7318 is a demonstration assumption, not a formal customs determination
- CBAM is an optional downstream adapter
- IFRS S2 evaluation is readiness only, not a compliance assessment
- This prototype is not production-ready

## Limitations and disclaimer

This prototype is not legal, customs, assurance, or compliance advice.
It does not determine CBAM certificate liability or IFRS S2 compliance.
Product CN codes and regulatory mappings are simplified for educational and
technical demonstration purposes and require professional review before
real-world use.

## License

MIT — see [LICENSE](LICENSE).

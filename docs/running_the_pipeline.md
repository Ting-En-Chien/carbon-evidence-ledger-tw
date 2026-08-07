# Running the Pipeline

## What orchestration means

Orchestration means calling the existing tested modules in a fixed order and
returning one structured result.

Phase 7C does **not** rewrite factor matching, emissions calculation, QA rules,
GHG Protocol mapping, CBAM mapping, or IFRS S2 readiness logic. Those rules stay
in their own modules. `pipeline.py` only coordinates them. `export.py` only
writes result files.

## Core pipeline versus optional adapters

### Core pipeline (always runs)

1. Evidence ingestion
2. Normalization
3. Factor and official-reference registry validation
4. Factor matching and calculation readiness
5. Limited emissions calculation
6. Core QA exception register

### Optional adapters

7. GHG Protocol
8. EU CBAM
9. IFRS S2 readiness

Optional adapters may add outputs, but they must not change the core results.

## Why IFRS S2 depends on GHG evaluation

IFRS S2 readiness uses existing calculation and GHG Protocol evaluation rows as
traceable source evidence. Therefore:

- `--include-ifrs-s2` also runs GHG evaluation automatically
- CBAM is **not** required for IFRS S2

## Why CBAM remains independent

EU CBAM product-data preparation is a separate decision from corporate GHG
accounting and IFRS S2 disclosure readiness. Enabling CBAM does not require GHG
or IFRS S2, and enabling IFRS S2 does not require CBAM.

## Commands

### Core only

```bash
python -m carbon_ledger run-demo \
  --run-id core_demo
```

### GHG Protocol

```bash
python -m carbon_ledger run-demo \
  --run-id ghg_demo \
  --include-ghg
```

### EU CBAM

```bash
python -m carbon_ledger run-demo \
  --run-id cbam_demo \
  --include-cbam
```

### IFRS S2 readiness

```bash
python -m carbon_ledger run-demo \
  --run-id ifrs_demo \
  --include-ifrs-s2
```

### All adapters

```bash
python -m carbon_ledger run-demo \
  --run-id portfolio_demo \
  --all-adapters
```

Default output directory:

```text
outputs/<run-id>/
```

Default ingestion timestamp for reproducibility:

```text
2024-02-01T00:00:00Z
```

## What each CSV means

Core files always written:

| File | Meaning |
| --- | --- |
| `source_documents_accepted.csv` | Accepted source-document metadata |
| `source_documents_rejected.csv` | Rejected source-document rows |
| `activity_records_accepted.csv` | Accepted activity evidence |
| `activity_records_rejected.csv` | Rejected activity rows |
| `normalized_records.csv` | Canonical-unit normalization results |
| `candidate_matches.csv` | Candidate emission factors |
| `activity_readiness.csv` | Calculation readiness by activity |
| `calculation_results.csv` | Limited emissions calculation results |
| `core_qa_issues.csv` | Framework-neutral exception register |

Optional files:

| File | When written |
| --- | --- |
| `ghg_evaluations.csv` | GHG enabled, or IFRS S2 required GHG |
| `cbam_evaluations.csv` | CBAM enabled |
| `ifrs_s2_evaluations.csv` | IFRS S2 enabled |

Disabled adapters do not create empty optional CSV files.

## What manifest.json means

`manifest.json` records:

- schema version
- run ID
- synthetic-demo flag
- ingestion timestamp
- which adapters ran
- summary counts
- relative CSV filenames, row counts, and SHA-256 hashes

**The manifest records what the software produced; it does not certify
completeness or compliance.**

## What SHA-256 means here

Each exported CSV has a SHA-256 hash of the exact written file bytes. These are
export-artifact hashes for reproducibility checks. They do not replace the
evidence-document hashes created during ingestion.

## Why existing directories are not overwritten

If the chosen output directory already contains any file or folder, export
stops with an error. The runner never deletes or overwrites a previous bundle.

## Why no current timestamp is automatically generated

Repeated demos must stay reproducible. The CLI defaults to a fixed
`--ingested-at` value instead of using the computer clock.

## How reproducibility is preserved

- fixed synthetic input data
- explicit `run_id`
- explicit `ingested_at`
- deterministic module logic
- deterministic CSV serialization
- deterministic manifest key ordering

## Why outputs are ignored by Git

Generated exports are local analysis artifacts. Keeping them out of Git avoids
committing large regenerated files and accidental private pilot data.

## Current limitations

- Natural gas and diesel remain blocked until applicable heating values exist
- Purchased steel has no configured calculation factor
- CN 7318 remains a demonstration assumption
- CBAM and IFRS S2 remain optional downstream adapters
- No Streamlit UI yet
- No company-level totals, PDF filings, or compliance certificates

## Important statements

Generated exports are analysis artifacts, not regulatory filings.

Running all adapters does not merge the frameworks into one methodology.

The manifest records what the software produced; it does not certify
completeness or compliance.

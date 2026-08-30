# Contributing to Carbon Evidence Ledger

Thank you for helping improve Carbon Evidence Ledger. Contributions should
preserve the project's core goals: auditability, clear evidence lineage,
deterministic calculations, and safe handling of company data.

## Before you start

- Use GitHub Issues for reproducible bugs and focused feature proposals.
- Do not post credentials, personal information, or confidential company data.
- Use synthetic or fully anonymized fixtures in code, tests, screenshots, and
  discussions.
- Keep GHG Protocol, IFRS S2 readiness, Taiwan regulatory requirements, and
  other frameworks conceptually separate.
- Do not present prototype output as legal, assurance, customs, or compliance
  advice.

## Development setup

Python 3.11 or later is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Run the application locally:

```bash
streamlit run streamlit_app.py
```

## Making a change

1. Create a short, focused branch from `main`.
2. Add or update tests for behavior changes.
3. Keep customer-facing text available in Traditional Chinese and English.
4. Preserve provenance fields and deterministic identifiers in data workflows.
5. Update documentation when behavior, limitations, or setup steps change.
6. Run the relevant checks before opening a pull request.

```bash
make lint
make test
```

For a full local check:

```bash
make check
```

Browser tests require the optional end-to-end dependencies:

```bash
python -m pip install -e ".[e2e]"
pytest -m e2e
```

## Data and regulatory-reference changes

Changes to calculation factors, regulatory mappings, or official references
need extra care:

- identify the official source and retrieval date;
- retain source URLs, hashes, versions, and activation status;
- never silently replace an active factor or rule;
- add regression coverage for changed calculations or applicability outcomes;
- keep real customer activity data out of Git.

## Pull requests

A useful pull request includes:

- a concise explanation of the user problem;
- the chosen solution and important trade-offs;
- tests or verification evidence;
- screenshots for visible interface changes;
- any new limitations, migration notes, or reference-source changes.

Keep pull requests small enough to review. Unrelated cleanup should be proposed
separately.

## Reporting security concerns

Do not open a public issue for a potential vulnerability. Follow
[SECURITY.md](SECURITY.md) and use GitHub's private security-advisory channel.


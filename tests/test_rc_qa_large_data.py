"""RC QA — large-data fixtures, CSV/XLSX parity, and performance observations."""

from __future__ import annotations

import time
from decimal import Decimal

import pandas as pd
import pytest
from rc_qa_support import (
    REPO_ROOT,
    assert_blocked_not_zero,
    calculated_rows,
    calculated_tco2e_sum,
    csv_to_xlsx_bytes,
    dataset_a_csv,
    dataset_b_csv,
    dataset_c_csv,
    dataset_clean_1000_csv,
    dataset_d_csv,
    dataset_e_csv,
    diesel_tco2e,
    electricity_tco2e,
    intake_and_run,
    ng1_tco2e,
    ng2_tco2e,
    write_rc_qa_fixtures,
)

from carbon_ledger.ui.view_models import calculated_emissions_summary

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "rc_qa"
ELEC_2025 = Decimal("0.466")
RUNTIME_LOG = REPO_ROOT / "artifacts" / "e2e" / "rc_qa_runtime.txt"


@pytest.fixture(scope="module", autouse=True)
def persist_fixtures() -> None:
    write_rc_qa_fixtures(FIXTURE_DIR)


def _status_by_type(result) -> dict[str, set[str]]:
    activities = result.activity_records_accepted.set_index("record_id")
    calcs = result.calculation_results.set_index("record_id")
    out: dict[str, set[str]] = {}
    for record_id, row in activities.iterrows():
        activity = str(row["activity_type"])
        status = str(calcs.loc[record_id, "calculation_status"])
        out.setdefault(activity, set()).add(status)
    return out


def test_dataset_a_clean_single_site_calculates() -> None:
    csv = dataset_a_csv(rows=120)
    assert csv.count("\n") >= 121
    result, intake = intake_and_run(csv, run_id="rc_a", file_name="dataset_a.csv")
    assert intake.accepted_count >= 120
    assert intake.rejected_count == 0
    statuses = _status_by_type(result)
    for activity in ("grid_electricity", "natural_gas", "diesel"):
        assert statuses[activity] == {"calculated"}
    expected = (
        electricity_tco2e(Decimal("100"), ELEC_2025) * 30
        + ng1_tco2e(Decimal("10")) * 30
        + ng2_tco2e(Decimal("10")) * 30
        + diesel_tco2e(Decimal("5")) * 30
    )
    _approx = abs(calculated_tco2e_sum(result) - expected)
    assert _approx < Decimal("1e-6")
    sites = set(result.activity_records_accepted["site_id"].astype(str))
    assert sites == {"高雄廠"}
    assert_blocked_not_zero(result)


def test_dataset_b_multi_site_keeps_steel_unsupported() -> None:
    csv = dataset_b_csv(rows=200)
    result, intake = intake_and_run(csv, run_id="rc_b", file_name="dataset_b.csv")
    assert intake.accepted_count >= 200
    statuses = _status_by_type(result)
    assert statuses["grid_electricity"] == {"calculated"}
    assert statuses["natural_gas"] == {"calculated"}
    assert statuses["diesel"] == {"calculated"}
    assert "calculated" not in statuses["purchased_steel"]
    sites = set(result.activity_records_accepted["site_id"].astype(str))
    assert {"高雄廠", "台中廠", "台北倉"}.issubset(sites)
    by_site = (
        result.activity_records_accepted.merge(
            result.calculation_results[["record_id", "calculation_status"]],
            on="record_id",
        )
        .groupby("site_id")["record_id"]
        .nunique()
    )
    assert by_site.min() > 0
    assert_blocked_not_zero(result)
    steel_ids = result.activity_records_accepted.loc[
        result.activity_records_accepted["activity_type"] == "purchased_steel",
        "record_id",
    ]
    steel = result.calculation_results[
        result.calculation_results["record_id"].isin(steel_ids)
    ]
    numeric = pd.to_numeric(steel["calculated_tco2e"], errors="coerce")
    assert numeric.isna().all()


def test_dataset_c_partial_does_not_fail_whole_file() -> None:
    csv = dataset_c_csv(rows=150)
    result, intake = intake_and_run(
        csv,
        run_id="rc_c",
        file_name="dataset_c.csv",
        natural_gas_subtype="unknown",
        diesel_context="unknown",
    )
    assert intake.accepted_count >= 100
    statuses = _status_by_type(result)
    assert "calculated" in statuses.get("grid_electricity", set())
    assert "calculated" in statuses.get("natural_gas", set())
    assert "calculated" in statuses.get("diesel", set())
    assert "blocked_natural_gas_type_required" in statuses.get("natural_gas", set())
    diesel_status = statuses.get("diesel", set())
    assert any(item != "calculated" for item in diesel_status)
    assert calculated_emissions_summary(result)["calculated_row_count"] > 0
    assert_blocked_not_zero(result)


def test_dataset_d_business_column_names_map() -> None:
    csv = dataset_d_csv(rows=180)
    result, intake = intake_and_run(csv, run_id="rc_d", file_name="dataset_d.csv")
    assert intake.accepted_count >= 180
    text = csv
    assert "能源項目" in text
    assert "grid_electricity" not in text
    statuses = _status_by_type(result)
    assert statuses["grid_electricity"] == {"calculated"}
    assert "calculated" not in statuses["purchased_steel"]
    assert_blocked_not_zero(result)


def test_dataset_e_dirty_stress_no_crash_no_fake_zero() -> None:
    csv = dataset_e_csv(rows=300)
    result, intake = intake_and_run(
        csv,
        run_id="rc_e",
        file_name="dataset_e.csv",
        natural_gas_subtype="unknown",
        diesel_context="unknown",
    )
    assert intake.total_count >= 300
    assert intake.rejected_count > 0
    assert intake.accepted_count > 0
    assert not calculated_rows(result).empty
    assert_blocked_not_zero(result)
    issues = result.core_qa_issues
    assert not issues.empty or intake.rejected_count > 0


def test_csv_xlsx_parity_on_dataset_a() -> None:
    csv = dataset_a_csv(rows=120)
    csv_result, csv_intake = intake_and_run(
        csv, run_id="rc_a_csv", file_name="dataset_a.csv"
    )
    xlsx = csv_to_xlsx_bytes(csv)
    xlsx_result, xlsx_intake = intake_and_run(
        csv,
        run_id="rc_a_xlsx",
        file_name="dataset_a.xlsx",
        data=xlsx,
    )
    assert csv_intake.accepted_count == xlsx_intake.accepted_count
    assert len(calculated_rows(csv_result)) == len(calculated_rows(xlsx_result))
    assert abs(
        float(calculated_tco2e_sum(csv_result))
        - float(calculated_tco2e_sum(xlsx_result))
    ) < 1e-9


def test_dataset_e_runtime_observation() -> None:
    csv = dataset_e_csv(rows=300)
    started = time.perf_counter()
    result, intake = intake_and_run(
        csv,
        run_id="rc_e_perf",
        file_name="dataset_e.csv",
        natural_gas_subtype="unknown",
        diesel_context="unknown",
    )
    elapsed = time.perf_counter() - started
    RUNTIME_LOG.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_LOG.write_text(
        f"dataset_e_300_rows_seconds={elapsed:.3f}\n"
        f"accepted={intake.accepted_count} rejected={intake.rejected_count}\n"
        f"calculated={len(calculated_rows(result))}\n",
        encoding="utf-8",
    )
    assert elapsed < 120
    assert intake.accepted_count > 0


def test_generated_1000_row_clean_runtime() -> None:
    csv = dataset_clean_1000_csv()
    started = time.perf_counter()
    result, intake = intake_and_run(csv, run_id="rc_1000", file_name="dataset_1000.csv")
    elapsed = time.perf_counter() - started
    existing = RUNTIME_LOG.read_text(encoding="utf-8") if RUNTIME_LOG.exists() else ""
    RUNTIME_LOG.write_text(
        existing + f"dataset_1000_rows_seconds={elapsed:.3f}\n"
        f"accepted={intake.accepted_count} calculated={len(calculated_rows(result))}\n",
        encoding="utf-8",
    )
    assert intake.accepted_count == 1000
    assert len(calculated_rows(result)) == 1000
    assert elapsed < 180

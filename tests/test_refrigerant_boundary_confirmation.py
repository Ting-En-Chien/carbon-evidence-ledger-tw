"""Organizational-boundary confirmation for refrigerant refill rows."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from carbon_ledger.activity_boundary_decisions import (
    ERROR_EVIDENCE_REQUIRED,
    SCHEMA_VERSION,
    apply_activity_boundary_decisions,
    build_decision,
    derive_effective_ownership_and_boundary,
    validate_confirmation_input,
)
from carbon_ledger.company_workspace import CompanyWorkspace
from carbon_ledger.intake import (
    ColumnMapping,
    IntakeMetadata,
    build_and_validate_intake,
    default_value_maps,
    parse_uploaded_table,
    suggest_activity_type,
    suggest_column_mapping,
    suggest_unit,
)
from carbon_ledger.pipeline import run_uploaded_pipeline
from carbon_ledger.ui.i18n import LANG_EN, LANG_ZH, MESSAGES
from carbon_ledger.ui.state import (
    STATE_ACTIVITY_BOUNDARY_DECISIONS,
    STATE_INTAKE_RESULT,
    activity_boundary_decisions_from_state,
    initialize_ui_state,
    run_uploaded_analysis,
    save_activity_boundary_decision_in_session,
    withdraw_activity_boundary_decision_in_session,
)
from carbon_ledger.ui.view_models import (
    calculated_emissions_by_product_scope,
    calculated_emissions_summary,
    company_inventory_emissions_summary,
    inventory_status_counts,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXED_INGESTED_AT = pd.Timestamp("2025-02-01T00:00:00Z")

_HEADER = (
    "activity_type,activity_value,unit,activity_start_date,activity_end_date,"
    "refrigerant_code,refill_confirmed,ownership_control,"
    "organizational_boundary_status"
)
_R410A_THIRD_PARTY = (
    "冷媒實際補充,2,kg,2025-01-01,2025-12-31,R-410A,是,第三方,納入"
)
_R134A_OWNED_OUTSIDE = (
    "冷媒實際補充,15,kg,2025-01-01,2025-12-31,R-134a,是,公司所有,不納入"
)
_ELECTRICITY = "外購電力,50000,kWh,2025-01-01,2025-12-31,,,,"

_I18N_KEYS = (
    "dash.kpi.inventory",
    "dash.result_preliminary_body",
    "dash.result_incomplete_sources",
    "boundary.confirm.title",
    "boundary.confirm.save",
    "boundary.confirm.evidence_required",
    "boundary.outcome.included_scope_1",
    "boundary.outcome.excluded_outside",
    "boundary.outcome.still_needs_review",
    "status.outside_boundary",
    "status.needs_review",
)


def _metadata() -> IntakeMetadata:
    return IntakeMetadata(
        source_name="refrigerant_boundary.csv",
        site_id="高雄廠",
        document_date=date(2025, 12, 31),
        data_quality_tier="unknown",
        intake_run_id="refrigerant_boundary",
        ingested_at=FIXED_INGESTED_AT,
    )


def _mapping_for(table) -> ColumnMapping:
    suggestions = suggest_column_mapping(list(table.columns))
    activity_map, unit_map = default_value_maps(
        table,
        ColumnMapping(
            activity_type_column=suggestions["activity_type"],
            activity_value_column=suggestions["activity_value"],
            unit_column=suggestions["unit"],
        ),
    )
    activity_map = {
        key: value or suggest_activity_type(key) for key, value in activity_map.items()
    }
    unit_map = {key: value or suggest_unit(key) for key, value in unit_map.items()}
    return ColumnMapping(
        activity_type_column=suggestions["activity_type"],
        activity_value_column=suggestions["activity_value"],
        unit_column=suggestions["unit"],
        use_file_dates=True,
        start_date_column=suggestions["activity_start_date"],
        end_date_column=suggestions["activity_end_date"],
        activity_type_value_map=activity_map,
        unit_value_map=unit_map,
        electricity_context="enterprise",
    )


def _csv(*rows: str) -> str:
    return "\n".join((_HEADER, *rows, ""))


def _intake(*rows: str):
    text = _csv(*rows)
    table = parse_uploaded_table(
        file_name="refrigerant_boundary.csv",
        data=text.encode("utf-8"),
    )
    return build_and_validate_intake(table, _mapping_for(table), _metadata())


def _run(intake):
    return run_uploaded_pipeline(
        REPO_ROOT,
        run_id="refrigerant_boundary",
        ingested_at=FIXED_INGESTED_AT,
        source_documents=intake.source_documents,
        accepted_activities=intake.accepted_activities,
        include_ghg=True,
    )


def _rerun_with_decisions(intake, decisions):
    effective = apply_activity_boundary_decisions(
        intake.accepted_activities, decisions
    )
    return run_uploaded_pipeline(
        REPO_ROOT,
        run_id="refrigerant_boundary_rerun",
        ingested_at=FIXED_INGESTED_AT,
        source_documents=intake.source_documents,
        accepted_activities=effective,
        include_ghg=True,
    )


def _refrigerant_row(intake):
    accepted = intake.accepted_activities
    return accepted[accepted["activity_type"] == "refrigerant_refill"].iloc[0]


def _ghg_for(result, record_id):
    ghg = result.ghg_evaluations
    return ghg[ghg["record_id"] == record_id].iloc[0]


def _calc_for(result, record_id):
    calcs = result.calculation_results
    return calcs[calcs["record_id"] == record_id].iloc[0]


def _include_decision(
    record_id: str,
    *,
    year: int = 2025,
    evidence: str = "EV-410A",
    reporting_period_id: str = "",
):
    return build_decision(
        record_id=record_id,
        reporting_year=year,
        reporting_period_id=reporting_period_id,
        legal_owner="third_party",
        operational_controller="company",
        organizational_boundary_status="inside",
        boundary_basis="operational_control",
        evidence_reference=evidence,
        rationale="company operates the equipment",
    )


def _activity_frame(
    record_id: str,
    *,
    year: int = 2025,
    reporting_period_id: str | None = None,
    ownership: str = "third_party",
) -> pd.DataFrame:
    payload: dict[str, object] = {
        "record_id": record_id,
        "reporting_year": year,
        "ownership_control": ownership,
        "organizational_boundary_status": "unknown",
    }
    if reporting_period_id is not None:
        payload["reporting_period_id"] = reporting_period_id
    return pd.DataFrame([payload])


def test_third_party_r410a_is_calculated_but_not_in_inventory() -> None:
    intake = _intake(_R410A_THIRD_PARTY)
    result = _run(intake)
    row = _refrigerant_row(intake)
    calc = _calc_for(result, row["record_id"])
    mapped = _ghg_for(result, row["record_id"])
    assert str(calc["calculation_status"]) == "calculated"
    assert float(calc["calculated_tco2e"]) == pytest.approx(3.847)
    assert str(mapped["mapping_status"]) == "needs_review"
    assert str(mapped["ghg_scope"]) != "scope_1"
    assert str(mapped["ghg_scope"]) != "scope_3"
    scopes = calculated_emissions_by_product_scope(result)
    assert scopes["scope_1"] == pytest.approx(0.0)
    inventory = company_inventory_emissions_summary(result)
    assert inventory["inventory_row_count"] == 0
    assert not inventory["inventory_tco2e"]
    technical = calculated_emissions_summary(result)
    assert technical["calculated_row_count"] == 1
    assert technical["calculated_tco2e"] == pytest.approx(3.847)


def test_operational_control_confirmation_includes_same_tco2e() -> None:
    intake = _intake(_ELECTRICITY, _R410A_THIRD_PARTY)
    before = _run(intake)
    row = _refrigerant_row(intake)
    before_calc = _calc_for(before, row["record_id"])
    before_inventory = company_inventory_emissions_summary(before)
    before_counts = inventory_status_counts(before)
    assert str(_ghg_for(before, row["record_id"])["mapping_status"]) == "needs_review"
    assert before_counts["included_in_inventory"] == 1

    decision = _include_decision(str(row["record_id"]))
    after = _rerun_with_decisions(intake, [decision])
    after_calc = _calc_for(after, row["record_id"])
    mapped = _ghg_for(after, row["record_id"])
    assert str(mapped["mapping_status"]) == "mapped"
    assert str(mapped["ghg_scope"]) == "scope_1"
    assert float(after_calc["calculated_tco2e"]) == pytest.approx(
        float(before_calc["calculated_tco2e"])
    )
    assert float(after_calc["gwp_value"]) == pytest.approx(
        float(before_calc["gwp_value"])
    )
    assert str(intake.accepted_activities.loc[
        intake.accepted_activities["record_id"] == row["record_id"],
        "ownership_control",
    ].iloc[0]) == "third_party"
    assert str(after.activity_records_accepted.loc[
        after.activity_records_accepted["record_id"] == row["record_id"],
        "ownership_control",
    ].iloc[0]) == "controlled"

    after_inventory = company_inventory_emissions_summary(after)
    after_counts = inventory_status_counts(after)
    delta = float(after_inventory["inventory_tco2e"] or 0) - float(
        before_inventory["inventory_tco2e"] or 0
    )
    assert delta == pytest.approx(float(after_calc["calculated_tco2e"]))
    assert after_counts["included_in_inventory"] == (
        before_counts["included_in_inventory"] + 1
    )
    scopes = calculated_emissions_by_product_scope(after)
    assert scopes["scope_1"] == pytest.approx(float(after_calc["calculated_tco2e"]))


def test_prior_year_decision_does_not_apply_to_current_year() -> None:
    intake = _intake(_R410A_THIRD_PARTY)
    row = _refrigerant_row(intake)
    stale = _include_decision(str(row["record_id"]), year=2024)
    effective = apply_activity_boundary_decisions(
        intake.accepted_activities, [stale]
    )
    assert str(effective.iloc[0]["ownership_control"]) == "third_party"
    result = _rerun_with_decisions(intake, [stale])
    mapped = _ghg_for(result, row["record_id"])
    assert str(mapped["mapping_status"]) == "needs_review"
    assert company_inventory_emissions_summary(result)["inventory_row_count"] == 0


def test_owned_outside_stays_outside_boundary() -> None:
    intake = _intake(_R134A_OWNED_OUTSIDE)
    result = _run(intake)
    row = _refrigerant_row(intake)
    mapped = _ghg_for(result, row["record_id"])
    calc = _calc_for(result, row["record_id"])
    assert str(mapped["mapping_status"]) == "outside_boundary"
    assert str(calc["calculation_status"]) == "calculated"
    assert company_inventory_emissions_summary(result)["inventory_row_count"] == 0
    decision = build_decision(
        record_id=str(row["record_id"]),
        reporting_year=2025,
        legal_owner="company",
        operational_controller="company",
        organizational_boundary_status="outside",
        boundary_basis="operational_control",
        evidence_reference="EV-OUT",
    )
    ownership, boundary = derive_effective_ownership_and_boundary(decision)
    assert (ownership, boundary) == (None, "outside")
    after = _rerun_with_decisions(intake, [decision])
    assert str(_ghg_for(after, row["record_id"])["mapping_status"]) == (
        "outside_boundary"
    )


def test_blank_evidence_cannot_complete_confirmation() -> None:
    errors = validate_confirmation_input(
        record_id="up_test_r0002",
        reporting_year=2025,
        legal_owner="company",
        operational_controller="company",
        organizational_boundary_status="inside",
        boundary_basis="operational_control",
        evidence_reference="   ",
    )
    assert ERROR_EVIDENCE_REQUIRED in errors
    with pytest.raises(ValueError, match=ERROR_EVIDENCE_REQUIRED):
        build_decision(
            record_id="up_test_r0002",
            reporting_year=2025,
            legal_owner="company",
            operational_controller="company",
            organizational_boundary_status="inside",
            boundary_basis="operational_control",
            evidence_reference="",
        )


def test_shared_and_unknown_control_are_not_guessed() -> None:
    intake = _intake(_R410A_THIRD_PARTY)
    row = _refrigerant_row(intake)
    shared = build_decision(
        record_id=str(row["record_id"]),
        reporting_year=2025,
        legal_owner="third_party",
        operational_controller="shared",
        organizational_boundary_status="inside",
        boundary_basis="operational_control",
        evidence_reference="EV-SHARED",
    )
    unknown = build_decision(
        record_id=str(row["record_id"]),
        reporting_year=2025,
        legal_owner="unknown",
        operational_controller="unknown",
        organizational_boundary_status="inside",
        boundary_basis="unknown",
        evidence_reference="EV-UNK",
    )
    assert derive_effective_ownership_and_boundary(shared) is None
    assert derive_effective_ownership_and_boundary(unknown) is None
    for decision in (shared, unknown):
        result = _rerun_with_decisions(intake, [decision])
        mapped = _ghg_for(result, row["record_id"])
        assert str(mapped["mapping_status"]) == "needs_review"
        assert str(mapped["ghg_scope"]) not in {"scope_1", "scope_3"}
        assert company_inventory_emissions_summary(result)["inventory_row_count"] == 0


def test_withdrawn_decision_updates_inventory_on_rerun() -> None:
    intake = _intake(_R410A_THIRD_PARTY)
    row = _refrigerant_row(intake)
    record_id = str(row["record_id"])
    state: dict = {}
    initialize_ui_state(state)
    state[STATE_INTAKE_RESULT] = intake
    first = run_uploaded_analysis(state, run_id="rf_confirm_1")
    assert company_inventory_emissions_summary(first)["inventory_row_count"] == 0
    first_total = calculated_emissions_summary(first)["calculated_tco2e"]

    save_activity_boundary_decision_in_session(
        state, _include_decision(record_id)
    )
    included = run_uploaded_analysis(state, run_id="rf_confirm_2")
    assert included is not first
    mapped = _ghg_for(included, record_id)
    assert str(mapped["mapping_status"]) == "mapped"
    included_inventory = company_inventory_emissions_summary(included)
    assert included_inventory["inventory_row_count"] == 1
    assert included_inventory["inventory_tco2e"] == pytest.approx(3.847)
    assert calculated_emissions_summary(included)["calculated_tco2e"] == pytest.approx(
        first_total
    )

    withdraw_activity_boundary_decision_in_session(
        state,
        record_id=record_id,
        reporting_year=2025,
        reporting_period_id="",
    )
    withdrawn = run_uploaded_analysis(state, run_id="rf_confirm_3")
    assert str(_ghg_for(withdrawn, record_id)["mapping_status"]) == "needs_review"
    assert company_inventory_emissions_summary(withdrawn)["inventory_row_count"] == 0


def test_inventory_total_is_mapped_scope_1_plus_scope_2() -> None:
    intake = _intake(_ELECTRICITY, _R410A_THIRD_PARTY)
    result = _run(intake)
    technical = calculated_emissions_summary(result)
    inventory = company_inventory_emissions_summary(result)
    scopes = calculated_emissions_by_product_scope(result)
    counts = inventory_status_counts(result)
    assert technical["calculated_row_count"] == 2
    assert inventory["inventory_row_count"] == 1
    assert counts["technically_calculated"] == 2
    assert counts["included_in_inventory"] == 1
    assert counts["needs_review"] == 1
    expected = float(scopes["scope_1"] or 0) + float(scopes["scope_2"] or 0)
    assert inventory["inventory_tco2e"] == pytest.approx(expected)
    assert technical["calculated_tco2e"] != pytest.approx(expected)


def test_workspace_decisions_are_period_isolated(tmp_path: Path) -> None:
    workspace = CompanyWorkspace(tmp_path, "entity-testco")
    decision_2024 = _include_decision("up_test_r0008", year=2024)
    workspace.save_activity_boundary_decision(decision_2024)
    assert workspace.load_activity_boundary_decisions("period-2025") == []
    loaded = workspace.load_activity_boundary_decisions("period-2024")
    assert len(loaded) == 1
    assert loaded[0].reporting_year == 2024
    assert loaded[0].schema_version == SCHEMA_VERSION


def test_same_year_period_a_decision_does_not_apply_to_period_b() -> None:
    record_id = "up_test_r0100"
    decision_a = _include_decision(record_id, reporting_period_id="period-A")
    period_b = _activity_frame(record_id, reporting_period_id="period-B")
    skipped = apply_activity_boundary_decisions(period_b, [decision_a])
    assert str(skipped.iloc[0]["ownership_control"]) == "third_party"
    period_a = _activity_frame(record_id, reporting_period_id="period-A")
    applied = apply_activity_boundary_decisions(period_a, [decision_a])
    assert str(applied.iloc[0]["ownership_control"]) == "controlled"


def test_same_year_period_decisions_do_not_overwrite_each_other() -> None:
    record_id = "up_test_r0101"
    state: dict = {}
    initialize_ui_state(state)
    save_activity_boundary_decision_in_session(
        state,
        _include_decision(record_id, reporting_period_id="period-A", evidence="EV-A"),
    )
    save_activity_boundary_decision_in_session(
        state,
        _include_decision(record_id, reporting_period_id="period-B", evidence="EV-B"),
    )
    loaded = {
        item.reporting_period_id: item
        for item in activity_boundary_decisions_from_state(state)
        if not item.withdrawn
    }
    assert loaded["period-A"].evidence_reference == "EV-A"
    assert loaded["period-B"].evidence_reference == "EV-B"


def test_withdraw_period_a_does_not_withdraw_period_b() -> None:
    record_id = "up_test_r0102"
    state: dict = {}
    initialize_ui_state(state)
    save_activity_boundary_decision_in_session(
        state, _include_decision(record_id, reporting_period_id="period-A")
    )
    save_activity_boundary_decision_in_session(
        state, _include_decision(record_id, reporting_period_id="period-B")
    )
    withdraw_activity_boundary_decision_in_session(
        state,
        record_id=record_id,
        reporting_year=2025,
        reporting_period_id="period-A",
    )
    loaded = {
        item.reporting_period_id: item
        for item in activity_boundary_decisions_from_state(state)
    }
    assert loaded["period-A"].withdrawn is True
    assert loaded["period-B"].withdrawn is False


def test_period_qualified_decision_does_not_apply_to_activity_without_period() -> None:
    record_id = "up_test_r0103"
    decision = _include_decision(record_id, reporting_period_id="period-A")
    activity = _activity_frame(record_id)
    effective = apply_activity_boundary_decisions(activity, [decision])
    assert str(effective.iloc[0]["ownership_control"]) == "third_party"


def test_legacy_decision_without_period_falls_back_to_record_and_year() -> None:
    record_id = "up_test_r0104"
    decision = _include_decision(record_id, reporting_period_id="")
    activity = _activity_frame(record_id)
    effective = apply_activity_boundary_decisions(activity, [decision])
    assert str(effective.iloc[0]["ownership_control"]) == "controlled"
    assert str(effective.iloc[0]["organizational_boundary_status"]) == "inside"


def test_confirmation_i18n_keys_exist() -> None:
    for key in _I18N_KEYS:
        entry = MESSAGES[key]
        assert entry[LANG_ZH].strip()
        assert entry[LANG_EN].strip()
    body_zh = MESSAGES["dash.result_preliminary_body"][LANG_ZH]
    assert "尚未納入計算" not in body_zh
    assert "已納入公司盤查" in body_zh
    assert MESSAGES["boundary.confirm.save"][LANG_ZH] == "儲存判定並重新分析"
    assert STATE_ACTIVITY_BOUNDARY_DECISIONS == "activity_boundary_decisions"

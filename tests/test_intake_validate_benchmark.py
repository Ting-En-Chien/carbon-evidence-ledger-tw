"""Optional 1,000-row intake validation benchmark.

Not part of the standard quality gate. Run with:

    CEL_INTAKE_BENCH=1 pytest tests/test_intake_validate_benchmark.py -s
"""

from __future__ import annotations

import os
import time
from datetime import date

import pandas as pd
import pytest

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

pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.skipif(
        not os.environ.get("CEL_INTAKE_BENCH"),
        reason="set CEL_INTAKE_BENCH=1 to run the 1000-row intake benchmark",
    ),
]

FIXED_INGESTED_AT = pd.Timestamp("2025-02-01T00:00:00Z")


def _metadata() -> IntakeMetadata:
    return IntakeMetadata(
        source_name="ops.csv",
        site_id="高雄廠",
        document_date=date(2025, 1, 31),
        data_quality_tier="unknown",
        intake_run_id="progress_bench",
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
        key: value or suggest_activity_type(key)
        for key, value in activity_map.items()
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
    )


def _thousand_csv() -> str:
    header = (
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
    )
    rows = [
        "grid_electricity,1000,kWh,2025-01-01,2025-01-31" for _ in range(1000)
    ]
    return header + "\n".join(rows) + "\n"


def test_thousand_row_batch_benchmark_prints_timings() -> None:
    table = parse_uploaded_table(
        file_name="ops.csv", data=_thousand_csv().encode("utf-8")
    )
    mapping = _mapping_for(table)
    metadata = _metadata()
    start_row = time.perf_counter()
    row_result = build_and_validate_intake(
        table, mapping, metadata, schema_strategy="row"
    )
    row_s = time.perf_counter() - start_row
    start_batch = time.perf_counter()
    batch_result = build_and_validate_intake(
        table, mapping, metadata, schema_strategy="batch"
    )
    batch_s = time.perf_counter() - start_batch
    assert int(batch_result.accepted_count) == 1000
    assert int(row_result.accepted_count) == 1000
    print(
        f"INTAKE_VALIDATE_BENCH row={row_s:.3f}s batch={batch_s:.3f}s "
        f"n={batch_result.accepted_count}"
    )

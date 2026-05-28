from __future__ import annotations

import pytest

from daylib_ursa.analysis_commands import analysis_command_payload


@pytest.mark.parametrize(
    "command_id",
    [
        "illumina_run_qc",
        "illumina_bclconvert",
        "illumina_run_qc_bclconvert",
        "ont_run_qc",
        "ultima_run_qc",
    ],
)
def test_dayec_5014_run_directory_commands_are_run_analysis(command_id: str) -> None:
    payload = analysis_command_payload(command_id)

    assert payload["command_id"] == command_id
    assert payload["command_class"] == "run_analysis"
    assert payload["input_contract"] == "run_context"

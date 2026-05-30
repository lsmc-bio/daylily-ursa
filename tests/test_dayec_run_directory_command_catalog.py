from __future__ import annotations

import pytest

from daylib_ursa.analysis_commands import analysis_command_payload, preview_analysis_command


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
def test_dayec_run_directory_commands_are_run_analysis(command_id: str) -> None:
    payload = analysis_command_payload(command_id)

    assert payload["command_id"] == command_id
    assert payload["command_class"] == "run_analysis"
    assert payload["input_contract"] == "run_context"


def test_dayec_simple_test_command_is_no_input_utility() -> None:
    payload = analysis_command_payload("simple-test")

    assert payload["command_id"] == "simple-test"
    assert payload["command_class"] == "utility"
    assert payload["input_contract"] == "none"
    assert payload["requires_staging"] is False
    assert payload["requires_run_mount"] is False


def test_illumina_bclconvert_run_directory_command_uses_real_run_context() -> None:
    payload = analysis_command_payload("illumina_run_qc_bclconvert")
    runtime_parameters = payload["runtime_parameters"]

    assert runtime_parameters["run_context_file"] == "config/runs.tsv"
    assert runtime_parameters["bootstrap_bclconvert"] == "true"
    assert "samples_table" not in runtime_parameters
    assert "units_table" not in runtime_parameters

    preview = preview_analysis_command(
        "illumina_run_qc_bclconvert",
        profile="lsmc",
        region="us-west-2",
        cluster_name="goodole3",
        session_name="M-TEST-RUN",
        destination="s3://lsmc-dayoa-analysis-results-usw2/owy-run-directory-analysis/",
        project="daylily",
        analysis_id="M-TEST-ANALYSIS",
        executing_entity="ursa",
        run_context_file="config/runs.tsv",
        export_trigger="on-success",
        dry_run=True,
    )
    argv = preview["argv"]
    rendered = " ".join(str(item) for item in argv)
    shell_preview = preview["shell_preview"]

    assert "--run-context-file" in argv
    assert "config/runs.tsv" in argv
    assert "bootstrap_bclconvert=true" in rendered
    assert "bootstrap_bclconvert=true" in shell_preview
    forbidden = (
        ".test_data/data/bclconvert/samples.tsv",
        ".test_data/data/bclconvert/units.tsv",
        "samples_table=",
        "units_table=",
    )
    for text in forbidden:
        assert text not in rendered
        assert text not in shell_preview

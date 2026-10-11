from evaluate_access_modes import run_ablation


def test_access_mode_ablation_is_reproducible_and_labels_oracle_selection(tmp_path):
    output = tmp_path / "ablation.csv"
    rows = run_ablation([31], steps=3, output=output)

    assert output.exists()
    assert len(rows) == 3 * 1 * 3
    assert {row["mode"] for row in rows} == {
        "oma_no_ris", "cnoma_no_ris", "ris_cnoma_oracle"
    }
    assert all(row["simulation_only"] is True for row in rows)
    assert all(row["selection"] == "perfect_current_CSI_oracle" for row in rows)
    assert all(0.0 <= row["delivery_rate"] <= 1.0 for row in rows)

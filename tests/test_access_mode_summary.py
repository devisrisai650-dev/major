import csv

from evaluate_access_modes import summarize_ablation


def test_access_mode_summary_reports_seed_cluster_and_paired_intervals(tmp_path):
    rows = []
    for seed, oma, cnoma, ris in [
        (1, 0.5, 0.5, 0.5),
        (2, 0.6, 0.6, 0.7),
        (3, 0.4, 0.4, 0.4),
    ]:
        for mode, delivery in [
            ("oma_no_ris", oma),
            ("cnoma_no_ris", cnoma),
            ("ris_cnoma_oracle", ris),
        ]:
            rows.append({
                "scenario": "test",
                "seed": seed,
                "mode": mode,
                "delivery_rate": delivery,
                "mean_selected_snr_db": 8.0 + seed,
                "simulation_only": True,
            })

    output = tmp_path / "access_mode_ablation.csv"
    summary = summarize_ablation(rows, output, seed=7)

    summary_path = tmp_path / "access_mode_ablation_summary.csv"
    with summary_path.open(encoding="utf-8", newline="") as file:
        saved = list(csv.DictReader(file))

    assert summary_path.exists()
    assert any(row["record_type"] == "mode_summary" for row in saved)
    paired = [row for row in summary if row["record_type"] == "paired_comparison"]
    assert paired
    assert all(row["simulation_only"] is True for row in paired)
    assert any("No benefit established" in row["interpretation"] for row in paired)

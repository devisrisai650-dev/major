import sys

import runtime


def test_runtime_passes_evaluation_repeat_argument(monkeypatch, tmp_path):
    captured = {}

    def fake_train_and_evaluate(
        train_seeds,
        eval_seeds,
        episodes,
        eval_episodes_per_seed,
        steps,
        output_dir,
        learned_weight,
    ):
        captured.update(
            train_seeds=train_seeds,
            eval_seeds=eval_seeds,
            episodes=episodes,
            eval_episodes_per_seed=eval_episodes_per_seed,
            steps=steps,
            output_dir=output_dir,
            learned_weight=learned_weight,
        )
        return [], []

    monkeypatch.setattr(runtime, "train_and_evaluate", fake_train_and_evaluate)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime.py",
            "--train-seeds",
            "2",
            "--train-episodes",
            "3",
            "--eval-seeds",
            "2",
            "--eval-episodes-per-seed",
            "4",
            "--steps",
            "5",
            "--seed",
            "100",
            "--learned-weight",
            "0.05",
            "--output-dir",
            str(tmp_path),
        ],
    )

    runtime.main()

    assert captured["train_seeds"] == [100, 101]
    assert captured["eval_seeds"] == [10100, 10101]
    assert captured["episodes"] == 3
    assert captured["eval_episodes_per_seed"] == 4
    assert captured["steps"] == 5
    assert captured["output_dir"] == tmp_path
    assert captured["learned_weight"] == 0.05

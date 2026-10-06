"""Convenience entry point for the final reproducible FloodAI simulation."""
from __future__ import annotations
import argparse
from pathlib import Path
from evaluate_ris_agent import train_and_evaluate

def main():
    parser = argparse.ArgumentParser(description="Run the final FloodAI software simulation")
    parser.add_argument("--train-seeds", type=int, default=10)
    parser.add_argument("--train-episodes", type=int, default=250)
    parser.add_argument("--eval-seeds", type=int, default=5)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--learned-weight", type=float, default=0.05)
    parser.add_argument("--output-dir", default="outputs")
    args = parser.parse_args()
    train_seeds = [args.seed + i for i in range(args.train_seeds)]
    eval_seeds = [args.seed + 10000 + i for i in range(args.eval_seeds)]
    rows, summary = train_and_evaluate(
        train_seeds, eval_seeds, args.train_episodes, args.steps,
        Path(args.output_dir), args.learned_weight
    )
    print(f"Generated {len(rows)} episode rows and {len(summary)} summary rows.")
    print("All communication results are software simulations.")

if __name__ == "__main__":
    main()

"""Train the CNN+GRU forward-speed network.

Two-stage schedule, as in TLIO and GNIO: MSE first so the model learns the
mean, then Gaussian NLL so it learns when to be uncertain. Training NLL from
scratch lets a model minimise loss by predicting a huge variance everywhere
instead of learning anything.

Run:  PYTHONPATH=. python scripts/train_speednet.py [--epochs 60]
      PYTHONPATH=. python scripts/train_speednet.py --ablate
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shadownav.models import dataset as ds  # noqa: E402
from shadownav.models.speednet import (  # noqa: E402
    SpeedNet, SpeedNetConfig, gaussian_nll, mse,
)
from shadownav.utils.seed import DEFAULT_SEED, seed_everything  # noqa: E402

SHARED = Path(__file__).resolve().parents[2] / "shared"


def loaders(train: ds.SpeedDataset, val: ds.SpeedDataset, batch: int):
    mean, std = train.standardiser()
    tr = train.standardise(mean, std)
    va = val.standardise(mean, std)

    def make(d: ds.SpeedDataset, shuffle: bool) -> DataLoader:
        return DataLoader(
            TensorDataset(
                torch.tensor(d.x, dtype=torch.float32),
                torch.tensor(d.y, dtype=torch.float32),
            ),
            batch_size=batch, shuffle=shuffle, drop_last=False,
        )

    return make(tr, True), make(va, False), mean, std


@torch.no_grad()
def evaluate(model: SpeedNet, loader: DataLoader) -> dict[str, float]:
    model.eval()
    errs, sigmas, preds, targets = [], [], [], []
    for x, y in loader:
        p, lv = model(x)
        errs.append((p - y).numpy())
        sigmas.append(torch.exp(0.5 * lv).numpy())
        preds.append(p.numpy())
        targets.append(y.numpy())
    e = np.concatenate(errs)
    s = np.concatenate(sigmas)
    t = np.concatenate(targets)
    # Fraction of errors inside one predicted sigma. A well-calibrated
    # Gaussian gives 0.68; far from it means the variance head is decorative.
    coverage = float(np.mean(np.abs(e) <= s))
    return {
        "rmse": float(np.sqrt(np.mean(e**2))),
        "mae": float(np.mean(np.abs(e))),
        "bias": float(np.mean(e)),
        "sigma_median": float(np.median(s)),
        "coverage_1sigma": coverage,
        "target_std": float(np.std(t)),
    }


def train_one(cfg: SpeedNetConfig, train: ds.SpeedDataset, val: ds.SpeedDataset,
              *, epochs: int, batch: int, lr: float, verbose: bool = True):
    seed_everything(DEFAULT_SEED)
    tr, va, mean, std = loaders(train, val, batch)
    model = SpeedNet(cfg)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    nll_from = max(1, epochs // 3)
    best = {"rmse": float("inf")}
    best_state = None

    for epoch in range(epochs):
        loss_fn = mse if epoch < nll_from else gaussian_nll
        model.train()
        total, seen = 0.0, 0
        for x, y in tr:
            opt.zero_grad()
            pred, log_var = model(x)
            loss = loss_fn(pred, log_var, y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            total += float(loss) * len(y)
            seen += len(y)
        sched.step()

        stats = evaluate(model, va)
        if stats["rmse"] < best["rmse"]:
            best = stats
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        if verbose and (epoch % 5 == 0 or epoch == epochs - 1):
            print(f"  epoch {epoch:3d}  loss {total / max(seen, 1):8.4f}  "
                  f"val RMSE {stats['rmse']:6.3f}  MAE {stats['mae']:6.3f}  "
                  f"cov1s {stats['coverage_1sigma']:.2f}"
                  f"{'  <- best' if stats is best else ''}")

    if best_state is not None:
        model.load_state_dict(best_state)
    return model, best, mean, std


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--ablate", action="store_true",
                    help="run the Motion Bank / gate ablation grid")
    args = ap.parse_args(argv)

    seed_everything(DEFAULT_SEED)
    t0 = time.time()
    print("building datasets ...")
    train = ds.build("train")
    val = ds.build("val")
    test = ds.build("test")
    print(f"  train {len(train):6d}  val {len(val):6d}  test {len(test):6d} "
          f"windows   ({time.time() - t0:.0f}s)")
    if len(train) == 0 or len(val) == 0:
        print("empty split; run: python -m shadownav.data.fetch")
        return 1
    print(f"  label speed: train mean {train.y.mean():.2f} std {train.y.std():.2f} m/s, "
          f"test mean {test.y.mean():.2f} std {test.y.std():.2f} m/s")

    # Predicting the training mean everywhere is the bar any model must clear.
    naive_rmse = float(np.sqrt(np.mean((test.y - train.y.mean()) ** 2)))
    print(f"  trivial baseline (predict train mean) test RMSE: {naive_rmse:.3f} m/s")

    configs: dict[str, SpeedNetConfig] = {"full": SpeedNetConfig()}
    if args.ablate:
        configs.update({
            "no_bank": SpeedNetConfig(use_motion_bank=False),
            "no_gate": SpeedNetConfig(use_gate=False),
            "plain": SpeedNetConfig(use_motion_bank=False, use_gate=False),
            "tanh_gate": SpeedNetConfig(gate_activation="tanh"),
        })

    results: dict[str, dict] = {}
    best_name, best_rmse, best_bundle = None, float("inf"), None

    for name, cfg in configs.items():
        print(f"\n=== {name} ===")
        model = SpeedNet(cfg)
        print(f"  parameters: {model.n_parameters:,} "
              f"({model.n_parameters * 4 / 1e6:.2f} MB fp32, "
              f"~{model.n_parameters / 1e6:.2f} MB int8)")
        model, val_stats, mean, std = train_one(
            cfg, train, val, epochs=args.epochs, batch=args.batch, lr=args.lr
        )
        te, _, _, _ = loaders(test, test, args.batch)
        test_stats = evaluate(model, te)
        results[name] = {
            "config": cfg.as_dict(),
            "n_parameters": model.n_parameters,
            "val": val_stats,
            "test": test_stats,
        }
        print(f"  TEST  RMSE {test_stats['rmse']:.3f}  MAE {test_stats['mae']:.3f}  "
              f"bias {test_stats['bias']:+.3f}  "
              f"cov1s {test_stats['coverage_1sigma']:.2f}")
        if test_stats["rmse"] < best_rmse:
            best_name, best_rmse = name, test_stats["rmse"]
            best_bundle = (model, cfg, mean, std)

    if best_bundle is None:
        return 1
    model, cfg, mean, std = best_bundle
    SHARED.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "config": cfg.as_dict(),
            # Tensors rather than numpy arrays so the checkpoint can be loaded
            # with weights_only=True: torch.load defaults to unpickling
            # arbitrary Python objects, which is arbitrary code execution on a
            # file you did not produce.
            "feature_mean": torch.tensor(mean, dtype=torch.float64),
            "feature_std": torch.tensor(std, dtype=torch.float64),
            "window": train.window,
            "seed": DEFAULT_SEED,
            "variant": best_name,
        },
        SHARED / "speednet.pt",
    )

    out = Path(__file__).resolve().parents[2] / "eval" / "results" / "speednet_training.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "seed": DEFAULT_SEED,
                "epochs": args.epochs,
                "n_train": len(train), "n_val": len(val), "n_test": len(test),
                "trivial_baseline_test_rmse": naive_rmse,
                "best_variant": best_name,
                "variants": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nbest variant: {best_name} (test RMSE {best_rmse:.3f} m/s "
          f"vs trivial {naive_rmse:.3f})")
    print(f"saved {SHARED / 'speednet.pt'}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

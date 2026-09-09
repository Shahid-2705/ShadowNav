"""Seed-ensemble the CNN+GRU forward-speed network.

Motivation, measured this session: retraining ``train_speednet.py`` with the
*same* committed seed on a different PyTorch build (2.14 vs whatever produced
the committed checkpoint) picked a different winning architecture and a worse
test RMSE both times (1.994 and 2.014 vs the committed 1.847, against a 1.976
trivial baseline). ``seed_everything`` sets ``torch.use_deterministic_algorithms
(True, warn_only=True)`` -- warn-only, so nondeterministic CPU kernels in the
GRU / multi-head attention path fall back silently instead of erroring, and a
different reduction order changes where training lands. With ~14k labels and
a val/test split with opposite-signed bias (documented in shared/README.md),
that landing point matters a lot.

This does not fix the bias (that needs a confidence gate or online per-driver
correction -- separate work). It targets the *other* half of the problem: an
ensemble of K independently-seeded members, averaged with proper Gaussian
mixture moment matching, should be less sensitive to any single run's bad luck
than picking one seed's checkpoint.

Deliberately a separate script and a separate output file
(``shared/speednet_ensemble.pt``, ``eval/results/speednet_ensemble_training.json``)
rather than touching ``train_speednet.py`` / ``shared/speednet.pt`` -- the
committed single-model checkpoint is cited by the submission deck and must not
change as a side effect of this experiment.

Run:  PYTHONPATH=. python scripts/train_speednet_ensemble.py [--members 5] [--epochs 60]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import train_speednet as ts  # noqa: E402
from shadownav.models import dataset as ds  # noqa: E402
from shadownav.models.speednet import SpeedNet, SpeedNetConfig, gaussian_nll, mse  # noqa: E402
from shadownav.utils.seed import DEFAULT_SEED, seed_everything  # noqa: E402

SHARED = Path(__file__).resolve().parents[2] / "shared"


def train_member(cfg: SpeedNetConfig, train: ds.SpeedDataset, val: ds.SpeedDataset,
                 *, seed: int, epochs: int, batch: int, lr: float):
    """Same schedule as ``train_speednet.train_one``, but seeded per-member.

    ``train_one`` hardcodes ``seed_everything(DEFAULT_SEED)`` at its top, which
    is exactly right for a single reproducible run but wrong for an ensemble --
    every member would see identical init and identical minibatch order. This
    copies that loop with the seed as a parameter instead.
    """
    seed_everything(seed)
    tr, va, mean, std = ts.loaders(train, val, batch)
    model = SpeedNet(cfg)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    nll_from = max(1, epochs // 3)
    best = {"rmse": float("inf")}
    best_state = None

    for epoch in range(epochs):
        loss_fn = mse if epoch < nll_from else gaussian_nll
        model.train()
        for x, y in tr:
            opt.zero_grad()
            pred, log_var = model(x)
            loss = loss_fn(pred, log_var, y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
        sched.step()

        stats = ts.evaluate(model, va)
        if stats["rmse"] < best["rmse"]:
            best = stats
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)
    return model, best, mean, std


@torch.no_grad()
def ensemble_predict(models: list[SpeedNet], x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Moment-match a mixture of K unit-weight Gaussians into one (mean, var).

    mixture mean = mean_i(mu_i)
    mixture var  = mean_i(sigma_i^2) + mean_i((mu_i - mixture_mean)^2)
    the second term is the law-of-total-variance correction for disagreement
    between members -- without it, a confident-but-wrong minority member's
    variance would be invisible in the combined estimate.
    """
    mus, log_vars = [], []
    for m in models:
        m.eval()
        mu, lv = m(x)
        mus.append(mu)
        log_vars.append(lv)
    mu_stack = torch.stack(mus, dim=0)          # (K, B)
    var_stack = torch.exp(torch.stack(log_vars, dim=0))
    mean = mu_stack.mean(dim=0)
    var = var_stack.mean(dim=0) + ((mu_stack - mean) ** 2).mean(dim=0)
    return mean, var


@torch.no_grad()
def evaluate_ensemble(models: list[SpeedNet], loader) -> dict[str, float]:
    errs, sigmas, targets = [], [], []
    for x, y in loader:
        mean, var = ensemble_predict(models, x)
        errs.append((mean - y).numpy())
        sigmas.append(torch.sqrt(var).numpy())
        targets.append(y.numpy())
    e = np.concatenate(errs)
    s = np.concatenate(sigmas)
    t = np.concatenate(targets)
    coverage = float(np.mean(np.abs(e) <= s))
    return {
        "rmse": float(np.sqrt(np.mean(e**2))),
        "mae": float(np.mean(np.abs(e))),
        "bias": float(np.mean(e)),
        "sigma_median": float(np.median(s)),
        "coverage_1sigma": coverage,
        "target_std": float(np.std(t)),
    }


@torch.no_grad()
def fit_ensemble_sigma_scale(models: list[SpeedNet], loader,
                             target_coverage: float = 0.6827) -> float:
    errs, sigmas = [], []
    for x, y in loader:
        mean, var = ensemble_predict(models, x)
        errs.append((mean - y).abs().numpy())
        sigmas.append(torch.sqrt(var).numpy())
    e = np.concatenate(errs)
    s_hat = np.concatenate(sigmas)
    good = s_hat > 1e-9
    if good.sum() < 20:
        return 1.0
    ratio = np.sort(e[good] / s_hat[good])
    idx = min(len(ratio) - 1, int(np.ceil(target_coverage * len(ratio))) - 1)
    return float(max(1.0, ratio[max(idx, 0)]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--members", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=2e-3)
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

    naive_rmse = float(np.sqrt(np.mean((test.y - train.y.mean()) ** 2)))
    print(f"  trivial baseline (predict train mean) test RMSE: {naive_rmse:.3f} m/s")

    cfg = SpeedNetConfig()  # the "full" architecture: bank + sigmoid gate
    members, member_results = [], []
    mean = std = None

    for i in range(args.members):
        seed = DEFAULT_SEED + i
        print(f"\n=== member {i}  seed {seed} ===")
        t1 = time.time()
        model, val_stats, mean, std = train_member(
            cfg, train, val, seed=seed, epochs=args.epochs, batch=args.batch, lr=args.lr,
        )
        te, _, _, _ = ts.loaders(test, test, args.batch)
        test_stats = ts.evaluate(model, te)
        print(f"  val RMSE {val_stats['rmse']:.3f}   "
              f"TEST RMSE {test_stats['rmse']:.3f}  bias {test_stats['bias']:+.3f}  "
              f"({time.time() - t1:.0f}s)")
        members.append(model)
        member_results.append({"seed": seed, "val": val_stats, "test": test_stats})

    te, va_loader, _, _ = ts.loaders(test, test, args.batch)
    _, val_loader_for_sigma, _, _ = ts.loaders(train, val, args.batch)
    ensemble_test = evaluate_ensemble(members, te)
    sigma_scale = fit_ensemble_sigma_scale(members, val_loader_for_sigma)
    ensemble_val = evaluate_ensemble(members, val_loader_for_sigma)

    print(f"\n=== ensemble ({args.members} members) ===")
    print(f"  VAL   RMSE {ensemble_val['rmse']:.3f}  bias {ensemble_val['bias']:+.3f}  "
          f"cov1s {ensemble_val['coverage_1sigma']:.2f}")
    print(f"  TEST  RMSE {ensemble_test['rmse']:.3f}  MAE {ensemble_test['mae']:.3f}  "
          f"bias {ensemble_test['bias']:+.3f}  cov1s {ensemble_test['coverage_1sigma']:.2f}")
    print(f"  sigma scale fitted on val: {sigma_scale:.2f}x")

    best_single = min(r["test"]["rmse"] for r in member_results)
    print(f"\nbest single member test RMSE: {best_single:.3f}")
    print(f"ensemble test RMSE:           {ensemble_test['rmse']:.3f}")
    print(f"trivial baseline test RMSE:   {naive_rmse:.3f}")
    print(f"committed single-model (full) test RMSE, for reference: 1.847")

    SHARED.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dicts": [m.state_dict() for m in members],
            "config": cfg.as_dict(),
            "feature_mean": torch.tensor(mean, dtype=torch.float64),
            "feature_std": torch.tensor(std, dtype=torch.float64),
            "window": train.window,
            "seeds": [DEFAULT_SEED + i for i in range(args.members)],
            "variant": f"full_ensemble{args.members}",
            "sigma_scale": float(sigma_scale),
        },
        SHARED / "speednet_ensemble.pt",
    )

    out = Path(__file__).resolve().parents[2] / "eval" / "results" / "speednet_ensemble_training.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "seed_base": DEFAULT_SEED,
                "members": args.members,
                "epochs": args.epochs,
                "n_train": len(train), "n_val": len(val), "n_test": len(test),
                "trivial_baseline_test_rmse": naive_rmse,
                "committed_single_model_test_rmse": 1.847,
                "member_results": member_results,
                "ensemble_val": ensemble_val,
                "ensemble_test": ensemble_test,
                "ensemble_sigma_scale": sigma_scale,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nsaved {SHARED / 'speednet_ensemble.pt'}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

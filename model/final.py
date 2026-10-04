"""Train the final per-drug models on all QC-passed data, save them with their confidence bars, and explain them.

Saves data/models/models.pkl = {"drugs": {drug: {"model", "features", "bars"}}, "background": [...], "linked": {...}}.
Demo samples (demo/demo_samples.csv) and their families are left out of training so the app demo is honest.
Writes data/processed/top_markers.csv (global weights per drug) for the biotech lead to sanity-check.

Explanation = exact, not approximate: logistic regression scores a genome as
    log-odds(resistant) = intercept + sum(weight[m] for each marker m present)
so each present marker's contribution is just its weight.
"""
import os
import pickle

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from baseline_rules import features, labels
from confidence import call, class_bars, lineage, make_model

ALPHAS = [0.02, 0.05]
MODEL_PATH = "data/models/models.pkl"


BACKGROUND_SHARE = 0.5  # markers in more than half of all genomes are background, not evidence


def build():
    demo = pd.read_csv("demo/demo_samples.csv", dtype=str).genome_id
    demo_families = set(lineage.loc[lineage.index.isin(demo)])
    X_all = features.loc[features.index.isin(lineage.index) & ~lineage.reindex(features.index).isin(demo_families)]
    saved = {}
    for drug in labels.columns:
        y = labels.loc[X_all.index, drug].dropna().astype(int)
        X, g = X_all.loc[y.index], lineage.loc[y.index]
        p_oof = np.zeros(len(y))  # cross-fitted, family-held-out predictions for setting the bars
        for fit, held in GroupKFold(5).split(X, y, g):
            p_oof[held] = make_model().fit(X.iloc[fit], y.iloc[fit]).predict_proba(X.iloc[held])[:, 1]
        saved[drug] = {"model": make_model().fit(X, y), "features": list(X.columns),
                       "bars": {a: class_bars(p_oof, y.values, a) for a in ALPHAS}}
    mapping = pd.read_csv("pipeline/drug_marker_map.csv", index_col=0).draft_drugs.fillna("")
    saved = {"drugs": saved,
             "background": sorted(X_all.columns[X_all.mean() > BACKGROUND_SHARE]),
             # known mechanism per drug (draft map for now; biotech lead's corrections will replace it)
             "linked": {d: sorted(m for m, ds in mapping.items() if d in ds.split("; ")) for d in labels.columns}}
    os.makedirs("data/models", exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(saved, f)
    return saved


def predict(saved, markers_present, alpha=0.02):
    """For one genome (a set of marker names): per drug -> call, probability, and the evidence behind it."""
    out = {}
    for drug, s in saved["drugs"].items():
        x = pd.DataFrame([[int(m in markers_present) for m in s["features"]]], columns=s["features"])
        p = s["model"].predict_proba(x)[0, 1]
        weights = pd.Series(s["model"].coef_[0], index=s["features"])
        shown = [m for m in s["features"] if m in markers_present and m not in saved["background"]]
        evidence = weights[shown].sort_values(key=abs, ascending=False)
        out[drug] = {"call": call(np.array([p]), s["bars"][alpha])[0], "p_resistant": p,
                     "evidence": evidence[evidence.abs() >= 0.5].round(2).to_dict(),  # skip near-zero weights
                     "unknown_markers": sorted(set(markers_present) - set(s["features"]))}
    return out


if __name__ == "__main__":
    saved = build()
    top = []
    for drug, s in saved["drugs"].items():
        w = pd.Series(s["model"].coef_[0], index=s["features"]).sort_values()
        for m, v in pd.concat([w.tail(8)[::-1], w.head(4)]).items():
            top.append({"drug": drug, "marker": m, "weight": round(v, 2),
                        "direction": "towards resistant" if v > 0 else "towards susceptible"})
    top = pd.DataFrame(top)
    top.to_csv("data/processed/top_markers.csv", index=False)
    for drug, t in top.groupby("drug", sort=False):
        print(f"\n{drug}:  " + ", ".join(f"{m} {w:+.1f}" for m, w in zip(t.marker, t.weight)))

    overview = pd.read_csv("data/processed/overview.csv", index_col=0, dtype={"genome_id": str}).fillna("")
    print("\nbackground markers (hidden from evidence):", saved["background"])
    for gid in ["562.100000", "562.100002"]:
        print(f"\n=== {gid} (lab: {overview.loc[gid].drop('markers').to_dict()})")
        for drug, r in predict(saved, set(overview.loc[gid, "markers"].split("; "))).items():
            print(f"  {drug:30} {r['call']:9} p={r['p_resistant']:.2f}  evidence={r['evidence']}")

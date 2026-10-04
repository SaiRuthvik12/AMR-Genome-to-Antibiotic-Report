"""Confidence + UNCERTAIN flag via class-conditional (Mondrian) split conformal prediction.

For each family-held-out fold:
  1. Cross-fit inside the training families (4 inner folds) so every training sample gets a prediction from a model that never saw its family.
  2. On the calibration samples, score how "surprised" the model is by the true answer: 1 - p(true class).
  3. Per class (R and S separately), take the (1 - alpha) quantile of those scores as the bar.
  4. For a test sample, a class is "plausible" if its surprise is under that class's bar.
     Exactly one plausible class -> confident call. Both (or neither) -> UNCERTAIN.
Guarantee (if test families resemble calibration families): among truly resistant samples, at most ~alpha
are confidently called susceptible. That is the very major error rate, so alpha is the knob for safety.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from baseline_rules import features, labels

lineage = pd.read_csv("data/processed/lineage.csv", index_col=0, dtype={"genome_id": str}).cluster
features, labels = features.loc[features.index.isin(lineage.index)], labels.loc[labels.index.isin(lineage.index)]
ALPHAS = [0.01, 0.02, 0.05, 0.10]  # above ~0.1 both answers can fail the bar (empty set), which is meaningless here


def make_model():
    return LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000)


def class_bars(p_resistant, y, alpha):
    """Per-class conformal threshold on the surprise score 1 - p(true class)."""
    bars = {}
    for cls in (0, 1):
        surprise = np.sort(1 - (p_resistant[y == cls] if cls else 1 - p_resistant[y == cls]))
        k = min(int(np.ceil((len(surprise) + 1) * (1 - alpha))), len(surprise))
        bars[cls] = surprise[k - 1]
    return bars


def call(p_resistant, bars):
    """'R', 'S' or 'UNCERTAIN' for each sample."""
    r_ok = (1 - p_resistant) <= bars[1]
    s_ok = p_resistant <= bars[0]
    return np.where(r_ok & ~s_ok, "R", np.where(s_ok & ~r_ok, "S", "UNCERTAIN"))


def evaluate(y, calls):
    r, s, sure = y == 1, y == 0, calls != "UNCERTAIN"
    return {"uncertain": (~sure).mean(),
            "very_major_error": ((calls == "S") & r).sum() / r.sum(),  # share of all resistant
            "major_error": ((calls == "R") & s).sum() / s.sum(),
            "accuracy_when_sure": (calls[sure] == np.where(y[sure] == 1, "R", "S")).mean()}


if __name__ == "__main__":
    rows = []
    for drug in labels.columns:
        y_all = labels[drug].dropna().astype(int)
        X_all, g_all = features.loc[y_all.index], lineage.loc[y_all.index]
        calls = {a: pd.Series("", index=y_all.index) for a in ALPHAS}
        for train, test in GroupKFold(5).split(X_all, y_all, g_all):
            X, y, g = X_all.iloc[train], y_all.iloc[train], g_all.iloc[train]
            # Cross-fitted calibration: every training sample gets a prediction from a model that never saw its family,
            # so the bars come from all training families instead of one lopsided held-out quarter.
            p_cal = np.zeros(len(y))
            for fit, held in GroupKFold(4).split(X, y, g):
                p_cal[held] = make_model().fit(X.iloc[fit], y.iloc[fit]).predict_proba(X.iloc[held])[:, 1]
            p_test = make_model().fit(X, y).predict_proba(X_all.iloc[test])[:, 1]
            for a in ALPHAS:
                calls[a].iloc[test] = call(p_test, class_bars(p_cal, y.values, a))
        for a in ALPHAS:
            rows.append({"drug": drug, "alpha": a, **evaluate(y_all.values, calls[a].values)})

    out = pd.DataFrame(rows).set_index(["drug", "alpha"])
    out.to_csv("data/processed/results_conformal_v1.csv")
    print(out.to_string(formatters={c: "{:.1%}".format for c in out.columns}))

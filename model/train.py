"""First ML models vs the rule baseline, scored with family-held-out cross-validation.

5 folds: each fold holds out ~1/5 of the families (lineage clusters) as the test set, so the model is
always tested on bacteria from families it never saw. A random split is also reported to show how much
it inflates scores. Threshold is a plain 0.5 for now (calibration comes later).
"""
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, KFold

from baseline_rules import features, labels, mapping, metrics

lineage = pd.read_csv("data/processed/lineage.csv", index_col=0).cluster  # QC-passed genomes only
features, labels = features.loc[features.index.isin(lineage.index)], labels.loc[labels.index.isin(lineage.index)]

MODELS = {
    "logistic regression": lambda: LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000),
    "LightGBM": lambda: LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=15,
                                       class_weight="balanced", verbose=-1),
}


def cross_val_predict(make_model, X, y, splitter, groups=None):
    pred = pd.Series(0, index=y.index)
    for train, test in splitter.split(X, y, groups):
        model = make_model().fit(X.iloc[train], y.iloc[train])
        pred.iloc[test] = (model.predict_proba(X.iloc[test])[:, 1] >= 0.5).astype(int)
    return pred


rows = []
for drug in labels.columns:
    y = labels[drug].dropna().astype(int)
    X = features.loc[y.index]
    rule_markers = [m for m, d in mapping.items() if drug in d.split("; ")]
    rows.append({"drug": drug, "method": "rules (draft map)",
                 **metrics(y, (X[rule_markers].sum(axis=1) > 0).astype(int))})
    for name, make in MODELS.items():
        pred = cross_val_predict(make, X, y, GroupKFold(5), groups=lineage.loc[y.index])
        rows.append({"drug": drug, "method": name, **metrics(y, pred)})
    pred = cross_val_predict(MODELS["LightGBM"], X, y, KFold(5, shuffle=True, random_state=0))
    rows.append({"drug": drug, "method": "LightGBM, random split (inflated)", **metrics(y, pred)})

out = pd.DataFrame(rows).set_index(["drug", "method"])
out.to_csv("data/processed/results_v1.csv")
print(out.to_string(formatters={c: "{:.1%}".format for c in ["very_major_error", "major_error", "balanced_acc"]}))

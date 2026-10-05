"""Rule baseline = what existing tools do: predict RESISTANT if the genome carries any marker linked to that drug.

Uses pipeline/drug_marker_map.csv: the biotech lead's review ("yes" keeps draft_drugs, "no" = no drug,
"no + X; Y" = drugs X and Y) overrides the auto-guessed draft_drugs; unreviewed rows keep the draft.
Usage: .venv/bin/python model/baseline_rules.py [marker_to_ignore ...]
"""
import os
import sys

import pandas as pd

features = pd.read_csv("data/processed/features.csv", index_col=0, dtype={"genome_id": str})
labels = pd.read_csv("data/processed/labels.csv", index_col=0, dtype={"genome_id": str})
if os.path.exists("data/processed/qc.csv"):
    qc = pd.read_csv("data/processed/qc.csv", index_col=0, dtype={"genome_id": str})
    keep = qc.index[qc.qc_pass]
    features, labels = features.loc[features.index.isin(keep)], labels.loc[labels.index.isin(keep)]
def reviewed_drugs(row):
    verdict = str(row["friend_correct?"]).strip() if pd.notna(row["friend_correct?"]) else ""
    if verdict.lower().startswith("no"):
        return verdict.partition("+")[2].strip()  # "no" -> "", "no + ampicillin" -> "ampicillin"
    return row.draft_drugs if pd.notna(row.draft_drugs) else ""  # "yes" or not reviewed


mapping = pd.read_csv("pipeline/drug_marker_map.csv", index_col=0).apply(reviewed_drugs, axis=1)
ignore = set(sys.argv[1:])


def metrics(truth, pred):
    """VME = resistant called susceptible (dangerous). ME = susceptible called resistant."""
    r, s = truth == 1, truth == 0
    vme, me = (pred[r] == 0).mean(), (pred[s] == 1).mean()
    return {"n": len(truth), "very_major_error": vme, "major_error": me, "balanced_acc": 1 - (vme + me) / 2}


if __name__ == "__main__":
    rows = {}
    for drug in labels.columns:
        markers = [m for m, d in mapping.items() if drug in d.split("; ") and m not in ignore]
        y = labels[drug].dropna()
        pred = (features.loc[y.index, markers].sum(axis=1) > 0).astype(int)
        rows[drug] = metrics(y, pred) | {"n_markers": len(markers)}
    out = pd.DataFrame(rows).T
    print(out.to_string(formatters={c: "{:.1%}".format for c in ["very_major_error", "major_error", "balanced_acc"]}))

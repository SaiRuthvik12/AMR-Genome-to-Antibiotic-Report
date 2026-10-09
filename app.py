"""AMR Lens: upload an E. coli genome (or pick an example) and get a per-antibiotic resistance report.

Run:  .venv/bin/streamlit run app.py
Research prototype for decision support. Not for clinical use.
"""
import gzip
import hashlib
import io
import os
import re
from html import escape

import pandas as pd
import streamlit as st

from report import DRUG_INFO, build_report, llm_summary, load_models, tools_available

if os.path.exists(".env"):  # optional: ANTHROPIC_API_KEY=... for the AI summary
    for line in open(".env"):
        key, _, value = line.strip().partition("=")
        if key and not key.startswith("#") and value:
            os.environ.setdefault(key.strip(), value.strip().strip('"'))

st.set_page_config(page_title="AMR Lens", page_icon=":material/biotech:", layout="wide")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&display=swap');
.stApp { font-family: 'Inter', sans-serif; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"], footer { display: none; }
.block-container { padding-top: 2.2rem; max-width: 1180px; }
section[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #E6E3DA; }
.eyebrow { text-transform: uppercase; letter-spacing: .12em; font-size: .72rem; color: #0F6E56; font-weight: 600; }
.hero-title { font-family: 'Source Serif 4', serif; font-size: 2.7rem; font-weight: 600; letter-spacing: -.02em;
  color: #14211D; margin: .2rem 0 0 0; line-height: 1.1; }
.hero-sub { color: #5B6360; font-size: 1.05rem; margin: .5rem 0 1.6rem 0; max-width: 640px; line-height: 1.55; }
.brand { font-family: 'Source Serif 4', serif; font-size: 1.5rem; font-weight: 600; color: #14211D; }
.brand-sub { color: #6B726F; font-size: .85rem; margin-bottom: .6rem; }
.card { background: #FFFFFF; border: 1px solid #E6E3DA; border-radius: 16px; padding: 20px 22px;
  box-shadow: 0 1px 2px rgba(20,33,29,.04); margin-bottom: 16px; }
.card h4 { margin: 0 0 .2rem 0; font-size: 1.05rem; font-weight: 600; color: #14211D; }
.muted { color: #6B726F; font-size: .88rem; }
.sample-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
.sample-name { font-family: 'Source Serif 4', serif; font-size: 1.45rem; font-weight: 600; color: #14211D; }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-top: 16px; }
.metric { background: #F7F6F2; border-radius: 12px; padding: 12px 14px; }
.metric .label { font-size: .7rem; color: #6B726F; text-transform: uppercase; letter-spacing: .07em; }
.metric .value { font-size: 1.25rem; font-weight: 600; color: #14211D; margin-top: 2px; }
.pill { display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: .78rem; font-weight: 600; white-space: nowrap; }
.pill-r { background: #FCEBEB; color: #A32D2D; } .pill-s { background: #E1F5EE; color: #085041; }
.pill-u { background: #FAEEDA; color: #854F0B; } .pill-ok { background: #E1F5EE; color: #085041; }
.pill-bad { background: #FCEBEB; color: #A32D2D; }
.summary { font-size: 1rem; line-height: 1.65; color: #1F2328; margin-top: .5rem; }
.counts { display: flex; gap: 10px; flex-wrap: wrap; margin: 4px 0 16px 0; }
.count { background: #FFFFFF; border: 1px solid #E6E3DA; border-radius: 999px; padding: 6px 14px; font-size: .85rem; color: #1F2328; }
.count b { font-weight: 600; margin-right: 4px; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; vertical-align: middle; }
.drug-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 16px; }
.drug-card { background: #FFFFFF; border: 1px solid #E6E3DA; border-radius: 16px; padding: 18px 20px;
  display: flex; flex-direction: column; gap: 12px; box-shadow: 0 1px 2px rgba(20,33,29,.04); }
.drug-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.drug-name { font-size: 1.08rem; font-weight: 600; color: #14211D; }
.drug-class { font-size: .8rem; color: #6B726F; margin-top: 2px; }
.meter { height: 8px; background: #EFEDE6; border-radius: 999px; overflow: hidden; }
.meter > div { height: 100%; border-radius: 999px; }
.fill-r { background: #E24B4A; } .fill-s { background: #1D9E75; } .fill-u { background: #EF9F27; }
.meter-label { font-size: .8rem; color: #5B6360; margin-top: 6px; }
.section-label { font-size: .7rem; color: #6B726F; text-transform: uppercase; letter-spacing: .07em; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px; border-radius: 8px; font-size: .78rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.chip-known { background: #EEF5F2; color: #0F3D33; border: 1px solid #CFE5DC; }
.chip-other { background: transparent; color: #5B6360; border: 1px dashed #D3D1C7; }
.chip .w { color: #8A918E; font-size: .7rem; }
.note { font-size: .82rem; color: #854F0B; background: #FDF6EA; border-radius: 10px; padding: 8px 12px; }
.lab { font-size: .8rem; color: #6B726F; border-top: 1px solid #F0EEE8; padding-top: 10px; margin-top: auto; }
.match { color: #0F6E56; font-weight: 600; } .differ { color: #A32D2D; font-weight: 600; }
.legend { font-size: .8rem; color: #6B726F; margin-top: 12px; }
.steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
.step-num { width: 28px; height: 28px; border-radius: 50%; background: #E1F5EE; color: #085041; font-weight: 600;
  display: flex; align-items: center; justify-content: center; font-size: .85rem; margin-bottom: 10px; }
table.perf { width: 100%; border-collapse: collapse; font-size: .9rem; border: none; }
table.perf th, table.perf td { border-left: none !important; border-right: none !important; border-top: none !important; }
table.perf th { text-align: left; font-size: .72rem; color: #6B726F; text-transform: uppercase; letter-spacing: .06em;
  font-weight: 600; padding: 8px 10px; border-bottom: 1px solid #E6E3DA; }
table.perf td { padding: 10px; border-bottom: 1px solid #F0EEE8; color: #1F2328; }
.disclaimer { font-size: .75rem; color: #8A918E; line-height: 1.5; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

PILL = {"R": ("Resistant", "r"), "S": ("Susceptible", "s"), "UNCERTAIN": ("Uncertain", "u")}
DEMO = pd.read_csv("demo/demo_samples.csv", dtype=str)
DEMO = DEMO[DEMO.show_in_app != "no"]  # held-out genomes kept for the live upload demo
LABELS = pd.read_csv("data/processed/labels.csv", dtype={"genome_id": str}).set_index("genome_id")


@st.cache_resource
def models():
    return load_models()


@st.cache_data(show_spinner=False)
def cached_report(path, alpha, cached_amrfinder):
    return build_report(path, alpha, cached_amrfinder, models())


@st.cache_data(show_spinner=False)
def cached_summary(path, alpha, cached_amrfinder):
    return llm_summary(cached_report(path, alpha, cached_amrfinder))


def bvbrc_id(data):
    """BV-BRC FASTA headers end with '| <genome_id>]'; used only to show known lab results next to the prediction."""
    stream = gzip.GzipFile(fileobj=io.BytesIO(data)) if data[:2] == b"\x1f\x8b" else io.BytesIO(data)
    head = stream.readline(2000).decode(errors="ignore")
    found = re.search(r"\|\s*(\d+\.\d+)\]", head)
    return found.group(1) if found else None


def save_upload(upload):
    data = upload.getvalue()
    os.makedirs("data/uploads", exist_ok=True)
    suffix = ".fna.gz" if upload.name.endswith(".gz") else ".fna"
    path = f"data/uploads/{hashlib.sha256(data).hexdigest()[:16]}{suffix}"
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
    return path


# ---------- Sidebar: choose a sample ----------
with st.sidebar:
    st.markdown('<div class="brand">AMR Lens</div><div class="brand-sub">Genome-based resistance report</div>',
                unsafe_allow_html=True)
    can_upload = tools_available()
    source = st.radio("Sample", ["Example isolates", "Upload a genome"] if can_upload else ["Example isolates"],
                      label_visibility="collapsed")
    if not can_upload:
        st.caption("This online version runs the example isolates. Scanning an uploaded genome needs the "
                   "bioinformatics tools, which run in our local version.")
    path = cached_amr = None
    lab = {}
    if source == "Example isolates":
        linked = st.query_params.get("example")  # keep the sidebar in step with a ?example= link
        start = DEMO.genome_id.tolist().index(linked) if linked in DEMO.genome_id.tolist() else 0
        pick = st.selectbox("Example isolate", DEMO.title, index=start)
        row = DEMO[DEMO.title == pick].iloc[0]
        st.caption(f"{row.description}. Not used to train the model.")
        path, cached_amr = f"demo/{row.genome_id}.fna.gz", f"demo/{row.genome_id}.amrfinder.tsv"
        sample_name, sample_id = row.title, row.genome_id
        lab = LABELS.loc[row.genome_id].dropna().to_dict() if row.genome_id in LABELS.index else {}
    else:
        upload = st.file_uploader("Assembled E. coli genome", type=["fna", "fa", "fasta", "gz"],
                                  help="FASTA file of an assembled genome (contigs), optionally gzipped.")
        if upload:
            path = save_upload(upload)
            sample_name, sample_id = upload.name, os.path.basename(path)
            gid = bvbrc_id(upload.getvalue())
            if gid in LABELS.index:  # a public genome with known lab results: show them for comparison
                sample_id, lab = f"BV-BRC {gid}", LABELS.loc[gid].dropna().to_dict()
    level = st.segmented_control("Confidence level", ["Strict", "Balanced"], default="Strict",
                                 help="Strict: aims for about 2% errors, more answers flagged uncertain. "
                                      "Balanced: aims for about 5% errors, fewer uncertain answers.")
    alpha = 0.05 if level == "Balanced" else 0.02
    run = st.button("Analyze genome", type="primary", use_container_width=True, disabled=path is None)
    st.markdown('<p class="disclaimer">Research prototype for decision support. Predictions do not replace '
                'laboratory susceptibility testing. No treatment advice is given.</p>', unsafe_allow_html=True)

if run:
    st.session_state.active = {"path": path, "cached": cached_amr, "alpha": alpha, "name": sample_name,
                               "id": sample_id, "lab": lab}
elif "active" not in st.session_state and st.query_params.get("example") in set(DEMO.genome_id):
    # a link like ?example=562.28131 opens that example's report directly
    ex = DEMO[DEMO.genome_id == st.query_params["example"]].iloc[0]
    st.session_state.active = {"path": f"demo/{ex.genome_id}.fna.gz", "cached": f"demo/{ex.genome_id}.amrfinder.tsv",
                               "alpha": 0.02, "name": ex.title, "id": ex.genome_id,
                               "lab": LABELS.loc[ex.genome_id].dropna().to_dict()}

# ---------- Header ----------
st.markdown('<div class="eyebrow">Antimicrobial resistance · E. coli</div>'
            '<div class="hero-title">Which antibiotics will still work?</div>'
            '<div class="hero-sub">Reads a bacterial genome, predicts resistance to five common antibiotics, '
            'shows the genetic evidence, and says plainly when it is not sure.</div>', unsafe_allow_html=True)

tab_report, tab_perf, tab_about = st.tabs(["Report", "How well it works", "How it works"])


def drug_card(drug, r, lab_value):
    name, drug_class = DRUG_INFO[drug]
    label, kind = PILL[r["call"]]
    p = r["p_resistant"]
    pct = lambda x: ">99%" if x > 0.99 else f"{x:.0%}"  # never claim certainty
    if r["call"] == "R":
        meter_text = f"{pct(p)} probability resistant"
    elif r["call"] == "S":
        meter_text = f"{pct(1 - p)} probability susceptible"
    else:
        lean = "resistant" if p >= 0.5 else "susceptible"
        meter_text = f"Leans {lean} ({max(p, 1 - p):.0%}), below the confidence bar"
    chips = "".join(
        f'<span class="chip {"chip-known" if e["known_mechanism"] and e["weight"] > 0 else "chip-other"}" '
        f'title="{escape(e["name"])}">{escape(e["marker"])}<span class="w">{e["weight"]:+.1f}</span></span>'
        for e in r["evidence"][:6])
    if not chips:
        chips = '<span class="muted">No resistance markers linked to this drug.</span>'
    note = ('<div class="note">Not confident enough to call. Confirm with laboratory susceptibility testing.</div>'
            if r["call"] == "UNCERTAIN" else "")
    lab_html = ""
    if lab_value is not None:
        lab_word = "Resistant" if lab_value == 1 else "Susceptible"
        if r["call"] == "UNCERTAIN":
            verdict = '<span class="muted">· flagged for lab check</span>'
        elif (r["call"] == "R") == (lab_value == 1):
            verdict = '<span class="match">· matches</span>'
        else:
            verdict = '<span class="differ">· differs</span>'
        lab_html = f'<div class="lab">Lab result: {lab_word} {verdict}</div>'
    return (f'<div class="drug-card"><div class="drug-top"><div><div class="drug-name">{name}</div>'
            f'<div class="drug-class">{drug_class}</div></div><span class="pill pill-{kind}">{label}</span></div>'
            f'<div><div class="meter"><div class="fill-{kind}" style="width:{max(p * 100, 2):.0f}%"></div></div>'
            f'<div class="meter-label">{meter_text}</div></div>'
            f'<div><div class="section-label">Genetic evidence</div><div class="chips">{chips}</div></div>'
            f'{note}{lab_html}</div>')


# ---------- Report tab ----------
with tab_report:
    active = st.session_state.get("active")
    if not active:
        st.markdown(
            '<div class="steps">'
            '<div class="card"><div class="step-num">1</div><h4>Choose a genome</h4><div class="muted">Pick an example '
            'isolate or upload an assembled <i>E. coli</i> genome in the sidebar.</div></div>'
            '<div class="card"><div class="step-num">2</div><h4>Scan for resistance</h4><div class="muted">Quality and '
            'species checks, then a search for known resistance genes and mutations.</div></div>'
            '<div class="card"><div class="step-num">3</div><h4>Read the report</h4><div class="muted">A call per '
            'antibiotic with its evidence, and an honest "uncertain" when the model is not sure.</div></div>'
            '</div>', unsafe_allow_html=True)
    else:
        with st.spinner("Scanning the genome for resistance markers. Uploaded genomes take about a minute."):
            try:
                rep = cached_report(active["path"], active["alpha"], active["cached"])
            except Exception as e:
                st.error(f"Could not analyze this file. Is it an assembled genome in FASTA format? ({e})")
                st.stop()
        qc = rep["qc"]
        qc_pill = ('<span class="pill pill-ok">Quality check passed</span>' if not qc["qc_reason"]
                   else f'<span class="pill pill-bad">Quality check failed: {escape(qc["qc_reason"])}</span>')
        st.markdown(
            f'<div class="card"><div class="sample-head"><div><div class="eyebrow">Sample</div>'
            f'<div class="sample-name">{escape(active["name"])}</div><div class="muted">{escape(active["id"])}</div></div>'
            f'{qc_pill}</div><div class="metrics">'
            f'<div class="metric"><div class="label">Genome size</div><div class="value">{qc["size_mb"]:.2f} Mb</div></div>'
            f'<div class="metric"><div class="label">Pieces (contigs)</div><div class="value">{int(qc["contigs"])}</div></div>'
            f'<div class="metric"><div class="label">Similarity to E. coli</div><div class="value">{(1 - qc["dist_to_ecoli"]) * 100:.1f}%</div></div>'
            f'<div class="metric"><div class="label">Resistance markers</div><div class="value">{len(rep["markers"])}</div></div>'
            f'</div></div>', unsafe_allow_html=True)

        if qc["qc_reason"]:
            st.warning("This genome did not pass the quality check, so no predictions are made. "
                       "Expected: 4.5–6.0 Mb, at most 500 contigs, and at least 95% similarity to E. coli.")
            st.stop()

        drugs = rep["drugs"]
        with st.spinner("Writing the summary"):
            summary, why_not = cached_summary(active["path"], active["alpha"], active["cached"])
        if summary or "ANTHROPIC_API_KEY" not in (why_not or ""):  # no key configured: hide the box instead of a setup hint
            body = (f'<div class="summary">{escape(summary)}</div>' if summary else f'<div class="muted">{escape(why_not)}</div>')
            st.markdown(f'<div class="card"><div class="eyebrow">Summary · written by Claude from the evidence below</div>'
                        f'{body}</div>', unsafe_allow_html=True)

        n = {k: sum(r["call"] == k for r in drugs.values()) for k in PILL}
        st.markdown(
            '<div class="counts">'
            f'<span class="count"><span class="dot" style="background:#E24B4A"></span><b>{n["R"]}</b>resistant</span>'
            f'<span class="count"><span class="dot" style="background:#1D9E75"></span><b>{n["S"]}</b>susceptible</span>'
            f'<span class="count"><span class="dot" style="background:#EF9F27"></span><b>{n["UNCERTAIN"]}</b>uncertain</span>'
            f'<span class="count">Confidence level: <b>{"Strict" if active["alpha"] == 0.02 else "Balanced"}</b></span>'
            '</div>', unsafe_allow_html=True)

        cards = "".join(drug_card(d, r, active["lab"].get(d)) for d, r in drugs.items())
        st.markdown(f'<div class="drug-grid">{cards}</div>'
                    '<div class="legend"><span class="chip chip-known">solid</span> known resistance mechanism for that '
                    'drug &nbsp; <span class="chip chip-other">dashed</span> often found together with resistance, '
                    'not a cause &nbsp;·&nbsp; numbers are the model\'s weight for each marker</div>',
                    unsafe_allow_html=True)

        with st.expander(f"All {len(rep['markers'])} resistance markers found in this genome"):
            st.dataframe(rep["markers"].rename(columns={"Element symbol": "Marker", "Element name": "Description"}),
                         hide_index=True, use_container_width=True)

# ---------- Performance tab ----------
with tab_perf:
    conf = pd.read_csv("data/processed/results_conformal_v1.csv")
    v1 = pd.read_csv("data/processed/results_v1.csv").set_index(["drug", "method"])
    a = st.session_state.get("active", {}).get("alpha", 0.02)
    rows = ""
    for _, r in conf[conf.alpha == a].iterrows():
        rows += (f'<tr><td><b>{DRUG_INFO[r.drug][0]}</b></td>'
                 f'<td>{v1.loc[(r.drug, "rules (expert map)"), "balanced_acc"]:.0%}</td>'
                 f'<td>{v1.loc[(r.drug, "logistic regression"), "balanced_acc"]:.0%}</td>'
                 f'<td>{r.uncertain:.0%}</td><td>{r.accuracy_when_sure:.1%}</td>'
                 f'<td>{r.very_major_error:.1%}</td><td>{r.major_error:.1%}</td></tr>')
    st.markdown(
        f'<div class="card"><h4>Tested on bacterial families the model never saw</h4><div class="muted" '
        f'style="margin-bottom:14px">5-fold cross-validation where whole families of near-identical bacteria are held '
        f'out together, so scores reflect new patients rather than memorised strains. Confidence level: '
        f'{"Strict" if a == 0.02 else "Balanced"}.</div><table class="perf"><tr><th>Antibiotic</th>'
        f'<th>Balanced accuracy, simple rules</th><th>Balanced accuracy, model</th><th>Flagged uncertain</th>'
        f'<th>Accuracy when sure</th><th>Dangerous errors</th><th>Wasteful errors</th></tr>{rows}</table>'
        f'<div class="legend">Dangerous error: predicted the drug works when it does not (share of resistant samples). '
        f'Wasteful error: predicted resistance when the drug works. Simple rules: "resistant if any gene linked to the '
        f'drug is present", using a gene list reviewed by our biotech lead.</div></div>', unsafe_allow_html=True)

# ---------- About tab ----------
with tab_about:
    st.markdown(
        '<div class="steps">'
        '<div class="card"><div class="step-num">1</div><h4>Check the genome</h4><div class="muted">Size, '
        'fragmentation and species are checked first. Broken or mislabelled files get no prediction.</div></div>'
        '<div class="card"><div class="step-num">2</div><h4>Find resistance markers</h4><div class="muted">NCBI '
        'AMRFinderPlus lists known resistance genes and mutations in the DNA.</div></div>'
        '<div class="card"><div class="step-num">3</div><h4>Predict per antibiotic</h4><div class="muted">A model '
        'trained on about 6,000 lab-tested isolates weighs the markers. Every call shows its evidence.</div></div>'
        '<div class="card"><div class="step-num">4</div><h4>Say when unsure</h4><div class="muted">Conformal '
        'prediction sets a confidence bar per answer. Below it, the call is "uncertain" and needs a lab test.'
        '</div></div></div>'
        '<div class="card"><h4>Limitations</h4><div class="muted" style="line-height:1.7">'
        '· Resistance from mechanisms not in the gene database is invisible to the model, and is not flagged as uncertain.<br>'
        '· Trained on public <i>E. coli</i> data from BV-BRC; other species are not supported.<br>'
        '· Still needs a cultured isolate to sequence; it shortens the testing step, not the growing step.<br>'
        '· Research prototype: not validated prospectively and not approved for clinical use.</div></div>',
        unsafe_allow_html=True)

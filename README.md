# AMR Lens

Reads an *E. coli* genome and predicts resistance to five common antibiotics, with the genetic evidence for each
call and an honest **UNCERTAIN** when the model is not confident. Research prototype for decision support; not for
clinical use.

- What we did and why, in plain language: [`docs/PROJECT_LOG.md`](docs/PROJECT_LOG.md)
- Plan, roles and glossary: [project doc](https://claude.ai/code/artifact/7dbc4cdf-5882-4763-9f38-e686a4678c90)

## Run the app

```bash
.venv/bin/streamlit run app.py
```

Then open http://localhost:8501. Pick an example isolate (no setup needed) or upload an assembled genome (FASTA, optionally
`.gz`; about a minute to scan). Uploading needs the bioinformatics tools (see `CLAUDE.md` → Environments).

Optional AI summary: put `ANTHROPIC_API_KEY=...` in a `.env` file in this folder (it is gitignored).

## Re-run the analysis after data changes

```bash
./run_all.sh
```

Then `git diff data/processed/` shows how the numbers changed.

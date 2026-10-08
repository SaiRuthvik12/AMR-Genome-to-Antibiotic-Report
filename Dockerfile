# AMR Lens for Hugging Face Spaces (Docker). Bioinformatics tools come from bioconda (native Linux, no Rosetta).
FROM condaforge/miniforge3:latest

RUN mamba install -y -c conda-forge -c bioconda python=3.11 ncbi-amrfinderplus mash seqkit \
    && mamba clean -afy \
    && amrfinder -u

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Spaces run the container as user 1000; uploads are written to data/uploads
RUN useradd -m -u 1000 user && mkdir -p data/uploads && chown -R user /app
USER user

ENV AMR_BIN=/opt/conda/bin
EXPOSE 7860
# XSRF/CORS off: Spaces serve the app inside an iframe, where Streamlit's upload protection blocks file uploads
CMD ["streamlit", "run", "app.py", "--server.port", "7860", "--server.address", "0.0.0.0", "--server.headless", "true", \
     "--server.enableXsrfProtection", "false", "--server.enableCORS", "false"]

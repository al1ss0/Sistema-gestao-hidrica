FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    HIDRO_ATUALIZAR=0 \
    PORT=8000

# libgomp: biblioteca OpenMP que o XGBoost precisa em tempo de execução.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Em produção usa-se o xgboost-cpu (mesmo módulo `xgboost`, sem as bibliotecas de GPU, bem menor).
COPY requirements.txt .
RUN sed 's/^xgboost==/xgboost-cpu==/' requirements.txt > /tmp/requirements-prod.txt \
    && pip install -r /tmp/requirements-prod.txt

COPY . .
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/saude' % os.environ['PORT'], timeout=4)"

# Um processo com várias threads: o modelo e o cache de clima ficam em um só lugar na memória.
CMD ["sh", "-c", "exec gunicorn wsgi:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120 --access-logfile -"]

# syntax=docker/dockerfile:1
FROM python:3.12-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 XDG_CACHE_HOME=/tmp/etcs-cache
RUN apt-get update && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core postgresql-client ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock.txt ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.lock.txt
RUN useradd --uid 10001 --create-home etcs && mkdir -p /data/private_media && chown -R etcs:etcs /data
COPY --chown=etcs:etcs . .
RUN ETCS_DEBUG=1 python manage.py collectstatic --noinput && chown -R etcs:etcs /app/staticfiles
USER etcs
ENV ETCS_PRIVATE_MEDIA=/data/private_media
EXPOSE 8000
CMD ["gunicorn","config.wsgi:application","--bind","0.0.0.0:8000","--workers","2","--timeout","90","--access-logfile","-"]

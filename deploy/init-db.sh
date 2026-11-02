#!/bin/sh
set -eu
# Values are generated locally by prepare_deploy.py; no credentials are baked into the image.
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=web_password="$ETCS_WEB_DB_PASSWORD" <<'SQL'
CREATE USER etcs_web PASSWORD :'web_password';
SQL

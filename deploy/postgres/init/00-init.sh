#!/bin/sh
# Создание ролей и схем сервисов при первом запуске контейнера PostgreSQL.
#
# Официальный образ выполняет файлы из /docker-entrypoint-initdb.d один раз, на пустом томе. Сам SQL лежит в
# подкаталоге sql/: файл *.sql в корне каталога образ выполнил бы без переменных psql, и пароли не подставились бы.
set -eu

: "${AUTH_DB_PASSWORD:?не задан AUTH_DB_PASSWORD}"
: "${MEETING_DB_PASSWORD:?не задан MEETING_DB_PASSWORD}"
: "${ANALYTICS_DB_PASSWORD:?не задан ANALYTICS_DB_PASSWORD}"

psql --set ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set auth_password="$AUTH_DB_PASSWORD" \
    --set meeting_password="$MEETING_DB_PASSWORD" \
    --set analytics_password="$ANALYTICS_DB_PASSWORD" \
    --file /docker-entrypoint-initdb.d/sql/roles-and-schemas.sql

-- Роли и схемы сервисов (docs/backend/database.md, ADR-004).
-- Выполняется один раз суперпользователем при создании тома – скриптом ../00-init.sh.
-- Пароли подставляются переменными psql: -v auth_password=... -v meeting_password=... -v analytics_password=...

CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO PUBLIC;   -- только для доступа к типам и функциям расширений

CREATE ROLE auth_svc      LOGIN PASSWORD :'auth_password';
CREATE ROLE meeting_svc   LOGIN PASSWORD :'meeting_password';
CREATE ROLE analytics_svc LOGIN PASSWORD :'analytics_password';

CREATE SCHEMA auth      AUTHORIZATION auth_svc;
CREATE SCHEMA meeting   AUTHORIZATION meeting_svc;
CREATE SCHEMA analytics AUTHORIZATION analytics_svc;

ALTER ROLE auth_svc      SET search_path = auth, public;
ALTER ROLE meeting_svc   SET search_path = meeting, public;
ALTER ROLE analytics_svc SET search_path = analytics, public;

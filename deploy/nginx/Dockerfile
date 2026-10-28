# Nginx со статикой SPA (EMO-71). Контекст – корень репозитория: нужен frontend/.
#   docker build -f deploy/nginx/Dockerfile -t vks/nginx .
FROM node:22-alpine AS frontend
WORKDIR /frontend
# Версия pnpm – из packageManager в package.json.
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend ./
RUN pnpm build

FROM nginx:1.27-alpine
COPY deploy/nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend /frontend/dist /usr/share/nginx/html

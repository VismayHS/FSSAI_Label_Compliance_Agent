# Web client (A8): built with Vite, served by unprivileged nginx, which also proxies the API so the
# browser talks to one origin. Build context: apps/web (infra/compose/web.yml). Multi-arch images.
FROM node:22-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 8080

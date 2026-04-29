FROM node:18-bullseye-slim AS builder

WORKDIR /build/frontend

COPY src/frontend/package*.json ./
RUN npm ci

COPY src/frontend/ ./

ARG VITE_API_BASE_URL=
ARG VITE_ENABLE_DEBUG=false
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_ENABLE_DEBUG=${VITE_ENABLE_DEBUG}

RUN npm run build


FROM nginx:1.25-alpine

COPY docker/intranet/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/frontend/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]

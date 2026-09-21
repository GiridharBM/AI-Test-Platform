# AI Test Platform frontend image (M16-B): multi-stage build.
# Build with the committed package-lock.json via `npm ci` (deterministic),
# then the project's own `npm run build` (tsc -b && vite build).

# --- Build stage: pinned Node 22 LTS Alpine ---------------------------------
FROM node:22.20.0-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# --- Runtime stage: pinned nginx stable-alpine -------------------------------
FROM nginx:1.28.0-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
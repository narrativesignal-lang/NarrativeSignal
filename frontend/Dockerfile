FROM node:20-alpine

WORKDIR /app

# Node 20 ships with Corepack; pin pnpm for reproducible installs (no npm i -g).
RUN corepack enable && corepack prepare pnpm@9.15.5 --activate

# Dependency layer: invalidate only when manifests change.
COPY package.json pnpm-lock.yaml ./

# --frozen-lockfile: fail fast in CI/build when lockfile is out of sync with package.json.
RUN pnpm install --frozen-lockfile

COPY . /app

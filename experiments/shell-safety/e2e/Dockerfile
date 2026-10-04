FROM node:24.14.0-bookworm-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY pilot.mjs cases.json ./
USER node
WORKDIR /tmp
ENTRYPOINT ["node","/app/pilot.mjs"]

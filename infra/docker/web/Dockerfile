FROM node:24-alpine

WORKDIR /app

# Lockfile primero: `npm ci` es reproducible y no necesita secretos.
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

# Resto de la aplicación; se excluyen node_modules/.next del host (no sirven en Linux).
COPY apps/web/src ./src
COPY apps/web/tests ./tests
COPY apps/web/*.mjs apps/web/*.ts apps/web/*.json ./

RUN npm run build

CMD ["npm", "start"]

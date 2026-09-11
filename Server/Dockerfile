# FlowShield license server.
#
# Node 24 because node:sqlite is stable there (on 22 it needs
# --experimental-sqlite), and this image deliberately does not build
# better-sqlite3's native binding: that install script runs `node-gyp rebuild`,
# which needs python3/make/g++ that the slim image lacks — the build would fail
# outright. --ignore-scripts skips it, and db.js falls back to Node's built-in
# SQLite. Run locally with FLOWSHIELD_DB_DRIVER=node-sqlite to exercise the
# same driver this image uses.
FROM node:24-slim

ENV NODE_ENV=production
WORKDIR /app

# Copy manifests first so `npm ci` is cached across code-only changes.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force

COPY . .

# The database lives here. Mount a persistent volume at /data to keep it
# across deploys; without one the server recovers licences from Stripe on
# demand, so an ephemeral disk costs a round-trip, not a customer.
ENV FLOWSHIELD_DB=/data/licenses.db
RUN mkdir -p /data && chown -R node:node /data /app

USER node
EXPOSE 3000

# Hosts that honour HEALTHCHECK get a real readiness signal rather than
# "the port is open".
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "require('http').get('http://127.0.0.1:'+(process.env.PORT||3000)+'/health',r=>process.exit(r.statusCode<500?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "server.js"]

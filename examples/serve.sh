#!/bin/sh
# Build docs and serve with periodic rebuild.
# Checks for file changes every 10 seconds using find -newer against a marker.
# Falls back to forced rebuild every 60 seconds if change detection is unreliable
# (Docker Desktop Windows bind mounts don't always propagate timestamps).

SITE_DIR="/tmp/docs-site"
MARKER="/tmp/.docs-last-build"
POLL_INTERVAL=10
FORCE_INTERVAL=60
FORCE_COUNTER=0

build() {
    echo "[docs] Building..."
    mkdocs build -d "$SITE_DIR" 2>&1 | grep -v '^WARNING' | grep -v '^  -' | grep -v '^$'
    touch "$MARKER"
    echo "[docs] Build complete at $(date '+%H:%M:%S')"
}

has_changes() {
    # Find .md/.yml/.yaml files newer than marker, excluding noise directories.
    # Use -regex to match all extensions in one pass (avoids -o grouping issues).
    find /app \
        \( -path '*/vendor/*' \
        -o -path '*/node_modules/*' \
        -o -path '*/tmp/*' \
        -o -path '*/.git/*' \
        -o -path '*/_repo/*' \
        -o -path '*/.claude/*' \
        \) -prune \
        -o -type f \( -name '*.md' -o -name '*.yml' -o -name '*.yaml' \) \
        -newer "$MARKER" \
        -print -quit 2>/dev/null
}

# Initial build
build

# Start HTTP server in background
cd "$SITE_DIR" || exit 1
python -m http.server 8081 --bind 0.0.0.0 &
echo "[docs] Serving on port 8081"
echo "[docs] Polling for changes every ${POLL_INTERVAL}s (force rebuild every ${FORCE_INTERVAL}s)"

# Poll loop
while true; do
    sleep "$POLL_INTERVAL"
    FORCE_COUNTER=$((FORCE_COUNTER + POLL_INTERVAL))

    CHANGED=$(has_changes)

    if [ -n "$CHANGED" ]; then
        echo "[docs] Change detected: $CHANGED"
        build
        FORCE_COUNTER=0
    elif [ "$FORCE_COUNTER" -ge "$FORCE_INTERVAL" ]; then
        echo "[docs] Force rebuild (${FORCE_INTERVAL}s interval)"
        build
        FORCE_COUNTER=0
    fi
done

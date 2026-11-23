#!/bin/sh
# HD1 start order: restore state, then sync beside the API, then serve.
# The sync runs without HF_HUB_OFFLINE; the API keeps it (backend README).
set -eu
env -u HF_HUB_OFFLINE python -m app.workers.state_sync restore
env -u HF_HUB_OFFLINE python -m app.workers.state_sync run &
exec python -m uvicorn app.main:create_app --factory \
    --host 0.0.0.0 --port 7860 --no-proxy-headers --no-access-log

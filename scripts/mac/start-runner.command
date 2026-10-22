#!/bin/bash
# Double-click this in Finder to start the Copyist runner, which runs jobs an agent queues in
# out/runner/queue/ (see scripts/mac/runner.py). Close the window or press Ctrl-C to stop it.
cd "$(dirname "$0")/../.." || exit 1
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" scripts/mac/runner.py

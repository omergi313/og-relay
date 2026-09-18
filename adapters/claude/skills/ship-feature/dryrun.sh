#!/bin/sh
set -eu
exec python3 "@RELAY_ROOT@/scripts/dryrun.py"

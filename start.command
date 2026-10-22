#!/usr/bin/env bash
# macOS double-click launcher: Finder opens .command files in Terminal, starting in $HOME.
# All launcher logic lives in start.sh (the canonical launcher); this only moves to the repo
# folder and hands off. To allow phones / other devices, run `./start.command --lan` in Terminal.

cd "$(dirname "$0")" || exit 1
exec bash ./start.sh "$@"

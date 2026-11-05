#!/usr/bin/env bash
# devlog.sh - read a Wappa dev server's live log without guessing or touching it.
#
# Usage:
#   scripts/devlog.sh [--dir DIR] [--since HH:MM[:SS]] [--restart] [PATTERN]
#
#   --dir DIR      App folder that holds logs/ (or the logs/ folder itself).
#                  Default: current directory. The server writes logs/ relative
#                  to ITS cwd (SYSTEM_LOG_DIR), i.e. the app folder, not the
#                  wappa repo.
#   --since T      Only records at or after local time T (HH:MM or HH:MM:SS)
#                  of the resolved daily file. Traceback lines stay with
#                  their record.
#   --restart      Start at the last "🚀 Starting Wappa Framework" banner,
#                  i.e. the current server run (each reload prints one).
#   PATTERN        Extended regex (grep -E) applied after the filters above.
#
# File resolution: DIR/logs/current.log (a symlink the server repoints at the
# active wappa_YYYYMMDD.log), else the newest wappa_*.log by name.
# The server's PIDs and port are in DIR/logs/dev.pid (printed to stderr).
#
# Read-only: this script never writes, truncates or moves a log. Never edit a
# live log in place (sed -i replaces the inode and the server keeps writing to
# the deleted file).
#
# Examples:
#   scripts/devlog.sh --dir ../wappa_examples/instagram_conversations_example --restart
#   scripts/devlog.sh --restart 'META_SCHEMA_DRIFT|❌|not accepted'
#   scripts/devlog.sh --since 14:05 '📥 Message from'
set -euo pipefail

BANNER='🚀 Starting Wappa Framework'
dir="."
since=""
restart=0
pattern=""

usage() { sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) dir="${2:?--dir needs a value}"; shift 2 ;;
    --dir=*) dir="${1#*=}"; shift ;;
    --since) since="${2:?--since needs HH:MM}"; shift 2 ;;
    --since=*) since="${1#*=}"; shift ;;
    --restart) restart=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; pattern="${1:-}"; shift || true ;;
    -*) echo "devlog: unknown option $1" >&2; usage >&2; exit 2 ;;
    *) pattern="$1"; shift ;;
  esac
done

if [[ -n "$since" && ! "$since" =~ ^[0-2][0-9]:[0-5][0-9](:[0-5][0-9])?$ ]]; then
  echo "devlog: --since expects HH:MM or HH:MM:SS, got '$since'" >&2
  exit 2
fi

logdir="$dir/logs"
if [[ -e "$dir/current.log" ]] || { [[ ! -d "$logdir" ]] && compgen -G "$dir/wappa_*.log" >/dev/null; }; then
  logdir="$dir"
fi
[[ -d "$logdir" ]] || { echo "devlog: no logs/ folder under '$dir'" >&2; exit 1; }

if [[ -e "$logdir/current.log" ]]; then
  file="$logdir/current.log"
  via="current.log -> $(readlink "$logdir/current.log" 2>/dev/null || echo '?')"
else
  file="$(find "$logdir" -maxdepth 1 -name 'wappa_*.log' -type f 2>/dev/null | sort | tail -n 1)"
  [[ -n "$file" ]] || { echo "devlog: no wappa_*.log in '$logdir'" >&2; exit 1; }
  via="newest wappa_*.log (no current.log)"
fi

echo "==> $file [$via]" >&2
if [[ -f "$logdir/dev.pid" ]]; then
  echo "==> dev.pid: $(tr '\n' ' ' < "$logdir/dev.pid")" >&2
fi

start=1
if [[ "$restart" -eq 1 ]]; then
  line="$(grep -naF "$BANNER" "$file" | tail -n 1 | cut -d: -f1 || true)"
  if [[ -n "$line" ]]; then
    start="$line"
  else
    echo "==> no '$BANNER' banner in this file; showing all of it" >&2
  fi
fi

tail -n "+$start" "$file" \
  | awk -v since="$since" '
      since == "" { print; next }
      /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]/ {
        keep = (substr($0, 12, length(since)) >= since)
      }
      keep { print }
    ' \
  | if [[ -n "$pattern" ]]; then grep -aE -- "$pattern"; else cat; fi

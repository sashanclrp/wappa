#!/usr/bin/env bash
# Print the key names in a dotenv file and whether each one has a value.
# Never prints a value. Usage: scripts/env_keys.sh [path/to/.env]
set -euo pipefail

file="${1:-.env}"
if [[ ! -f "$file" ]]; then
    echo "env_keys: no such file: $file" >&2
    exit 1
fi

while IFS= read -r line || [[ -n "$line" ]]; do
    # Skip blank lines and comments.
    [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line#export }"
    [[ "$line" == *=* ]] || continue
    key="${line%%=*}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${line#*=}"
    # Drop an inline comment and surrounding whitespace/quotes before testing.
    value="${value%%[[:space:]]#*}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    value="${value#[\"\']}"
    value="${value%[\"\']}"
    if [[ -n "$value" ]]; then
        printf '%s\tset\n' "$key"
    else
        printf '%s\tempty\n' "$key"
    fi
done < "$file"

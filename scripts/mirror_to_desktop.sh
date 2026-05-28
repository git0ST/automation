#!/usr/bin/env bash
# Offline mirror — use when GitHub is unreachable and you need to ship/upload
# the repo by hand. Self-locating, so it works no matter where the repo lives.
#
#   ./scripts/mirror_to_desktop.sh
#
# Produces on your Desktop:
#   automation-upload/        ← only the files in commits NOT yet on origin/main
#                               (drag these into GitHub → Add file → Upload files)
#   Automation-mirror/        ← full push-ready clone (origin = GitHub); when the
#                               network is back:  cd Automation-mirror && git push
#   automation-latest.bundle  ← portable backup of ALL commits/branches; restore
#                               anywhere offline with:  git clone <bundle> <dir>
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESK="$HOME/Desktop"
REMOTE="$(git -C "$ROOT" remote get-url origin 2>/dev/null || echo '')"

echo "── INTL offline mirror ───────────────────────────────────────────"
echo "Repo:   $ROOT"
echo "Remote: ${REMOTE:-<none>}"

# Unpushed files (uses the local origin/main tracking ref — works offline).
# Portable array build (macOS ships bash 3.2, which lacks `mapfile`).
CHANGED=()
while IFS= read -r _line; do
  [ -n "$_line" ] && CHANGED+=("$_line")
done < <(git -C "$ROOT" diff --name-only origin/main..main 2>/dev/null || true)

UP="$DESK/automation-upload"
rm -rf "$UP"; mkdir -p "$UP"
if [ "${#CHANGED[@]}" -gt 0 ]; then
  for f in "${CHANGED[@]}"; do
    [ -f "$ROOT/$f" ] || continue
    mkdir -p "$UP/$(dirname "$f")"
    cp "$ROOT/$f" "$UP/$f"
  done
  {
    echo "Files to upload to GitHub (same paths), generated $(date):"
    printf '  %s\n' "${CHANGED[@]}"
  } > "$UP/_UPLOAD_THESE.txt"
  echo "✓ upload folder: $UP  (${#CHANGED[@]} files)"
else
  echo "• nothing unpushed — upload folder left empty"
fi

# Full push-ready clone
MIR="$DESK/Automation-mirror"
rm -rf "$MIR"
git clone --quiet "$ROOT" "$MIR"
[ -n "$REMOTE" ] && git -C "$MIR" remote set-url origin "$REMOTE"
echo "✓ mirror clone:  $MIR"

# Portable bundle of everything
git -C "$ROOT" bundle create "$DESK/automation-latest.bundle" --all >/dev/null
echo "✓ bundle:        $DESK/automation-latest.bundle"

echo "──────────────────────────────────────────────────────────────────"
echo "When GitHub is reachable again, push from the live repo:"
echo "    git -C \"$ROOT\" push origin main"

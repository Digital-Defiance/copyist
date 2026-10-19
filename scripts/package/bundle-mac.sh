#!/usr/bin/env bash
# Build the Mac .app / .dmg with Tauri, after the engine (and optional sidecars) are staged.
#
# Usage:
#   scripts/package/bundle-mac.sh              # unsigned (local smoke test, CI)
#   scripts/package/bundle-mac.sh --sign       # Developer ID + notarize
#
# For --sign, either export the env vars below or let this script pick the
# Digital Defiance Developer ID from the keychain (Jessica has one).
#
#   APPLE_SIGNING_IDENTITY   e.g. "Developer ID Application: Digital Defiance (J6887N729S)"
#   APPLE_TEAM_ID            e.g. J6887N729S
#
# Notarization, either an App Store Connect API key (preferred, used when set):
#   APPLE_API_ISSUER, APPLE_API_KEY, APPLE_API_KEY_PATH (path to AuthKey_XXX.p8)
# or an Apple ID with an app-specific password:
#   APPLE_ID, APPLE_PASSWORD (appleid.apple.com → App-Specific Passwords)
#
# Needs: freeze-engine.sh already run for this Mac's triple (dist/copyist-engine-<triple>,
# or COPYIST_ENGINE=<path>); Node + Rust (app/README.md).
#
# The checkout stays clean: the frozen engine is copied over the tracked placeholder
# in app/src-tauri/binaries/ only for the build and the placeholder is put back on
# exit, and the extra sidecars reach Tauri through a temporary --config file rather
# than an edit to tauri.conf.json (DECISIONS.md, 2026-10-19).
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
sign=0
[[ "${1:-}" == "--sign" ]] && sign=1
case "$(uname -m)" in
  arm64) triple=aarch64-apple-darwin ;;
  x86_64) triple=x86_64-apple-darwin ;;
  *) echo "Unsupported Mac arch" >&2; exit 1 ;;
esac
bin_dir="$root/app/src-tauri/binaries"
frozen="${COPYIST_ENGINE:-$root/dist/copyist-engine-$triple}"
if [[ ! -x "$frozen" ]] || head -c 2 "$frozen" | grep -q '^#!'; then
  echo "No frozen engine at $frozen. Run:" >&2
  echo "  scripts/package/freeze-engine.sh $triple" >&2
  exit 1
fi

# Put the frozen engine where Tauri looks, and the tracked placeholder back afterwards.
engine="$bin_dir/copyist-engine-$triple"
work="$(mktemp -d)"
cp -p "$engine" "$work/placeholder"
restore() {
  cp -p "$work/placeholder" "$engine"
  rm -rf "$work"
}
trap restore EXIT
trap 'exit 130' INT TERM
cp "$frozen" "$engine"
chmod +x "$engine"
echo "Staged the frozen engine ($(du -h "$frozen" | awk '{print $1}'))"

# Optional Metal / sfizz sidecars from the developer cache (same folder as the engine
# in the .app). They're gitignored in binaries/.
external='"binaries/copyist-engine"'
for name in yue-synth yue-plan yue-transcribe yue-tokenize sfizz_render; do
  src=""
  [[ -x "$root/.cache/yue2.cpp/build/$name" ]] && src="$root/.cache/yue2.cpp/build/$name"
  [[ -x "$root/.cache/sfizz/$name" ]] && src="$root/.cache/sfizz/$name"
  if [[ -n "$src" ]]; then
    cp "$src" "$bin_dir/$name-$triple"
    chmod +x "$bin_dir/$name-$triple"
    echo "Staged $name"
  fi
  [[ -f "$bin_dir/$name-$triple" ]] && external="$external, \"binaries/$name\""
done
# Tauri merges this over tauri.conf.json (JSON merge patch: the array replaces the
# engine-only list there).
conf="$work/sidecars.conf.json"
printf '{"bundle": {"externalBin": [%s]}}\n' "$external" > "$conf"
echo "externalBin: [$external]"

pick_identity() {
  # Prefer Digital Defiance's Developer ID Application, then Jessica's.
  local line
  line="$(security find-identity -v -p codesigning 2>/dev/null \
    | grep 'Developer ID Application: Digital Defiance' | head -1 || true)"
  if [[ -z "$line" ]]; then
    line="$(security find-identity -v -p codesigning 2>/dev/null \
      | grep 'Developer ID Application:' | head -1 || true)"
  fi
  # "  7) HASH "Developer ID Application: Name (TEAM)""
  sed -n 's/.*"\(Developer ID Application: .*\)".*/\1/p' <<<"$line"
}
cd "$root/app"
if [[ ! -d node_modules ]]; then
  npm install
fi
if [[ "$sign" -eq 1 ]]; then
  if [[ -z "${APPLE_SIGNING_IDENTITY:-}" ]]; then
    APPLE_SIGNING_IDENTITY="$(pick_identity)"
    export APPLE_SIGNING_IDENTITY
  fi
  if [[ -z "${APPLE_SIGNING_IDENTITY:-}" ]]; then
    echo "No Developer ID Application identity in the keychain." >&2
    echo "Install a Developer ID cert from developer.apple.com, or set APPLE_SIGNING_IDENTITY." >&2
    exit 1
  fi
  echo "Signing as: $APPLE_SIGNING_IDENTITY"
  if [[ -z "${APPLE_TEAM_ID:-}" ]]; then
    # TEAMID from "… (J6887N729S)"
    APPLE_TEAM_ID="$(sed -n 's/.*(\([A-Z0-9]\{10\}\))$/\1/p' <<<"$APPLE_SIGNING_IDENTITY")"
    export APPLE_TEAM_ID
  fi
  if [[ -n "${APPLE_API_KEY:-}" && -n "${APPLE_API_ISSUER:-}" && -n "${APPLE_API_KEY_PATH:-}" ]]; then
    # The API key wins; drop the Apple ID so Tauri doesn't try it without a password.
    unset APPLE_ID APPLE_PASSWORD
    export APPLE_API_ISSUER APPLE_API_KEY APPLE_API_KEY_PATH
    echo "Notarizing with the App Store Connect API key"
  elif [[ -n "${APPLE_ID:-}" && -n "${APPLE_PASSWORD:-}" ]]; then
    export APPLE_ID APPLE_PASSWORD
    echo "Notarizing with the Apple ID"
  else
    echo "Notarization needs either:" >&2
    echo "  APPLE_API_ISSUER + APPLE_API_KEY + APPLE_API_KEY_PATH" >&2
    echo "or APPLE_ID + APPLE_PASSWORD (app-specific) + APPLE_TEAM_ID=$APPLE_TEAM_ID" >&2
    exit 1
  fi
  export APPLE_SIGNING_IDENTITY APPLE_TEAM_ID
  echo "Building signed + notarized (Tauri will submit to Apple; this can take several minutes)…"
  npm run build -- --config "$conf"
else
  # Keep a local unsigned build from picking up signing/notarizing settings in the shell.
  unset APPLE_SIGNING_IDENTITY APPLE_CERTIFICATE APPLE_ID APPLE_PASSWORD \
    APPLE_API_ISSUER APPLE_API_KEY APPLE_API_KEY_PATH
  echo "Building unsigned (local smoke test). For distribution: scripts/package/bundle-mac.sh --sign"
  npm run build -- --config "$conf"
fi
echo
echo "Artifacts:"
find "$root/app/src-tauri/target/release/bundle" -maxdepth 3 \( -name '*.app' -o -name '*.dmg' \) 2>/dev/null || true
if [[ "$sign" -eq 1 ]]; then
  dmg="$(find "$root/app/src-tauri/target/release/bundle/dmg" -name '*.dmg' 2>/dev/null | head -1 || true)"
  if [[ -n "$dmg" ]]; then
    # Tauri notarizes and staples the .app, not the DMG around it; do the DMG here.
    echo
    echo "Notarizing the DMG (a few minutes)…"
    if [[ -n "${APPLE_API_KEY:-}" ]]; then
      xcrun notarytool submit "$dmg" --key "$APPLE_API_KEY_PATH" --key-id "$APPLE_API_KEY" \
        --issuer "$APPLE_API_ISSUER" --wait
    else
      xcrun notarytool submit "$dmg" --apple-id "$APPLE_ID" --password "$APPLE_PASSWORD" \
        --team-id "$APPLE_TEAM_ID" --wait
    fi
    xcrun stapler staple "$dmg"
    spctl -a -vv -t install "$dmg"
    echo
    echo "SHA-256 for the tap's cask (Digital-Defiance/homebrew-tap, Casks/copyist.rb):"
    shasum -a 256 "$dmg"
  fi
fi

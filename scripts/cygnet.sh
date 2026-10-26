#!/usr/bin/env bash
#
# cygnet.sh - Build the Cygnet databases and web UI for the omw-kinship site
#
# Usage: bash scripts/cygnet.sh [--rebuild]
#   --rebuild   Wipe the Cygnet work directory first
#
# Run scripts/build.py first: this stages its release/omw-kin-VERSION/ lexicons.
# Needs a clone of omwn/cygnet next to this repository.
#
# Produces (in docs/, served by GitHub Pages):
#   kin-cygnet.db.gz, kin-provenance.db.gz   the databases (gitignored;
#                                            attach them to the GitHub release)
#   index.html, relations.json, local.json   the web UI

set -euo pipefail

VERSION="0.2"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CYGNET_DIR="$(cd "$PROJECT_DIR/../cygnet" && pwd)"
CYGNET_WORK="$PROJECT_DIR/build/cygnet-work"
RELEASE="$PROJECT_DIR/release/omw-kin-$VERSION"

if [[ "${1:-}" == "--rebuild" ]]; then
    echo "Cleaning the Cygnet work directory"
    rm -rf "$CYGNET_WORK"
fi

if [[ ! -d "$RELEASE" ]]; then
    echo "No $RELEASE: run 'uv run scripts/build.py' first" >&2
    exit 1
fi

# Pre-stage the lexicons, so the download step skips the release URL.
mkdir -p "$CYGNET_WORK/bin/raw_wns"
cp "$PROJECT_DIR/etc/wordnets.toml" "$CYGNET_WORK/wordnets.toml"
find "$CYGNET_WORK/bin/raw_wns" -name 'omw-kin*.xml' -delete
find "$RELEASE" -name 'omw-kin*.xml' -exec cp {} "$CYGNET_WORK/bin/raw_wns/" \;

# --all-languages: keep every language, not only those with another wordnet.
bash "$CYGNET_DIR/build.sh" --work-dir "$CYGNET_WORK" --all-languages --skip-tests

echo "Deploying to docs/"
cp "$CYGNET_DIR/web/index.html"        "$PROJECT_DIR/docs/"
cp "$CYGNET_DIR/web/relations.json"    "$PROJECT_DIR/docs/"
cp "$PROJECT_DIR/etc/local.json"       "$PROJECT_DIR/docs/"
touch "$PROJECT_DIR/docs/.nojekyll"
cp "$CYGNET_WORK/web/cygnet.db.gz"     "$PROJECT_DIR/docs/kin-cygnet.db.gz"
cp "$CYGNET_WORK/web/provenance.db.gz" "$PROJECT_DIR/docs/kin-provenance.db.gz"

echo "Done: serve docs/ with 'bash run.sh'"

#!/bin/bash
# Packs dist/Autocorrect.app into dist/Autocorrect.dmg with an "Applications" shortcut to drag onto.
set -e
cd "$(dirname "$0")/.."
STAGE=$(mktemp -d)
cp -R dist/Autocorrect.app "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Autocorrect" -srcfolder "$STAGE" -ov -format UDZO dist/Autocorrect.dmg
rm -rf "$STAGE"
echo "dist/Autocorrect.dmg ready"

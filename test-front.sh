#!/usr/bin/env bash
# Tests de fumée du front sur un faux navigateur (JavaScriptCore, présent sur macOS). Code retour != 0 en cas d'échec.
cd "$(dirname "$0")" || exit 1
JSC=/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc
[ -x "$JSC" ] || { echo "jsc introuvable : ce test nécessite macOS (ou adaptez-le à Node)."; exit 2; }
status=0
for t in frontend/tests/*.test.js; do
  echo "== $t"
  "$JSC" -m "$t" 2>&1 | cut -c1-200 || status=1
  [ "${PIPESTATUS[0]}" -eq 0 ] || status=1
done
exit $status

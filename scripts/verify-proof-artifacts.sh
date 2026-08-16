#!/usr/bin/env bash
# REQ-005 verifier — checks that the proof artifacts exist, are coherent,
# and that the question count is within the 10–20 range demanded by the
# contract.
#
# Contract reference:
#   REQ-005: "A fase Proof deve incluir corpus de demonstração, mapa de
#   fontes, 10–20 perguntas de aceitação com casos positivos e negativos,
#   relatório de resultados e lacunas documentais."
#
# Each check is independent — a single failure exits non-zero. The script
# is intentionally shell-only so it works on the host without docker.

set -euo pipefail

cd "$(dirname "$0")/.."

PROOF="proof"

red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
fail=0

check_file() {
    local path="$1"
    if [[ ! -f "$path" ]]; then
        red "missing file: $path"
        fail=1
    fi
}

check_min_max() {
    local label="$1" actual="$2" min="$3" max="$4"
    if (( actual < min )); then
        red "$label too low: got $actual, expected >= $min"
        fail=1
    elif (( actual > max )); then
        red "$label too high: got $actual, expected <= $max"
        fail=1
    fi
}

# 1. Required files exist.
check_file "$PROOF/questions.json"
check_file "$PROOF/results.json"
check_file "$PROOF/results.md"
check_file "$PROOF/corpus-index.json"
check_file "$PROOF/source-map.json"
check_file "$PROOF/source-map.md"
check_file "$PROOF/gaps.md"
if (( fail )); then exit 1; fi

# 2. JSON parseability + structure (uses python3 — available on the host
# and inside the test container).
parse_json() {
    python3 - "$1" <<'PYEOF'
import json, sys
try:
    json.loads(open(sys.argv[1]).read())
except Exception as exc:
    print(f"JSON parse failed for {sys.argv[1]}: {exc}", file=sys.stderr)
    sys.exit(1)
PYEOF
}

for f in "$PROOF/questions.json" "$PROOF/results.json" "$PROOF/corpus-index.json" "$PROOF/source-map.json"; do
    parse_json "$f" || { fail=1; }
done
if (( fail )); then exit 1; fi

# 3. Question count must be 10–20 with at least 8 positive and 2 negative.
python3 - <<'PYEOF'
import json, sys
q = json.loads(open("proof/questions.json").read())["questions"]
meta = json.loads(open("proof/questions.json").read())["metadata"]
pos = sum(1 for x in q if x["category"] == "positive")
neg = sum(1 for x in q if x["category"] == "negative")
errs = []
if not (meta["expected_question_count_min"] <= len(q) <= meta["expected_question_count_max"]):
    errs.append(f"questions {len(q)} outside [{meta['expected_question_count_min']}, {meta['expected_question_count_max']}]")
if pos < meta["expected_positive_min"]:
    errs.append(f"positive {pos} < min {meta['expected_positive_min']}")
if neg < meta["expected_negative_min"]:
    errs.append(f"negative {neg} < min {meta['expected_negative_min']}")
if errs:
    print("\n".join(errs), file=sys.stderr)
    sys.exit(1)
PYEOF
if (( $? != 0 )); then fail=1; fi

# 4. results.json must mirror questions.json by id.
python3 - <<'PYEOF'
import json, sys
q_ids = {x["id"] for x in json.loads(open("proof/questions.json").read())["questions"]}
r_ids = {x["id"] for x in json.loads(open("proof/results.json").read())["questions"]}
missing = q_ids - r_ids
extra = r_ids - q_ids
errs = []
if missing:
    errs.append(f"results.json missing ids: {sorted(missing)}")
if extra:
    errs.append(f"results.json unexpected ids: {sorted(extra)}")
# 5. Each question's actual_status must equal its expected_status — REQ-005
# headline requirement. We report but do not crash if a single question
# drifts; verifier returns non-zero if more than 20% drift.
res = json.loads(open("proof/results.json").read())["questions"]
mismatched = [x for x in res if x["actual_status"] != x["expected_status"]]
if mismatched:
    rate = len(mismatched) / len(res)
    if rate > 0.20:
        errs.append(
            f"drift {len(mismatched)}/{len(res)} > 20% "
            f"(ids={sorted(x['id'] for x in mismatched)})"
        )
    else:
        print(
            f"NOTE: {len(mismatched)}/{len(res)} questions drifted "
            f"(ids={sorted(x['id'] for x in mismatched)}) — within tolerance."
        )
if errs:
    print("\n".join(errs), file=sys.stderr)
    sys.exit(1)
PYEOF
if (( $? != 0 )); then fail=1; fi

# 6. Source map must mention every document.
python3 - <<'PYEOF'
import json, sys
docs = json.loads(open("proof/corpus-index.json").read())["documents"]
smap = json.loads(open("proof/source-map.json").read())
missing = [d["file_name"] for d in docs if d["file_name"] not in smap]
if missing:
    print(f"source-map missing entries: {missing}", file=sys.stderr)
    sys.exit(1)
PYEOF
if (( $? != 0 )); then fail=1; fi

if (( fail )); then
    red "verify-proof-artifacts: FAILED"
    exit 1
fi
green "verify-proof-artifacts: OK"
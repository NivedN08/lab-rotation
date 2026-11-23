#!/usr/bin/env bash
# Bruin in Lab Rotation, in three short steps for a screen recording. Reads the current
# warehouse (data/warehouse.duckdb), which lab.learner.refresh updates after every session.
#
#   bash bruin/demo.sh          # from anywhere in the repo
#   bash bruin/demo.sh --open   # also open the docs page in the browser
set -u
cd "$(dirname "$0")/.." || exit 1
command -v bruin >/dev/null || { echo "bruin is not installed (https://getbruin.com)"; exit 1; }

DOCS=data/bruin/docs/lab-rotation.html
OPEN=""
[ "${1:-}" = "--open" ] && OPEN="--open"

title() { printf '\n== %s\n\n' "$1"; }

# `bruin query` appends logs/queries to .gitignore when that line is missing (logs/ is already
# ignored); keep the file exactly as it was so the demo never leaves a change behind.
query() {
    local snap rc
    snap=$(mktemp)
    [ -f .gitignore ] && cp .gitignore "$snap"
    bruin query -c duckdb-default -q "$1" 2>&1
    rc=$?
    [ -f .gitignore ] && ! cmp -s .gitignore "$snap" && cp "$snap" .gitignore
    rm -f "$snap"
    return $rc
}

MISSES="
SELECT CASE skill
         WHEN 'duplicate_rows'  THEN 'duplicate rows'
         WHEN 'unit_mismatch'   THEN 'unit mix-up'
         WHEN 'dictionary_flip' THEN 'dictionary flip'
         WHEN 'confounder'      THEN 'confounder'
         WHEN 'hidden_variable' THEN 'hidden variable'
         WHEN 'none'            THEN 'no trap (clean data)'
         ELSE skill END                                                  AS trap,
       count(*)                                                          AS attempts,
       count(*) FILTER (WHERE NOT correct)                               AS misses,
       CAST(round(100.0 * count(*) FILTER (WHERE NOT correct) / count(*)) AS INTEGER) || '%'
                                                                         AS miss_rate,
       round(avg(score), 2)                                              AS avg_score
FROM learn.skill_attempts
GROUP BY skill
ORDER BY count(*) FILTER (WHERE NOT correct) / count(*) DESC, attempts DESC, trap"

TOTALS="
SELECT count(DISTINCT learner) AS players, count(DISTINCT session_id) AS sessions,
       count(*) AS graded_tasks
FROM learn.skill_attempts"

status=0

title "1/3  Which trap do players miss most? (bruin query on learn.skill_attempts; a miss is a score under 0.6)"
if out=$(query "$MISSES"); then
    printf '%s\n' "$out"
    query "$TOTALS"
else
    echo "No graded sessions in the warehouse yet. Play a session, or run: uv run python -m lab.learner.refresh"
fi

title "2/3  Where the mastery numbers come from (bruin lineage of learn.bkt_mastery)"
bruin lineage --full bruin/assets/learn/bkt_mastery.py || status=1

title "3/3  The whole pipeline as one web page (bruin docs)"
mkdir -p "$(dirname "$DOCS")"
if bruin docs --title "Lab Rotation: Bruin pipeline" -o "$DOCS" $OPEN bruin >/dev/null; then
    echo "Assets, checks and lineage: file://$PWD/$DOCS"
else
    status=1
fi
exit $status

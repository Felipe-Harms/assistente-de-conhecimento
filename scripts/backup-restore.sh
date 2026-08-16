#!/usr/bin/env bash
# REQ-009 — backup & restore for the pgvector volume + corpus files.
#
# Two operations, picked from $1:
#
#   backup   dump the Postgres database with `pg_dump` (custom format) and
#            archive the on-disk corpus directory used by the demo. Writes
#            the two artifacts into $BACKUP_DIR (default ./backups) with a
#            timestamped subdirectory. Returns the path on stdout.
#
#   restore  read the path from $2 and apply it to the running stack:
#            * pg_restore into the live database (drops & recreates the
#              public schema so the dump is the source of truth);
#            * replace the corpus directory in $BACKUP_CORPUS with the
#              archived copy if the archive contains one.
#            Refuses to run unless the operator passes --confirm so a
#            stray `restore` cannot wipe production data.
#
# The script lives entirely on the host so it does not require the test
# image; it relies on the `db` container running and on `docker` being on
# PATH. The dump format (`--format=custom`) is the recommended pg_dump
# output for a single-DB restore and is what `pg_restore` consumes.
#
# Usage:
#   ./scripts/backup-restore.sh backup [BACKUP_DIR]
#   ./scripts/backup-restore.sh restore <backup-path> --confirm

set -euo pipefail

cd "$(dirname "$0")/.."

DB_CONTAINER="${DB_CONTAINER:-upworkkb-db}"
BACKUP_DIR="${BACKUP_DIR:-$(pwd)/backups}"
CORPUS_SRC="${CORPUS_SRC:-$(pwd)/data/corpus}"
BACKUP_CORPUS="${BACKUP_CORPUS:-$CORPUS_SRC}"

red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
note()  { printf '\033[36m%s\033[0m\n' "$*"; }

usage() {
    cat <<'USAGE'
Usage:
  ./scripts/backup-restore.sh backup [BACKUP_DIR]
  ./scripts/backup-restore.sh restore <backup-path> --confirm

Environment overrides:
  DB_CONTAINER   Postgres container name (default: upworkkb-db)
  BACKUP_DIR     Destination directory for backups (default: ./backups)
  CORPUS_SRC     Corpus directory on the host (default: ./data/corpus)
  BACKUP_CORPUS  Where to materialise the corpus on restore (default: $CORPUS_SRC)
USAGE
}

require_db() {
    if ! docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
        red "container $DB_CONTAINER is not running; start the stack first"
        exit 1
    fi
}

cmd_backup() {
    require_db
    local stamp
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    local target="${BACKUP_DIR%/}/$stamp"
    mkdir -p "$target"

    note "writing pg_dump to $target/db.dump"
    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD:-change-me-locally-only}" \
        "$DB_CONTAINER" \
        pg_dump -U "${POSTGRES_USER:-upworkkb}" -d "${POSTGRES_DB:-upworkkb}" \
        --format=custom --no-owner --clean --if-exists \
        > "$target/db.dump"

    if [[ -d "$CORPUS_SRC" ]]; then
        note "archiving corpus directory to $target/corpus.tar.gz"
        tar -czf "$target/corpus.tar.gz" -C "$(dirname "$CORPUS_SRC")" "$(basename "$CORPUS_SRC")"
    fi

    # SHA256 sidecar — operators can compare a future backup against an
    # older one to confirm integrity before deleting the older one.
    (cd "$target" && sha256sum db.dump corpus.tar.gz 2>/dev/null > SHA256SUMS) || true

    green "backup complete: $target"
    printf '%s\n' "$target"
}

cmd_restore() {
    local backup_path="${1:-}"
    local confirm="${2:-}"
    if [[ -z "$backup_path" ]]; then
        red "restore requires a backup path; pass it as the first arg"
        usage >&2
        exit 2
    fi
    if [[ "$confirm" != "--confirm" ]]; then
        red "refusing to restore without --confirm (this drops the public schema)"
        exit 2
    fi
    if [[ ! -d "$backup_path" ]]; then
        red "backup directory not found: $backup_path"
        exit 1
    fi
    require_db

    if [[ -f "$backup_path/db.dump" ]]; then
        note "restoring pg_dump into $DB_CONTAINER"
        # Drop & recreate the public schema so the dump is authoritative.
        docker exec -e PGPASSWORD="${POSTGRES_PASSWORD:-change-me-locally-only}" \
            "$DB_CONTAINER" \
            psql -U "${POSTGRES_USER:-upworkkb}" -d "${POSTGRES_DB:-upworkkb}" \
            -v ON_ERROR_STOP=1 \
            -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO ${POSTGRES_USER:-upworkkb};"

        docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD:-change-me-locally-only}" \
            "$DB_CONTAINER" \
            pg_restore -U "${POSTGRES_USER:-upworkkb}" -d "${POSTGRES_DB:-upworkkb}" \
                --no-owner --clean --if-exists --single-transaction \
                < "$backup_path/db.dump"
    else
        red "no db.dump inside $backup_path; aborting"
        exit 1
    fi

    if [[ -f "$backup_path/corpus.tar.gz" ]]; then
        note "restoring corpus directory to $BACKUP_CORPUS"
        mkdir -p "$BACKUP_CORPUS"
        tar -xzf "$backup_path/corpus.tar.gz" -C "$(dirname "$BACKUP_CORPUS")"
    fi

    green "restore complete from $backup_path"
}

case "${1:-}" in
    backup)
        cmd_backup
        ;;
    restore)
        shift
        cmd_restore "${1:-}" "${2:-}"
        ;;
    -h|--help|help|"")
        usage
        ;;
    *)
        red "unknown command: $1"
        usage >&2
        exit 2
        ;;
esac
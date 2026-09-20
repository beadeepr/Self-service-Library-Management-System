#!/bin/sh
set -eu
umask 077
mkdir -p /backups
while true; do
    backup_stamp=$(date -u +%Y%m%dT%H%M%SZ)
    backup_file="/backups/library-${backup_stamp}.sql"
    if MYSQL_PWD="$MYSQL_PASSWORD" mysqldump --host=mysql --user="$MYSQL_USER" \
        --single-transaction --no-tablespaces --skip-lock-tables "$MYSQL_DATABASE" > "${backup_file}.partial"; then
        gzip -c "${backup_file}.partial" > "${backup_file}.gz"
        rm -f "${backup_file}.partial"
        echo "Backup complete: ${backup_file}.gz"
    else
        echo "Backup failed; partial file retained for diagnosis" >&2
    fi
    sleep 86400
done

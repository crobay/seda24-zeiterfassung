#!/bin/bash
# Super-PIN zuruecksetzen (vergessen / nach 10 Fehlversuchen dauerhaft gesperrt) - NUR auf dem Server, als postgres.
# Danach richtet Drazen die PIN im Cockpit neu ein (mit Login-Passwort). Wird in audit_log protokolliert.
# Aufruf: sudo tools/superpin_reset.sh <datenbank> "<Grund>" [<neue Inhaber-E-Mail>]
set -euo pipefail
DB="${1:?Datenbank (seda24_zeiterfassung oder dev_cockpit)}"; GRUND="${2:?Grund}"; NEU="${3:-}"
sudo -n -u postgres psql -X -q -v ON_ERROR_STOP=1 -d "$DB" -v grund="$GRUND" -v neu="$NEU" <<'SQL'
BEGIN;
UPDATE superpin SET pin_hash = NULL, fehlversuche = 0, gesperrt_bis = NULL, dauerhaft_gesperrt = false, gesetzt_am = NULL,
       user_id = coalesce((SELECT id FROM users WHERE email = nullif(:'neu', '') AND role::text = 'ADMIN'), user_id);
INSERT INTO audit_log (user_id, action, entity_type, details, created_at)
SELECT user_id, 'superpin_zurueckgesetzt', 'superpin', 'Super-PIN auf dem Server zurückgesetzt (' || current_user || '): ' || :'grund', now()
  FROM superpin;
COMMIT;
SELECT 'Super-PIN zurueckgesetzt, Inhaber user ' || user_id FROM superpin;
SQL

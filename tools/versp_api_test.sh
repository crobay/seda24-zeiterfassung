#!/bin/bash
# NUR DEV: verspaetet uebertragen + Telegram-Toleranz (T9999 temporaer an Lidl Bie2, raeumt selbst auf). Aufruf: bash tools/versp_api_test.sh
cd /var/www/vhosts/seda.de/dev.seda.de/cockpit/backend
PG="sudo -n -u postgres psql -X -q -At -d dev_cockpit"
EMAIL=$(cd /tmp && $PG -c "select u.email from employees e join users u on u.id=e.user_id where e.id=50")
TM=$(venv/bin/python ../tools/dev_token.py "$EMAIL" 2>/dev/null | awk '{print $NF}' | tail -1)
TA=$(venv/bin/python ../tools/dev_token.py admin@seda24.de 2>/dev/null | awk '{print $NF}' | tail -1)
API=http://127.0.0.1:8003/api/v1
LOG=logs/dev_uvicorn.log
ok=0; bad=0; chk(){ if [ "$1" = "$2" ]; then echo "OK   $3"; ok=$((ok+1)); else echo "FAIL $3 (ist '$1', soll '$2')"; bad=$((bad+1)); fi; }
cleanup(){ (cd /tmp && $PG -c "delete from time_entries where employee_id=50 and object_id=20 and check_in > now() - interval '2 days';
  delete from schedules where employee_id=50 and object_id=20 and date=current_date;
  delete from employee_object_assignments where employee_id=50 and object_id=20;") ; }
cleanup
START=$(date -d '-60 min' +%H:%M:00); ENDE=$(date -d '+120 min' +%H:%M:00)
(cd /tmp && $PG -c "insert into employee_object_assignments (employee_id, object_id, tracking_category, is_active) values (50,20,'C',true);
  insert into schedules (employee_id, object_id, date, start_time, end_time, status, no_stamp_notified) values (50,20,current_date,'$START','$ENDE','normal',true)")
ts(){ date -u -d "@$(( $(date -d "$(date +%F) $START" +%s) + $1 * 60 ))" +%Y-%m-%dT%H:%M:%S.000Z; }

# A: Handy-Kommen 3 Min nach Schichtbeginn, kommt ~57 Min spaeter an -> keine Meldung, Zeichen 📶
N=$(wc -l < $LOG)
R=$(curl -s -X POST $API/time-entries/check-in -H "Authorization: Bearer $TM" -H 'Content-Type: application/json' \
  -d "{\"object_id\":20,\"client_timestamp\":\"$(ts 3)\",\"client_id\":\"versp-test-a-$(date +%s)\"}")
ID=$(echo "$R" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))")
[ -n "$ID" ] || echo "Kommen A: $R"
sleep 1
chk "$(tail -n +$N $LOG | grep -c "Kommen innerhalb Toleranz (Eintrag $ID")" 1 "A: Log 'innerhalb Toleranz'"
chk "$(tail -n +$N $LOG | grep -c "Spaetes Kommen gemeldet (Eintrag $ID")" 0 "A: keine Meldung 'erst um'"
Z=$(curl -s -H "Authorization: Bearer $TA" "$API/cockpit/zeiten/$ID")
chk "$(echo "$Z" | python3 -c "import json,sys; v=json.load(sys.stdin)['verspaetet']; print(len(v), v[0]['art'] if v else '')")" "1 kommen" "A: Cockpit-Zeile hat 1 Hinweis (Kommen)"
echo "     Tooltip: $(echo "$Z" | python3 -c "import json,sys; print(json.load(sys.stdin)['verspaetet'][0]['text'])")"
# Gehen sauber (online) -> kein Gehen-Hinweis
curl -s -X POST $API/time-entries/check-out -H "Authorization: Bearer $TM" -H 'Content-Type: application/json' -d '{}' > /dev/null
Z=$(curl -s -H "Authorization: Bearer $TA" "$API/cockpit/zeiten/$ID")
chk "$(echo "$Z" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['gehen'] is not None, [v['art'] for v in d['verspaetet']])")" "True ['kommen']" "A: Gehen online -> nur Kommen-Zeichen"
B=$(curl -s -H "Authorization: Bearer $TA" "$API/admin/bookings/all?start_date=$(date +%F)&end_date=$(date +%F)" | python3 -c "
import json,sys; d=json.load(sys.stdin); d=d if isinstance(d,list) else d.get('bookings',d)
print([ (len(b.get('verspaetet') or []), b.get('sync_delay_minutes')>=50) for b in d if b.get('id')==int('$ID' or 0)])")
chk "$B" "[(1, True)]" "A: alte Journal-Ansicht liefert Hinweis"
cleanup; (cd /tmp && $PG -c "insert into employee_object_assignments (employee_id, object_id, tracking_category, is_active) values (50,20,'C',true);
  insert into schedules (employee_id, object_id, date, start_time, end_time, status, no_stamp_notified) values (50,20,current_date,'$START','$ENDE','normal',true)")

# B: Handy-Kommen 20 Min nach Schichtbeginn -> Meldung 'erst um'
N=$(wc -l < $LOG)
R=$(curl -s -X POST $API/time-entries/check-in -H "Authorization: Bearer $TM" -H 'Content-Type: application/json' \
  -d "{\"object_id\":20,\"client_timestamp\":\"$(ts 20)\",\"client_id\":\"versp-test-b-$(date +%s)\"}")
ID=$(echo "$R" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
[ -n "$ID" ] || echo "     Antwort: $R"
sleep 1
chk "$(tail -n +$N $LOG | grep -c "Spaetes Kommen gemeldet (Eintrag $ID")" 1 "B: Meldung 'erst um' (20 Min nach Beginn)"
# C: Online-Kommen jetzt (60 Min nach Beginn) ohne Offline -> Meldung, kein Zeichen
cleanup; (cd /tmp && $PG -c "insert into employee_object_assignments (employee_id, object_id, tracking_category, is_active) values (50,20,'C',true);
  insert into schedules (employee_id, object_id, date, start_time, end_time, status, no_stamp_notified) values (50,20,current_date,'$START','$ENDE','normal',true)")
N=$(wc -l < $LOG)
R=$(curl -s -X POST $API/time-entries/check-in -H "Authorization: Bearer $TM" -H 'Content-Type: application/json' -d '{"object_id":20}')
ID=$(echo "$R" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
[ -n "$ID" ] || echo "     Antwort: $R"
sleep 1
chk "$(tail -n +$N $LOG | grep -c "Spaetes Kommen gemeldet (Eintrag $ID")" 1 "C: online 60 Min zu spaet -> Meldung"
chk "$(curl -s -H "Authorization: Bearer $TA" "$API/cockpit/zeiten/$ID" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['verspaetet']))")" 0 "C: sauber gestempelt -> kein Zeichen"
cleanup
echo "== $ok OK, $bad FAIL"

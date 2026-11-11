/**
 * Zwischenspeicher der zuletzt bekannten C-Objekte (Stempeluhr KOMMEN/GEHEN).
 * Wird bei jedem erfolgreichen /my-c-objects gesetzt und ohne Verbindung gelesen.
 * Pro Benutzer (userEmail), Logout leert ihn mit localStorage.clear().
 * Dazu die heutigen Schichten (nur am selben Tag gueltig) fuer die KOMMEN-Sperre offline.
 */
const KEY = 'seda_c_objects_cache';

export function saveCObjects(objects) {
  try {
    localStorage.setItem(KEY, JSON.stringify({
      email: localStorage.getItem('userEmail') || '',
      objects: objects || [],
      saved_at: new Date().toISOString(),
    }));
  } catch (e) { /* Speicher voll/gesperrt: ignorieren */ }
}

export function loadCachedCObjects() {
  try {
    const c = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (!c || !Array.isArray(c.objects)) return [];
    if ((c.email || '') !== (localStorage.getItem('userEmail') || '')) return [];
    return c.objects;
  } catch (e) {
    return [];
  }
}

const SHIFTS_KEY = 'seda_today_shifts_cache';

function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

export function saveTodayShifts(shifts) {
  try {
    localStorage.setItem(SHIFTS_KEY, JSON.stringify({
      email: localStorage.getItem('userEmail') || '',
      day: todayStr(),
      shifts: shifts || [],
    }));
  } catch (e) { /* ignorieren */ }
}

export function loadCachedTodayShifts() {
  try {
    const c = JSON.parse(localStorage.getItem(SHIFTS_KEY) || 'null');
    if (!c || !Array.isArray(c.shifts) || c.day !== todayStr()) return [];
    if ((c.email || '') !== (localStorage.getItem('userEmail') || '')) return [];
    return c.shifts;
  } catch (e) {
    return [];
  }
}

/**
 * Zwischenspeicher der zuletzt bekannten C-Objekte (Stempeluhr KOMMEN/GEHEN).
 * Wird bei jedem erfolgreichen /my-c-objects gesetzt und ohne Verbindung gelesen.
 * Pro Benutzer (userEmail), Logout leert ihn mit localStorage.clear().
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

// Gemeinsame Helfer fuer Stempeluhr und Historie: Erkennen, ob eine Antwort wirklich von unserem Server kommt
// (Kennung X-Seda24 + JSON, nicht von einem Captive Portal), und die noch nicht uebertragenen Stempel.
export const QUEUE_KEY = 'bie2_offline_queue';

export function vonUnseremServer(res) {
  if (!res || !res.headers) return false;
  const typ = String(res.headers['content-type'] || '');
  return res.headers['x-seda24'] === '1' && typ.includes('application/json');
}

export function currentOwner() {
  return localStorage.getItem('userEmail') || '';
}

export function isOwnItem(i) {
  return !i.owner || i.owner === currentOwner();
}

export function ausstehendeStempel() {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]').filter(i => i.status !== 'synced' && isOwnItem(i));
  } catch { return []; }
}

export const AKTION_NAME = { check_in: 'Kommen', check_out: 'Gehen', pause_start: 'Pause', pause_end: 'Pause Ende' };
export const uhrzeit = (iso) => new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
export const stempelText = (items) => items.map(i => `${AKTION_NAME[i.action]} ${uhrzeit(i.timestamp)}`).join(' · ');

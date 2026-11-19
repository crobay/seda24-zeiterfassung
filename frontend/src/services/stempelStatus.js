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

export const AKTION_NAME = { check_in: 'Kommen', check_out: 'Gehen', pause_start: 'Pause', pause_end: 'Pause Ende', mehrzeit: 'Mehrzeit-Antrag' };
export const uhrzeit = (iso) => new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
export const stempelText = (items) => items.map(i => `${AKTION_NAME[i.action]} ${uhrzeit(i.timestamp)}`).join(' · ');

// Zentraler Filter fuer alle Anfragen an unsere API: Antworten ohne Server-Kennung (z.B. Anmeldeseite im
// Gast-WLAN, Weiterleitung, fremdes 403/511) werden wie "kein Netz" behandelt (Fehler ohne response).
// So greifen ueberall die vorhandenen Offline-Wege, statt HTML als Daten zu uebernehmen.
export function installiereServerPruefung(instanz, apiUrl) {
  const istApi = (config) => `${(config && config.baseURL) || ''}${(config && config.url) || ''}`.startsWith(apiUrl);
  const keinNetz = (config, status) => {
    const e = new Error(`Keine Antwort unseres Servers${status ? ` (HTTP ${status})` : ''}`);
    e.code = 'ERR_NICHT_UNSER_SERVER';
    e.config = config;
    return Promise.reject(e);
  };
  instanz.interceptors.response.use(
    (res) => (istApi(res.config) && !(res.headers && res.headers['x-seda24'] === '1') ? keinNetz(res.config, res.status) : res),
    (err) => (err.response && istApi(err.config) && !(err.response.headers && err.response.headers['x-seda24'] === '1')
      ? keinNetz(err.config, err.response.status) : Promise.reject(err)),
  );
}

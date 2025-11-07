// Automatische Erkennung: app.seda.de oder app.seda.de
const hostname = window.location.hostname;
export const API_URL = hostname === 'app.seda.de' 
  ? 'https://app.seda.de/api/v1'
  : 'https://app.seda.de/api/v1';

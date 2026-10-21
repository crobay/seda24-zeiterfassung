const hostname = window.location.hostname;

const API_URLS = {
  'app.seda.de':  'https://app.seda.de/api/v1',
  'dev.seda.de':  'https://dev.seda.de/api/v1',
  'demo.seda.de': 'https://demo.seda.de/api/v1',
};

export const API_URL = API_URLS[hostname] || 'https://dev.seda.de/api/v1';

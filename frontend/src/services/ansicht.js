// Startansicht fuer Admin + Objektleitung (Drazen 23.11.2026): nach dem Login und beim Aufruf von app.seda.de bzw. /admin
// immer das Cockpit - ausser man hat bewusst "Klassische Ansicht" gewaehlt. Die Wahl gilt bis zum Abmelden
// (jeder neue Login startet wieder im Cockpit). Mitarbeiter bleiben bei der Stempeluhr (/dashboard).
const KEY = 'ansicht_klassisch';

export const istLeitung = (role = localStorage.getItem('userRole')) => role === 'admin' || role === 'objektleiter';
export const klassisch = () => localStorage.getItem(KEY) === '1';
export const setKlassisch = (an) => (an ? localStorage.setItem(KEY, '1') : localStorage.removeItem(KEY));
export const leitungStart = () => (klassisch() ? '/admin' : '/cockpit');

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { API_URL } from '../config';
import de from './i18n/de';
import { CheckCircle2, AlertTriangle, Clock, CircleCheckBig, HelpCircle, Bot, CalendarClock, Palmtree, Thermometer, Inbox } from 'lucide-react';

/* ---------- Übersetzung ---------- */
const DICTS = { de };
let lang = 'de';
export function setLang(l) { if (DICTS[l]) lang = l; }
export function t(key, vars) {
  const v = key.split('.').reduce((o, k) => (o ? o[k] : undefined), DICTS[lang]) ?? key.split('.').reduce((o, k) => (o ? o[k] : undefined), de);
  if (typeof v !== 'string') return key;
  return vars ? v.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? '')) : v;
}
export const fmtNum = (n, d = 1) => Number(n || 0).toLocaleString(lang === 'de' ? 'de-DE' : lang, { minimumFractionDigits: d, maximumFractionDigits: d });
export const fmtDate = (iso, opts = { day: '2-digit', month: '2-digit' }) => iso ? new Date(iso + (iso.length === 10 ? 'T12:00:00' : '')).toLocaleDateString('de-DE', opts) : '';

/* ---------- API ---------- */
const token = () => localStorage.getItem('token') || sessionStorage.getItem('token');
export const api = axios.create({ baseURL: `${API_URL}/cockpit` });
api.interceptors.request.use((c) => { const tk = token(); if (tk) c.headers.Authorization = `Bearer ${tk}`; return c; });
export const apiError = (e) => {
  const d = e?.response?.data?.detail;
  return typeof d === 'string' ? d : d?.text || t('app.error');
};

export function useApi(path, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const load = useCallback(() => {
    if (!path) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    api.get(path).then((r) => setState({ data: r.data, loading: false, error: null }))
      .catch((e) => setState({ data: null, loading: false, error: apiError(e), status: e?.response?.status }));
  }, [path]); // eslint-disable-line
  useEffect(load, [load, ...deps]); // eslint-disable-line
  return { ...state, reload: load };
}

/* ---------- App-Kontext: Branding, Theme, Benutzer, Toasts ---------- */
const Ctx = createContext(null);
const THEME_KEY = 'ck_theme_v2';  // neuer Schluessel: alte automatisch gespeicherte Werte gelten nicht mehr

// Branding-Einstellung -> CSS-Variablen; leere Werte = neutrale Vorgaben aus cockpit.css
const BRAND_VARS = { akzent: '--b-akzent', cta: '--b-cta', cta_text: '--b-cta-fg', leiste: '--b-leiste', leiste_text: '--b-leiste-fg' };
// WCAG-Kontrastverhaeltnis zweier #RRGGBB-Farben (null bei ungueltiger Eingabe)
export function contrast(a, b) {
  const lum = (h) => {
    if (!/^#[0-9a-f]{6}$/i.test(h || '')) return null;
    const [r, g, bl] = [1, 3, 5].map((i) => { const c = parseInt(h.slice(i, i + 2), 16) / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const x = lum(a), y = lum(b);
  if (x == null || y == null) return null;
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

export function brandStyle(b) {
  if (!b) return undefined;
  const st = {};
  Object.entries(BRAND_VARS).forEach(([k, v]) => { if (b[k]) st[v] = b[k]; });
  if (b.schrift_text) st['--b-font'] = `'${b.schrift_text}'`;
  if (b.schrift_titel) st['--b-font-head'] = `'${b.schrift_titel}'`;
  return st;
}
export const useApp = () => useContext(Ctx);

export function AppProvider({ children }) {
  const [brand, setBrand] = useState(null);
  const [me, setMe] = useState(null);
  // Standard ist der helle Firmen-Look; dunkel nur, wenn der Benutzer selbst umgeschaltet hat
  const [dark, setDarkState] = useState(() => localStorage.getItem(THEME_KEY) === 'dark');
  const setDark = useCallback((d) => { localStorage.setItem(THEME_KEY, d ? 'dark' : 'light'); setDarkState(d); }, []);
  const [toasts, setToasts] = useState([]);
  const [counts, setCounts] = useState({});
  const timers = useRef({});

  useEffect(() => {  // Schriften des Brandings lokal nachladen (z. B. /brand/seda24/fonts/fonts.css)
    if (!brand?.schrift_css || document.getElementById('ck-brand-fonts')) return;
    const l = document.createElement('link'); l.id = 'ck-brand-fonts'; l.rel = 'stylesheet'; l.href = brand.schrift_css;
    document.head.appendChild(l);
  }, [brand?.schrift_css]);
  const loadBrand = useCallback(() => api.get('/branding').then((r) => { setBrand(r.data); setLang(r.data.sprache || 'de'); }).catch(() => setBrand({ firma: '', akzent: '#2563eb' })), []);
  useEffect(() => { loadBrand(); api.get('/me').then((r) => setMe(r.data)).catch(() => setMe(false)); }, [loadBrand]);

  const dismiss = useCallback((id) => { setToasts((ts) => ts.filter((x) => x.id !== id)); clearTimeout(timers.current[id]); }, []);
  const toast = useCallback((text, { undo, tone } = {}) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((ts) => [...ts.slice(-2), { id, text, undo, tone }]);
    timers.current[id] = setTimeout(() => dismiss(id), undo ? 7000 : 4000);
  }, [dismiss]);

  const value = useMemo(() => ({ brand, setBrand, loadBrand, me, dark, setDark, toast, counts, setCounts }), [brand, me, dark, toast, counts, loadBrand]);
  const style = brandStyle(brand);
  return (
    <Ctx.Provider value={value}>
      <div className={`ck${dark ? ' ck-dark' : ''}`} style={style}>
        {children}
        <div className="ck-toasts" role="status" aria-live="polite">
          {toasts.map((x) => (
            <div key={x.id} className="ck-toast">
              {x.tone === 'warn' ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
              <span>{x.text}</span>
              {x.undo && <button onClick={() => { dismiss(x.id); x.undo(); }}>{t('app.undo')}</button>}
            </div>
          ))}
        </div>
      </div>
    </Ctx.Provider>
  );
}

/* ---------- Status: immer Symbol + Wort ---------- */
const STATUS = {
  da: { tone: 'ok', Icon: CheckCircle2 },
  fertig: { tone: 'done', Icon: CircleCheckBig },
  kommt: { tone: 'info', Icon: Clock },
  fehlt: { tone: 'warn', Icon: AlertTriangle },
  offen: { tone: 'warn', Icon: HelpCircle },
  auto: { tone: 'info', Icon: Bot },
  geplant: { tone: 'info', Icon: CalendarClock },
  urlaub: { tone: 'info', Icon: Palmtree },
  krank: { tone: 'info', Icon: Thermometer },
  aktiv: { tone: 'ok', Icon: CheckCircle2 },
  inaktiv: { tone: 'done', Icon: Clock },
  pending: { tone: 'warn', Icon: HelpCircle },
  approved: { tone: 'ok', Icon: CheckCircle2 },
  rejected: { tone: 'done', Icon: AlertTriangle },
  cancelled: { tone: 'done', Icon: Clock },
  shifted: { tone: 'info', Icon: CalendarClock },
};
export function Status({ s, label }) {
  const def = STATUS[s] || { tone: 'info', Icon: Inbox };
  const { Icon } = def;
  return <span className={`ck-status s-${def.tone}`}><Icon size={16} strokeWidth={2.4} aria-hidden="true" />{label || t(`status.${s}`)}</span>;
}

/* ---------- Bausteine ---------- */
export function Skeleton({ w = '100%', h = 16, r, style }) {
  return <div className="ck-skel" style={{ width: w, height: h, borderRadius: r, ...style }} aria-hidden="true" />;
}
export function SkeletonRows({ n = 4 }) {
  return (
    <div aria-busy="true" aria-label={t('app.loading')}>
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="ck-row" style={{ gap: 16 }}>
          <Skeleton w={52} h={18} />
          <div style={{ flex: 1, display: 'grid', gap: 8 }}><Skeleton w="45%" h={16} /><Skeleton w="70%" h={13} /></div>
          <Skeleton w={96} h={26} r={999} />
        </div>
      ))}
    </div>
  );
}
export function Empty({ icon: Icon = Inbox, title, text, children }) {
  return (
    <div className="ck-empty">
      <div className="ck-empty-icon"><Icon size={24} /></div>
      <b>{title}</b><span>{text}</span>{children}
    </div>
  );
}
export function ErrorBox({ text, onRetry }) {
  return (
    <div className="ck-empty">
      <div className="ck-empty-icon" style={{ background: 'var(--ck-warn-soft)', color: 'var(--ck-warn)' }}><AlertTriangle size={24} /></div>
      <b>{t('app.error')}</b><span>{text}</span>
      {onRetry && <button className="ck-btn" onClick={onRetry}>{t('app.retry')}</button>}
    </div>
  );
}
export function Card({ title, icon: Icon, action, children, style, bodyless }) {
  return (
    <section className="ck-card" style={style}>
      {title && <div className="ck-card-head"><h2>{Icon && <Icon size={20} />}{title}</h2>{action}</div>}
      {bodyless ? children : <div className="ck-card-body">{children}</div>}
    </section>
  );
}
export function Dialog({ title, children, onClose, footer }) {
  useEffect(() => {
    const k = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k);
  }, [onClose]);
  return (
    <div className="ck-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="ck-dialog" role="dialog" aria-modal="true" aria-label={title}>
        <div className="ck-card-head"><h2>{title}</h2></div>
        <div className="ck-dialog-body">{children}</div>
        {footer && <div className="ck-dialog-foot">{footer}</div>}
      </div>
    </div>
  );
}
export const initials = (name = '') => name.split(' ').filter(Boolean).map((p) => p[0]).slice(0, 2).join('').toUpperCase();

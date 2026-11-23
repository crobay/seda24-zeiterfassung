import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Sun, CalendarDays, CalendarCog, Users, Building2, Clock3, Wallet, ClipboardCheck, Settings, Package, Search, Moon, LogOut, LayoutGrid, User, CornerDownLeft } from 'lucide-react';
import { api, t, useApp, initials, ObjektMarke } from './core';
import { setKlassisch } from '../services/ansicht';

export const NAV = [
  { key: 'heute', path: '/cockpit', Icon: Sun },
  { key: 'dienstplan', path: '/cockpit/dienstplan', Icon: CalendarDays },
  { key: 'vorlage', path: '/cockpit/vorlage', Icon: CalendarCog },
  { key: 'mitarbeiter', path: '/cockpit/mitarbeiter', Icon: Users },
  { key: 'objekte', path: '/cockpit/objekte', Icon: Building2 },
  { key: 'zeiten', path: '/cockpit/zeiten', Icon: Clock3 },
  { key: 'abrechnung', path: '/cockpit/abrechnung', Icon: Wallet, right: 'verwalten' },
  { key: 'abschluss', path: '/cockpit/abschluss', Icon: ClipboardCheck, right: 'abschluss' },
  { key: 'material', path: '/cockpit/material', Icon: Package, right: 'material' },
  { key: 'einstellungen', path: '/cockpit/einstellungen', Icon: Settings, right: 'verwalten' },
];
const MOBILE = ['heute', 'dienstplan', 'mitarbeiter', 'zeiten'];

export function isActive(path, loc) {
  return path === '/cockpit' ? loc === '/cockpit' || loc === '/cockpit/' : loc.startsWith(path);
}

export default function Shell({ children }) {
  const { brand, me, dark, setDark, counts } = useApp();
  const nav = useNavigate();
  const loc = useLocation().pathname;
  const [cmd, setCmd] = useState(false);
  const [more, setMore] = useState(false);
  const items = NAV.filter((n) => !n.right || me?.rechte?.[n.right]);

  useEffect(() => {
    const k = (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setCmd((c) => !c); } };
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k);
  }, []);
  useEffect(() => { setMore(false); }, [loc]);
  useEffect(() => { if (brand) document.title = `${brand.firma} · ${t('app.subtitle')}`; }, [brand]);

  const logout = () => { ['token'].forEach((k) => { localStorage.removeItem(k); sessionStorage.removeItem(k); }); setKlassisch(false); nav('/login'); };
  const go = (p) => nav(p);
  // Mit Logo (Wortmarke aus dem Branding): Logo in voller Breite; ohne Logo: Buchstaben-Quadrat + Firmenname
  const Brand = brand?.logo_url ? (
    <div className="ck-brand-mark">
      <img src={brand.logo_url} alt={brand.firma || ''} />
      <span>{brand.produkt} {t('app.subtitle')}</span>
    </div>
  ) : (
    <div className="ck-brand">
      <div className="ck-logo">{(brand?.firma || ' ').slice(0, 1)}</div>
      <div><b>{brand?.firma}</b><span>{brand?.produkt} {t('app.subtitle')}</span></div>
    </div>
  );
  const TopLogo = (
    <a className="ck-topbar-logo" href="/cockpit" onClick={(e) => { e.preventDefault(); go('/cockpit'); }} aria-label={t('nav.heute')}>
      {brand?.logo_url ? <img src={brand.logo_url} alt={brand.firma || ''} /> : <span className="ck-logo">{(brand?.firma || ' ').slice(0, 1)}</span>}
    </a>
  );

  return (
    <div className="ck-shell">
      <aside className="ck-sidebar" aria-label="Navigation">
        {Brand}
        {items.map(({ key, path, Icon }) => (
          <button key={key} className={`ck-nav-item${isActive(path, loc) ? ' is-active' : ''}`} onClick={() => go(path)}
            aria-current={isActive(path, loc) ? 'page' : undefined}>
            <Icon size={20} />{t(`nav.${key}`)}
            {key === 'heute' && counts.offen > 0 && <span className="ck-nav-count">{counts.offen}</span>}
          </button>
        ))}
        <div className="ck-sidebar-foot">
          <button className="ck-nav-item" onClick={() => setDark(!dark)}>{dark ? <Sun size={20} /> : <Moon size={20} />}{dark ? t('app.theme_light') : t('app.theme_dark')}</button>
          <button className="ck-nav-item" onClick={() => nav('/dashboard')} data-stempeln><Clock3 size={20} />{t('app.stempeln')}</button>
          <a className="ck-nav-item" href="/admin?klassisch=1" data-klassisch><LayoutGrid size={20} />{t('app.classic')}</a>
          <button className="ck-nav-item" onClick={logout}><LogOut size={20} />{t('app.logout')}</button>
        </div>
      </aside>

      <div className="ck-main">
        <header className="ck-topbar">
          {TopLogo}
          <button className="ck-search" onClick={() => setCmd(true)} aria-label={t('app.search')}>
            <Search size={18} /><span className="ck-search-long">{t('app.search')}</span><span className="ck-search-short">{t('app.searchShort')}</span><span className="ck-kbd">Strg K</span>
          </button>
          <div className="ck-topbar-right">
            <button className="ck-btn ck-btn-ghost ck-btn-icon" onClick={() => setDark(!dark)} aria-label={dark ? t('app.theme_light') : t('app.theme_dark')}>
              {dark ? <Sun size={19} /> : <Moon size={19} />}
            </button>
            <div style={{ textAlign: 'right', lineHeight: 1.2 }} className="ck-hide-sm">
              <div style={{ fontWeight: 600, fontSize: 15 }}>{me?.name}</div>
              <div className="ck-subtle">{me ? t(`app.role_${me.role}`) : ''}</div>
            </div>
            <div className="ck-avatar" aria-hidden="true">{initials(me?.name)}</div>
          </div>
        </header>
        <main className="ck-content" key={loc}>{children}</main>
      </div>

      <nav className="ck-bottomnav" aria-label="Navigation">
        {items.filter((n) => MOBILE.includes(n.key)).map(({ key, path, Icon }) => (
          <button key={key} className={isActive(path, loc) ? 'is-active' : ''} onClick={() => go(path)}>
            <Icon size={22} />{t(`nav.${key}`)}
            {key === 'heute' && counts.offen > 0 && <span className="ck-nav-count">{counts.offen}</span>}
          </button>
        ))}
        <button className={more ? 'is-active' : ''} onClick={() => setMore(!more)}><User size={22} />{t('app.more')}</button>
      </nav>
      {more && (
        <div className="ck-overlay" style={{ alignItems: 'flex-end', padding: 0 }} onMouseDown={(e) => e.target === e.currentTarget && setMore(false)}>
          <div className="ck-dialog" style={{ maxWidth: 'none', borderRadius: '16px 16px 0 0', paddingBottom: 72 }}>
            <div style={{ padding: 12 }}>{Brand}
              {items.filter((n) => !MOBILE.includes(n.key)).map(({ key, path, Icon }) => (
                <button key={key} className="ck-nav-item" onClick={() => go(path)}><Icon size={20} />{t(`nav.${key}`)}</button>))}
              <button className="ck-nav-item" onClick={() => setDark(!dark)}>{dark ? <Sun size={20} /> : <Moon size={20} />}{dark ? t('app.theme_light') : t('app.theme_dark')}</button>
              <button className="ck-nav-item" onClick={() => nav('/dashboard')} data-stempeln><Clock3 size={20} />{t('app.stempeln')}</button>
          <a className="ck-nav-item" href="/admin?klassisch=1" data-klassisch><LayoutGrid size={20} />{t('app.classic')}</a>
              <button className="ck-nav-item" onClick={logout}><LogOut size={20} />{t('app.logout')}</button>
            </div>
          </div>
        </div>
      )}
      {cmd && <CommandPalette onClose={() => setCmd(false)} items={items} />}
    </div>
  );
}

function CommandPalette({ onClose, items }) {
  const { dark, setDark } = useApp();
  const nav = useNavigate();
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const [data, setData] = useState({ ma: [], obj: [] });
  const inp = useRef(null);
  useEffect(() => {
    inp.current?.focus();
    Promise.all([api.get('/mitarbeiter'), api.get('/objekte')])
      .then(([m, o]) => setData({ ma: m.data, obj: o.data })).catch(() => {});
  }, []);
  const results = useMemo(() => {
    const s = q.trim().toLowerCase();
    const hit = (txt) => !s || txt.toLowerCase().includes(s);
    const out = [];
    items.forEach((n) => hit(t(`nav.${n.key}`)) && out.push({ g: 'pages', label: t(`nav.${n.key}`), Icon: n.Icon, run: () => nav(n.path) }));
    if (hit(t('cmd.toggle_theme'))) out.push({ g: 'actions', label: t('cmd.toggle_theme'), Icon: dark ? Sun : Moon, run: () => setDark(!dark) });
    data.ma.filter((m) => hit(`${m.first_name} ${m.last_name} ${m.personal_nr}`)).slice(0, s ? 8 : 4)
      .forEach((m) => out.push({ g: 'employees', label: `${m.first_name} ${m.last_name}`, hint: m.personal_nr, Icon: User, run: () => nav(`/cockpit/mitarbeiter/${m.id}`) }));
    data.obj.filter((o) => hit(`${o.name} ${o.kunde || ''}`)).slice(0, s ? 8 : 3)
      .forEach((o) => out.push({ g: 'objects', label: o.name, hint: o.kunde, Icon: Building2, objektId: o.id, run: () => nav(`/cockpit/objekte#o${o.id}`) }));
    return out;
  }, [q, data, items, dark, nav, setDark]);
  useEffect(() => setSel(0), [q]);
  const run = (r) => { onClose(); r.run(); };
  const key = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel((x) => Math.min(x + 1, results.length - 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSel((x) => Math.max(x - 1, 0)); }
    if (e.key === 'Enter' && results[sel]) run(results[sel]);
    if (e.key === 'Escape') onClose();
  };
  let last = null;
  return (
    <div className="ck-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="ck-dialog ck-cmd" role="dialog" aria-modal="true" aria-label={t('app.search')}>
        <div className="ck-cmd-input"><Search size={20} />
          <input ref={inp} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={key} placeholder={t('cmd.placeholder')} aria-label={t('cmd.placeholder')} />
          <span className="ck-kbd">Esc</span></div>
        <div className="ck-cmd-list" role="listbox">
          {results.length === 0 && <div className="ck-empty" style={{ padding: 24 }}>{t('cmd.none', { q })}</div>}
          {results.map((r, i) => {
            const head = r.g !== last ? <div className="ck-cmd-group">{t(`cmd.${r.g}`)}</div> : null; last = r.g;
            return (<React.Fragment key={i}>{head}
              <div role="option" aria-selected={i === sel} className={`ck-cmd-item${i === sel ? ' is-sel' : ''}`} onMouseEnter={() => setSel(i)} onClick={() => run(r)}>
                {r.objektId ? <ObjektMarke id={r.objektId} name={r.label} ohneName /> : <r.Icon size={18} />}{r.label}{r.hint ? <small>{r.hint}</small> : i === sel ? <small><CornerDownLeft size={14} /></small> : null}
              </div></React.Fragment>);
          })}
        </div>
      </div>
    </div>
  );
}

import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  UserCheck, UserX, ListChecks, Timer, Inbox, CalendarCheck2, PartyPopper, Check, X, MessageSquare, Palmtree, Thermometer,
  Building2, CalendarRange, AlertTriangle, ChevronRight, FileCheck2, CheckCircle2, Car, TrendingUp, TrendingDown, Minus,
  Activity, LogIn, LogOut, Bot, Pencil, ArrowRightLeft, Clock, CircleCheckBig, Moon as MoonIcon,
} from 'lucide-react';
import { api, apiError, t, fmtNum, fmtDate, useApi, useApp, Status, SkeletonRows, Skeleton, Empty, ErrorBox, Dialog } from '../core';

const greet = () => { const h = new Date().getHours(); return t(h < 11 ? 'greet.morning' : h < 18 ? 'greet.day' : 'greet.evening'); };
const ATTENTION = ['fehlt', 'offen'];
const ITEM_ICON = { genehmigung: CalendarCheck2, nachtrag: CalendarCheck2, urlaub: Palmtree, schichtwunsch: ArrowRightLeft, nachricht: MessageSquare };
const monthName = () => new Date().toLocaleDateString('de-DE', { month: 'long' });

export default function Heute() {
  const { me, toast, setCounts } = useApp();
  const heute = useApi('/heute');
  const ls = useApi('/leitstelle');
  const objs = useApi('/objekte');
  const [busy, setBusy] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [hidden, setHidden] = useState(() => new Set());
  const data = heute.data;
  const reloadAll = () => { heute.reload(); ls.reload(); };
  useEffect(() => { if (data) setCounts((c) => ({ ...c, offen: data.offen.length })); }, [data, setCounts]);
  useEffect(() => { const i = setInterval(reloadAll, 60000); return () => clearInterval(i); }, []); // eslint-disable-line

  const k = data?.kennzahlen;
  const dateText = new Date().toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' });

  const run = async (item, aktion, text) => {
    setBusy(`${item.typ}${item.id}`);
    try {
      await api.post(`/aktion/${item.typ}/${item.id}`, { aktion, text });
      setHidden((h) => new Set(h).add(`${item.typ}${item.id}`));
      const undo = aktion === 'gelesen' ? async () => {
        await api.post(`/aktion/nachricht/${item.id}`, { aktion: 'ungelesen' });
        setHidden((h) => { const n = new Set(h); n.delete(`${item.typ}${item.id}`); return n; });
        reloadAll();
      } : undefined;
      toast(t(`act.done_${aktion}`, { what: t(`item.${item.typ}`), name: item.name }), { undo });
      reloadAll();
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(null); setDialog(null);
  };

  const offen = (data?.offen || []).filter((i) => !hidden.has(`${i.typ}${i.id}`));
  const shifts = data?.schichten || [];
  const attention = shifts.filter((s) => ATTENTION.includes(s.status));
  const rest = shifts.filter((s) => !ATTENTION.includes(s.status));

  if (heute.error) return <div className="ck-card"><ErrorBox text={heute.error} onRetry={heute.reload} /></div>;

  return (
    <>
      <div className="ck-page-head">
        <div>
          <h1>{greet()}{me?.name ? `, ${me.name.split(' ')[0]}` : ''}</h1>
          <p>{dateText}{data ? ` · Stand ${data.uhrzeit} Uhr` : ''}</p>
        </div>
      </div>

      <div className="ck-kpis">
        <Kpi tone="ok" Icon={UserCheck} label={t('heute.kpi_present')} value={k?.anwesend} sub={k && t('heute.kpi_present_sub', { n: k.geplant })} href="#schichten" />
        <Kpi tone="warn" alert={k?.fehlt > 0} Icon={UserX} label={t('heute.kpi_missing')} value={k?.fehlt}
          sub={k && (k.fehlt ? t('heute.kpi_missing_sub') : t('heute.kpi_missing_none'))} href="#schichten" />
        <Kpi tone="accent" Icon={ListChecks} label={t('heute.kpi_open')} value={k ? offen.length : undefined} sub={t('heute.kpi_open_sub')} href="#todo" />
        <Kpi tone="info" Icon={Timer} label={t('heute.kpi_hours', { month: monthName() })} value={k && fmtNum(k.stunden_monat, 0)} sub={k && t('heute.kpi_hours_sub', { n: k.einsaetze_monat })} to="/cockpit/zeiten?range=month" />
      </div>

      <div className="ck-dash">
        {/* Handlungsliste */}
        <section className="ck-card span-7 m1" id="todo" aria-labelledby="todo-h">
          <div className="ck-card-head"><h2 id="todo-h"><ListChecks size={20} />{t('heute.todo')}</h2>
            {offen.length > 0 && <span className="ck-tag">{offen.length}</span>}</div>
          {!data ? <SkeletonRows n={3} /> : offen.length === 0 ? (
            <Empty icon={PartyPopper} title={t('heute.todo_empty_title')} text={t('heute.todo_empty')} />
          ) : (
            <ul className="ck-list">
              {offen.map((i) => {
                const Icon = ITEM_ICON[i.typ] || Inbox;
                const b = busy === `${i.typ}${i.id}`;
                return (
                  <li key={`${i.typ}${i.id}`} className="ck-row">
                    <div className="ck-kpi-icon" style={{ background: 'var(--ck-accent-soft)', color: 'var(--ck-accent-ink)', flex: 'none' }}><Icon size={18} /></div>
                    <div className="ck-row-main">
                      <div className="ck-row-title"><Link to={`/cockpit/mitarbeiter/${i.employee_id}`}>{i.name}</Link><span className="ck-tag">{t(`item.${i.typ}`)}</span></div>
                      <div className="ck-row-meta">{i.text}</div>
                    </div>
                    <div className="ck-row-actions">
                      {i.typ === 'nachricht' ? (<>
                        <button className="ck-btn ck-btn-primary ck-btn-sm" disabled={b} onClick={() => setDialog({ item: i, aktion: 'antworten' })}><MessageSquare size={16} />{t('act.antworten')}</button>
                        <button className="ck-btn ck-btn-sm" disabled={b} onClick={() => run(i, 'gelesen')}><Check size={16} />{t('act.gelesen')}</button>
                      </>) : (<>
                        <button className="ck-btn ck-btn-primary ck-btn-sm" disabled={b} onClick={() => run(i, 'genehmigen')}><Check size={16} />{t('act.genehmigen')}</button>
                        <button className="ck-btn ck-btn-sm" disabled={b} onClick={() => setDialog({ item: i, aktion: 'ablehnen' })}><X size={16} />{t('act.ablehnen')}</button>
                      </>)}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Monatsabschluss */}
        <Abschluss a={ls.data?.abschluss} className="span-5 m6" />

        {/* Objekte heute */}
        <ObjekteHeute shifts={shifts} objs={objs.data} loading={!data || !objs.data} className="span-12 m3" />

        {/* Schichten heute */}
        <section className="ck-card span-7 m2" id="schichten" aria-labelledby="sch-h">
          <div className="ck-card-head"><h2 id="sch-h"><CalendarCheck2 size={20} />{t('heute.shifts')}</h2>
            <Link className="ck-link-more" to="/cockpit/dienstplan">{t('nav.dienstplan')}<ChevronRight size={16} /></Link></div>
          {!data ? <SkeletonRows n={4} /> : shifts.length === 0 && !data.ohne_schicht.length ? (
            <Empty icon={CalendarCheck2} title={t('heute.shifts_empty_title')} text={t('heute.shifts_empty')} />
          ) : (<>
            {attention.length > 0 && <div className="ck-section-title">{t('heute.attention')}</div>}
            <ul className="ck-list">{attention.map((s) => <ShiftRow key={s.schicht_id} s={s} />)}</ul>
            {attention.length > 0 && rest.length > 0 && <div className="ck-section-title">{t('heute.later')}</div>}
            <ul className="ck-list">{rest.map((s) => <ShiftRow key={s.schicht_id} s={s} />)}</ul>
            {data.ohne_schicht.length > 0 && <>
              <div className="ck-section-title">{t('heute.unplanned')}</div>
              <ul className="ck-list">{data.ohne_schicht.map((s) => (
                <li key={s.eintrag_id} className="ck-row"><span className="ck-row-time">{s.seit}</span>
                  <div className="ck-row-main"><div className="ck-row-title"><Link to={`/cockpit/mitarbeiter/${s.employee_id}`}>{s.name}</Link></div>
                    <div className="ck-row-meta">{s.objekt || '–'}</div></div>
                  <Link to={`/cockpit/zeiten?eintrag=${s.eintrag_id}`}><Status s={s.status} /></Link></li>))}</ul></>}
          </>)}
        </section>

        <div className="ck-stack span-5 m5">
          <Abwesend heute={data?.abwesend} woche={ls.data?.woche} />
          <Kilometer km={ls.data?.km} />
        </div>

        {/* Woche */}
        <Woche woche={ls.data?.woche} className="span-12 m4" />

        <StundenSollIst rows={ls.data?.stunden} className="span-7 m7" />
        <Feed feed={ls.data?.feed} className="span-5 m8" />
      </div>

      {dialog && <ActionDialog {...dialog} busy={!!busy} onClose={() => setDialog(null)} onRun={(text) => run(dialog.item, dialog.aktion, text)} />}
    </>
  );
}

function Kpi({ tone, Icon, label, value, sub, href, to, alert }) {
  const inner = (<>
    <div className="ck-kpi-label"><span className="ck-kpi-icon"><Icon size={18} /></span>{label}</div>
    <div className="ck-kpi-value ck-num">{value === undefined || value === null ? <Skeleton w={64} h={34} /> : value}</div>
    <div className="ck-kpi-sub">{sub ?? <Skeleton w="60%" h={13} />}</div>
  </>);
  const cls = `ck-card ck-kpi tone-${tone}${alert ? ' is-alert' : ''}`;
  return to ? <Link className={cls} to={to}>{inner}</Link> : <a className={cls} href={href}>{inner}</a>;
}

function ShiftRow({ s }) {
  const long = ['da', 'fertig', 'fehlt'].includes(s.status);
  return (
    <li className={`ck-row ck-shift-row${ATTENTION.includes(s.status) ? ' is-warn' : ''}`}>
      <span className="ck-row-time">{s.beginn}</span>
      <div className="ck-row-main">
        <div className="ck-row-title"><Link to={`/cockpit/mitarbeiter/${s.employee_id}`}>{s.name}</Link></div>
        <div className="ck-row-meta"><Link className="ck-link" to={`/cockpit/objekte/${s.object_id}`}>{s.objekt}</Link> · {s.beginn}–{s.ende}
          <span className="ck-tag" title={t(`kat.${s.kategorie}`)}>{t(`kat.${s.kategorie}`).split(' · ')[1]}</span></div>
      </div>
      <Link className="ck-shift-status" to={s.eintrag_id ? `/cockpit/zeiten?eintrag=${s.eintrag_id}` : `/cockpit/zeiten?neu=${s.schicht_id}`}
        title={s.eintrag_id ? t('zeiten.edit') : t('zeiten.add_for_shift')}>
        <Status s={s.status} label={long ? s.status_text : undefined} />
      </Link>
    </li>
  );
}

/* 1) Objekte-Übersicht als Kacheln */
const OBJ_STATUS = {
  offen: { s: 'fehlt', key: 'st_offen' }, besetzt: { s: 'da', key: 'st_besetzt' }, kommt: { s: 'kommt', key: 'st_kommt' },
  fertig: { s: 'fertig', key: 'st_fertig' }, frei: { s: 'inaktiv', key: 'st_frei' },
};
function ObjekteHeute({ shifts, objs, loading, className }) {
  const tiles = useMemo(() => {
    if (!objs) return [];
    const by = {};
    shifts.forEach((s) => { (by[s.object_id] = by[s.object_id] || []).push(s); });
    return objs.filter((o) => o.is_active).map((o) => {
      const ss = by[o.id] || [];
      const n = (st) => ss.filter((x) => st.includes(x.status)).length;
      const c = { offen: n(['fehlt', 'offen']), besetzt: n(['da']), fertig: n(['fertig']), kommt: n(['kommt', 'geplant', 'auto']) };
      const main = !ss.length ? 'frei' : c.offen ? 'offen' : c.besetzt ? 'besetzt' : c.kommt ? 'kommt' : 'fertig';
      return { ...o, ss, c, main };
    }).sort((a, b) => ['offen', 'besetzt', 'kommt', 'fertig', 'frei'].indexOf(a.main) - ['offen', 'besetzt', 'kommt', 'fertig', 'frei'].indexOf(b.main) || a.name.localeCompare(b.name));
  }, [shifts, objs]);
  return (
    <section className={`ck-card ${className}`} aria-labelledby="obj-h">
      <div className="ck-card-head"><h2 id="obj-h"><Building2 size={20} />{t('ls.objects')}</h2>
        <Link className="ck-link-more" to="/cockpit/objekte">{t('ls.objects_all')}<ChevronRight size={16} /></Link></div>
      {loading ? <div className="ck-objgrid">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} h={92} r={10} />)}</div> : (
        <>
        <div className="ck-objgrid">
          {tiles.filter((o) => o.main !== 'frei').map((o) => (
            <Link key={o.id} to={`/cockpit/objekte/${o.id}`} className={`ck-objtile${o.main === 'offen' ? ' is-warn' : ''}`}>
              <b>{o.name}</b>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {['offen', 'besetzt', 'kommt', 'fertig'].filter((x) => o.c[x]).map((x) => (
                  <Status key={x} s={OBJ_STATUS[x].s} label={`${o.c[x]} ${t(`ls.${OBJ_STATUS[x].key}`)}`} />))}
              </div>
              <div className="ck-objtile-meta">
                <span>{o.ss.length === 1 ? t('ls.obj_shift') : t('ls.obj_shifts', { n: o.ss.length })}</span>
                <span className="ck-num">{o.ss.map((s) => s.beginn).sort()[0]}–{o.ss.map((s) => s.ende).sort().slice(-1)[0]}</span>
              </div>
            </Link>
          ))}
        </div>
        {tiles.some((o) => o.main === 'frei') && (
          <div style={{ padding: '0 20px 18px', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <span className="ck-mini m-info" style={{ marginRight: 4 }}><MoonIcon size={14} />{t('ls.idle_list')}</span>
            {tiles.filter((o) => o.main === 'frei').map((o) => <Link key={o.id} to={`/cockpit/objekte/${o.id}`} className="ck-tag" style={{ textDecoration: 'none' }}>{o.name}</Link>)}
          </div>
        )}
        </>
      )}
    </section>
  );
}

/* 2) Wochenleiste */
function Woche({ woche, className }) {
  const gaps = (woche || []).flatMap((d) => d.luecken.map((l) => ({ ...l, datum: d.datum, tag: d.tag })));
  return (
    <section className={`ck-card ${className}`} aria-labelledby="wo-h">
      <div className="ck-card-head"><h2 id="wo-h"><CalendarRange size={20} />{t('ls.week')}</h2>
        <Link className="ck-link-more" to="/cockpit/dienstplan">{t('ls.week_plan')}<ChevronRight size={16} /></Link></div>
      <div className="ck-weekstrip">
        {!woche ? Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} h={132} r={10} />) : woche.map((d, i) => (
          <Link key={d.datum} to={`/cockpit/dienstplan?start=${d.datum}&tag=${d.datum}`} className={`ck-wday${i === 0 ? ' is-today' : ''}`}>
            <div className="ck-wday-head"><b>{i === 0 ? t('nav.heute') : d.tag}</b><span>{fmtDate(d.datum)}</span></div>
            <div className="ck-wday-n ck-num">{d.schichten}<small>{t('ls.shifts')}</small></div>
            {d.luecken.length ? <span className="ck-mini m-warn"><AlertTriangle size={14} />{d.luecken.length === 1 ? t('ls.gap') : t('ls.gaps', { n: d.luecken.length })}</span>
              : <span className="ck-mini m-ok"><CheckCircle2 size={14} />{t('ls.no_gaps')}</span>}
            {d.urlaub.length > 0 && <span className="ck-mini m-info"><Palmtree size={14} />{t('ls.vac', { n: d.urlaub.length })}</span>}
            {d.krank.length > 0 && <span className="ck-mini m-info"><Thermometer size={14} />{t('ls.sick', { n: d.krank.length })}</span>}
          </Link>
        ))}
      </div>
      {woche && (
        <div className="ck-gaplist">
          <div className="ck-section-title">{t('ls.gaps_title')}</div>
          {gaps.length === 0 ? <div className="ck-subtle" style={{ padding: '0 20px 16px' }}>{t('ls.gaps_none')}</div> : (
            <ul className="ck-list">{gaps.map((g, i) => (
              <li key={i} className="ck-row is-warn">
                <span className="ck-row-time" style={{ minWidth: 76 }}>{g.tag} {fmtDate(g.datum)}</span>
                <div className="ck-row-main"><div className="ck-row-title" style={{ fontWeight: 550 }}>{g.text}</div></div>
                <Link className="ck-btn ck-btn-sm" to={`/cockpit/dienstplan?start=${g.datum}&tag=${g.datum}&objekt=${g.object_id}`}><Pencil size={15} />{t('dienstplan.plan_now')}</Link>
              </li>))}</ul>)}
        </div>
      )}
    </section>
  );
}

/* 3) Monatsabschluss */
function Abschluss({ a, className }) {
  const month = monthName();
  const pct = a && a.ma_gesamt ? Math.round((a.ma_bestaetigt / a.ma_gesamt) * 100) : 0;
  return (
    <section className={`ck-card ${className}`} aria-labelledby="ab-h">
      <div className="ck-card-head"><h2 id="ab-h"><FileCheck2 size={20} />{t('ls.close', { month })}</h2></div>
      {!a ? <SkeletonRows n={4} /> : (<>
        <div className="ck-card-body" style={{ display: 'grid', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
            <span className="ck-big ck-num">{a.tage_bis_export}</span>
            <div><div style={{ fontWeight: 650 }}>{a.tage_bis_export === 0 ? t('ls.export_today') : t('ls.export_in', { n: a.tage_bis_export })}</div>
              <div className="ck-subtle">{t('ls.export_on', { date: fmtDate(a.exporttag, { weekday: 'short', day: '2-digit', month: '2-digit' }) })}</div></div>
          </div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 15 }}>
              <span style={{ fontWeight: 600 }}>{t('ls.confirmed')}</span><span className="ck-num ck-muted">{t('ls.confirmed_of', { n: a.ma_bestaetigt, m: a.ma_gesamt })}</span></div>
            <div className="ck-progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${pct}%` }} /></div>
          </div>
        </div>
        <div className="ck-section-title" style={{ paddingTop: 0 }}>{t('ls.checks')}</div>
        <ul className="ck-checks">
          {a.pruefpunkte.map((p) => (
            <li key={p.key}><Link to={p.link} className={`ck-check${p.n ? '' : ' is-ok'}`}>
              {p.n ? <AlertTriangle size={18} color="var(--ck-warn)" /> : <CheckCircle2 size={18} color="var(--ck-ok)" />}
              <span style={{ fontWeight: p.n ? 600 : 500 }}>{t(`ls.chk_${p.key}`)}</span>
              <span className="ck-check-n">{p.n ? p.n : t('ls.chk_ok')}</span><ChevronRight size={16} />
            </Link></li>))}
        </ul>
        {a.offen_gesamt === 0 && <div className="ck-callout c-info" style={{ margin: 16 }}><CheckCircle2 size={18} />{t('ls.checks_ok')}</div>}
      </>)}
    </section>
  );
}

/* 4) Stunden Soll/Ist + KM */
function StundenSollIst({ rows, className }) {
  const max = Math.max(1, ...(rows || []).map((r) => Math.max(r.soll, r.ist)));
  return (
    <section className={`ck-card ${className}`} aria-labelledby="st-h">
      <div className="ck-card-head"><h2 id="st-h"><Timer size={20} />{t('ls.hours', { month: monthName() })}</h2>
        <Link className="ck-link-more" to="/cockpit/zeiten?range=month">{t('nav.zeiten')}<ChevronRight size={16} /></Link></div>
      {!rows ? <SkeletonRows n={5} /> : rows.length === 0 ? <Empty icon={Timer} title={t('ls.hours_empty')} text="" /> : (<>
        <div className="ck-bars">
          {rows.map((r) => {
            const diff = r.ist - r.soll_bis_heute;
            const st = Math.abs(diff) <= 1 ? 'in' : diff < 0 ? 'under' : 'over';
            const Icon = st === 'in' ? CheckCircle2 : st === 'under' ? TrendingDown : TrendingUp;
            return (
              <Link key={r.employee_id} to={`/cockpit/mitarbeiter/${r.employee_id}`} className="ck-bar-row" title={`${r.name}: ${t('ls.hours_ist')} ${fmtNum(r.ist)} h · ${t('ls.hours_soll')} ${fmtNum(r.soll_bis_heute)} h · ${t('ls.hours_plan', { h: fmtNum(r.soll) })}`}>
                <span className="ck-bar-name">{r.name}</span>
                <div className="ck-bar" aria-hidden="true">
                  <i className={r.ist > r.soll_bis_heute + 1 ? 'over' : ''} style={{ width: `${(Math.min(r.ist, max) / max) * 100}%` }} />
                  <s style={{ left: `calc(${(r.soll_bis_heute / max) * 100}% - 1px)` }} />
                  <s style={{ left: `calc(${(r.soll / max) * 100}% - 1px)`, opacity: .3 }} />
                </div>
                <span className="ck-bar-val"><b>{fmtNum(r.ist)}</b> / {fmtNum(r.soll_bis_heute)} h{' '}
                  <span className={`ck-mini ${st === 'under' ? 'm-warn' : st === 'over' ? 'm-ok' : 'm-info'}`}><Icon size={14} />{t(`ls.hours_${st}`)}</span></span>
              </Link>
            );
          })}
        </div>
        <div className="ck-legend"><span><i />{t('ls.hours_ist')}</span><span><s />{t('ls.hours_soll')}</span><span><s style={{ opacity: .3 }} />{t('ls.hours_plan', { h: '' }).replace(' h', '')}</span></div>
      </>)}
    </section>
  );
}

function Kilometer({ km }) {
  const month = monthName();
  const max = km ? Math.max(km.km, km.vormonat_gleicher_zeitraum, km.vormonat_gesamt, 1) : 1;
  const tr = km?.trend_prozent;
  const TIcon = tr == null || tr === 0 ? Minus : tr > 0 ? TrendingUp : TrendingDown;
  return (
    <section className="ck-card" aria-labelledby="km-h">
      <div className="ck-card-head"><h2 id="km-h"><Car size={20} />{t('ls.km', { month })}</h2>
        <Link className="ck-link-more" to="/cockpit/einstellungen?tab=km">{t('set.km')}<ChevronRight size={16} /></Link></div>
      <div className="ck-card-body" style={{ display: 'grid', gap: 14 }}>
        {!km ? <SkeletonRows n={2} /> : (<>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <span className="ck-big ck-num">{fmtNum(km.km, 0)}<span style={{ fontSize: 18, fontWeight: 600, marginLeft: 4 }}>km</span></span>
            <span className={`ck-trend ${tr > 0 ? 't-up' : tr < 0 ? 't-down' : ''}`}><TIcon size={15} />{tr == null || tr === 0 ? t('ls.km_flat') : `${tr > 0 ? '+' : ''}${tr} %`}</span>
          </div>
          <div className="ck-subtle" style={{ marginTop: -8 }}>{t('ls.km_money', { eur: fmtNum(km.eur, 2) })} · {tr != null ? t('ls.km_vs') : ''}</div>
          <div className="ck-cmp">
            {[[t('ls.km_this'), km.km, 1], [t('ls.km_prev_same', { d: new Date().getDate() }), km.vormonat_gleicher_zeitraum, .45], [t('ls.km_prev_full'), km.vormonat_gesamt, .25]].map(([l, v, op]) => (
              <div key={l} className="ck-cmp-row"><span className="ck-muted">{l}</span>
                <div className="ck-bar"><i style={{ width: `${(v / max) * 100}%`, opacity: op }} /></div><span className="ck-num" style={{ textAlign: 'right' }}>{fmtNum(v, 0)} km</span></div>))}
          </div>
        </>)}
      </div>
    </section>
  );
}

/* 5) Live-Aktivität */
const FEED_ICON = { kommen: [LogIn, 'f-in'], gehen: [LogOut, ''], auto: [Bot, ''], aenderung: [Pencil, 'f-edit'] };
function when(iso) {
  const d = new Date(iso); const now = new Date(); const min = Math.round((now - d) / 60000);
  if (min < 1) return t('ls.now');
  if (min < 60) return t('ls.min_ago', { n: min });
  const hm = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === now.toDateString()) return hm;
  const y = new Date(now); y.setDate(now.getDate() - 1);
  return d.toDateString() === y.toDateString() ? `${t('ls.yesterday')} ${hm}` : `${fmtDate(iso.slice(0, 10))} ${hm}`;
}
const ACTION_TXT = { booking_created: 'Buchung angelegt', booking_updated: 'Buchung geändert', booking_deleted: 'Buchung gelöscht', push_confirmed: 'Schicht bestätigt',
  schedule_created: 'Schicht angelegt', schedule_updated: 'Schicht geändert', schedule_deleted: 'Schicht gelöscht', schedule_copied: 'Woche kopiert',
  booking_approved: 'Antrag genehmigt', export_quittung: 'Export in Q: bestätigt', km_distance_created: 'KM-Strecke hinterlegt', assignment_created: 'Objekt zugeteilt',
  password_changed: 'Passwort geändert', employee_updated: 'Stammdaten geändert', message_status_changed: 'Nachricht bearbeitet', branding_updated: 'Branding geändert' };
function Feed({ feed, className }) {
  return (
    <section className={`ck-card ${className}`} aria-labelledby="fe-h">
      <div className="ck-card-head"><h2 id="fe-h"><Activity size={20} />{t('ls.feed')}</h2>
        <Link className="ck-link-more" to="/cockpit/einstellungen?tab=audit">{t('set.audit')}<ChevronRight size={16} /></Link></div>
      {!feed ? <SkeletonRows n={5} /> : feed.length === 0 ? <Empty icon={Activity} title={t('ls.feed_empty')} text="" /> : (
        <ul className="ck-feed">{feed.map((f, i) => {
          const [Icon, cls] = FEED_ICON[f.art] || [Clock, ''];
          const title = f.art === 'aenderung' ? (ACTION_TXT[f.aktion] || f.aktion) : `${f.name} ${t(`ls.f_${f.art}`)}`;
          const sub = f.art === 'aenderung' ? [f.name, f.wer && t('ls.by', { wer: f.wer })].filter(Boolean).join(' · ') : f.text;
          return (<li key={i}><Link to={f.link}>
            <span className={`ck-feed-ic ${cls}`}><Icon size={15} /></span>
            <span className="ck-feed-t">{title}<small>{sub}</small></span>
            <span className="ck-feed-time">{when(f.zeit)}</span></Link></li>);
        })}</ul>)}
    </section>
  );
}

/* 6) Heute abwesend */
function Abwesend({ heute, woche }) {
  const later = [];
  (woche || []).slice(1).forEach((d) => [...d.urlaub, ...d.krank].forEach((x) => {
    if (!later.find((l) => l.employee_id === x.employee_id) && !(heute || []).find((h) => h.employee_id === x.employee_id)) later.push({ ...x, ab: d.datum, tag: d.tag });
  }));
  return (
    <section className="ck-card" aria-labelledby="ab2-h">
      <div className="ck-card-head"><h2 id="ab2-h"><Palmtree size={20} />{t('ls.absent')}</h2>
        <Link className="ck-link-more" to="/cockpit/einstellungen?tab=urlaub">{t('status.urlaub')}<ChevronRight size={16} /></Link></div>
      {!heute ? <SkeletonRows n={2} /> : (<>
        {heute.length === 0 ? <div className="ck-card-body ck-muted" style={{ display: 'flex', gap: 10, alignItems: 'center' }}><CircleCheckBig size={18} />{t('ls.absent_none')}</div> : (
          <ul className="ck-list">{heute.map((a) => (
            <li key={a.employee_id} className="ck-row">{a.grund === 'Krank' ? <Thermometer size={18} /> : <Palmtree size={18} />}
              <div className="ck-row-main"><div className="ck-row-title"><Link to={`/cockpit/mitarbeiter/${a.employee_id}`}>{a.name}</Link></div></div>
              <Status s={a.grund === 'Krank' ? 'krank' : 'urlaub'} /></li>))}</ul>)}
        {later.length > 0 && <>
          <div className="ck-section-title">{t('ls.absent_week')}</div>
          <ul className="ck-list">{later.map((a) => (
            <li key={a.employee_id} className="ck-row"><span className="ck-row-time" style={{ minWidth: 70 }}>{a.tag} {fmtDate(a.ab)}</span>
              <div className="ck-row-main"><div className="ck-row-title"><Link to={`/cockpit/mitarbeiter/${a.employee_id}`}>{a.name}</Link></div></div>
              <Status s={a.grund === 'Krank' ? 'krank' : 'urlaub'} /></li>))}</ul></>}
      </>)}
    </section>
  );
}

function ActionDialog({ item, aktion, onClose, onRun, busy }) {
  const [text, setText] = useState('');
  const what = t(`item.${item.typ}`);
  const reply = aktion === 'antworten';
  return (
    <Dialog title={reply ? t('act.reply_title', { name: item.name }) : t('act.reject_title', { what, name: item.name })} onClose={onClose}
      footer={<>
        <button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button>
        <button className="ck-btn ck-btn-primary" disabled={busy || (reply && !text.trim())} onClick={() => onRun(text)}>
          {reply ? t('act.antworten') : t('act.ablehnen')}</button>
      </>}>
      <div className="ck-callout c-info" style={{ fontWeight: 500 }}>{item.text}</div>
      <label className="ck-field">{reply ? t('act.reply_label') : t('act.reject_label')}
        <textarea className="ck-input" style={{ height: 110, padding: 12 }} value={text} onChange={(e) => setText(e.target.value)} autoFocus /></label>
    </Dialog>
  );
}

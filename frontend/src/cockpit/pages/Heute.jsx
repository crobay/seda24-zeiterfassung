import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { UserCheck, UserX, ListChecks, Timer, Inbox, CalendarCheck2, PartyPopper, Check, X, MessageSquare, Palmtree, Thermometer } from 'lucide-react';
import { api, apiError, t, fmtNum, useApi, useApp, Status, SkeletonRows, Skeleton, Empty, ErrorBox, Dialog } from '../core';

const greet = () => { const h = new Date().getHours(); return t(h < 11 ? 'greet.morning' : h < 18 ? 'greet.day' : 'greet.evening'); };
const ATTENTION = ['fehlt', 'offen'];
const ITEM_ICON = { genehmigung: CalendarCheck2, nachtrag: CalendarCheck2, urlaub: Palmtree, schichtwunsch: CalendarCheck2, nachricht: MessageSquare };

export default function Heute() {
  const { me, toast, setCounts } = useApp();
  const { data, loading, error, reload } = useApi('/heute');
  const [busy, setBusy] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [hidden, setHidden] = useState(() => new Set());
  useEffect(() => { if (data) setCounts((c) => ({ ...c, offen: data.offen.length })); }, [data, setCounts]);
  useEffect(() => { const i = setInterval(reload, 60000); return () => clearInterval(i); }, [reload]);

  const k = data?.kennzahlen;
  const month = new Date().toLocaleDateString('de-DE', { month: 'long' });
  const dateText = new Date().toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' });

  const run = async (item, aktion, text) => {
    setBusy(`${item.typ}${item.id}`);
    try {
      await api.post(`/aktion/${item.typ}/${item.id}`, { aktion, text });
      setHidden((h) => new Set(h).add(`${item.typ}${item.id}`));
      const what = t(`item.${item.typ}`);
      const undo = aktion === 'gelesen' ? async () => {
        await api.post(`/aktion/nachricht/${item.id}`, { aktion: 'ungelesen' });
        setHidden((h) => { const n = new Set(h); n.delete(`${item.typ}${item.id}`); return n; });
        reload();
      } : undefined;
      toast(t(`act.done_${aktion}`, { what, name: item.name }), { undo });
      reload();
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(null); setDialog(null);
  };

  const offen = (data?.offen || []).filter((i) => !hidden.has(`${i.typ}${i.id}`));
  const shifts = data?.schichten || [];
  const attention = shifts.filter((s) => ATTENTION.includes(s.status));
  const rest = shifts.filter((s) => !ATTENTION.includes(s.status));

  return (
    <>
      <div className="ck-page-head">
        <div>
          <h1>{greet()}{me?.name ? `, ${me.name.split(' ')[0]}` : ''}</h1>
          <p>{dateText}{data ? ` · ${t('heute.subtitle', { date: '', time: data.uhrzeit }).replace(/^ · /, '')}` : ''}</p>
        </div>
      </div>

      <div className="ck-kpis">
        <Kpi tone="ok" Icon={UserCheck} label={t('heute.kpi_present')} value={k?.anwesend} sub={k && t('heute.kpi_present_sub', { n: k.geplant })} href="#schichten" />
        <Kpi tone="warn" alert={k?.fehlt > 0} Icon={UserX} label={t('heute.kpi_missing')} value={k?.fehlt}
          sub={k && (k.fehlt ? t('heute.kpi_missing_sub') : t('heute.kpi_missing_none'))} href="#schichten" />
        <Kpi tone="accent" Icon={ListChecks} label={t('heute.kpi_open')} value={k ? offen.length : undefined} sub={t('heute.kpi_open_sub')} href="#todo" />
        <Kpi tone="info" Icon={Timer} label={t('heute.kpi_hours', { month })} value={k && fmtNum(k.stunden_monat, 0)} sub={k && t('heute.kpi_hours_sub', { n: k.einsaetze_monat })} to="/cockpit/zeiten" />
      </div>

      {error ? <div className="ck-card"><ErrorBox text={error} onRetry={reload} /></div> : (
        <div className="ck-two">
          <section className="ck-card" id="todo" aria-labelledby="todo-h">
            <div className="ck-card-head"><h2 id="todo-h"><ListChecks size={20} />{t('heute.todo')}</h2>
              {offen.length > 0 && <span className="ck-tag">{offen.length}</span>}</div>
            {loading && !data ? <SkeletonRows n={3} /> : offen.length === 0 ? (
              <Empty icon={PartyPopper} title={t('heute.todo_empty_title')} text={t('heute.todo_empty')} />
            ) : (
              <ul className="ck-list">
                {offen.map((i) => {
                  const Icon = ITEM_ICON[i.typ] || Inbox;
                  const b = busy === `${i.typ}${i.id}`;
                  return (
                    <li key={`${i.typ}${i.id}`} className="ck-row">
                      <div className="ck-kpi-icon" style={{ background: 'var(--ck-accent-soft)', color: 'var(--ck-accent)', flex: 'none' }}><Icon size={18} /></div>
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

          <section className="ck-card" id="schichten" aria-labelledby="sch-h">
            <div className="ck-card-head"><h2 id="sch-h"><CalendarCheck2 size={20} />{t('heute.shifts')}</h2>
              {data && <span className="ck-subtle">{shifts.length}</span>}</div>
            {loading && !data ? <SkeletonRows n={4} /> : shifts.length === 0 && !data.ohne_schicht.length ? (
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
                      <div className="ck-row-meta">{s.objekt || '–'}</div></div><Status s={s.status} /></li>))}</ul></>}
              {data.abwesend.length > 0 && <>
                <div className="ck-section-title">{t('heute.absent')}</div>
                <ul className="ck-list">{data.abwesend.map((a) => (
                  <li key={a.employee_id} className="ck-row">{a.grund === 'Krank' ? <Thermometer size={18} /> : <Palmtree size={18} />}
                    <div className="ck-row-main"><div className="ck-row-title"><Link to={`/cockpit/mitarbeiter/${a.employee_id}`}>{a.name}</Link></div></div>
                    <Status s={a.grund === 'Krank' ? 'krank' : 'urlaub'} /></li>))}</ul></>}
            </>)}
          </section>
        </div>
      )}

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
    <li className={`ck-row ck-shift-row${['fehlt', 'offen'].includes(s.status) ? ' is-warn' : ''}`}>
      <span className="ck-row-time">{s.beginn}</span>
      <div className="ck-row-main">
        <div className="ck-row-title"><Link to={`/cockpit/mitarbeiter/${s.employee_id}`}>{s.name}</Link></div>
        <div className="ck-row-meta">{s.objekt} · {s.beginn}–{s.ende} <span className="ck-tag" title={t(`kat.${s.kategorie}`)}>{t(`kat.${s.kategorie}`).split(' · ')[1]}</span></div>
      </div>
      <div className="ck-shift-status"><Status s={s.status} label={long ? s.status_text : undefined} /></div>
    </li>
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

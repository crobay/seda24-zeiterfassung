import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Users, Search } from 'lucide-react';
import { t, useApi, Status, Skeleton, Empty, ErrorBox, initials } from '../core';

export default function Mitarbeiter() {
  const { data, loading, error, reload } = useApi('/mitarbeiter');
  const [q, setQ] = useState('');
  const [aktiv, setAktiv] = useState('aktiv');
  const list = useMemo(() => (data || []).filter((m) =>
    (aktiv === 'alle' || (aktiv === 'aktiv') === !!m.is_active) &&
    `${m.first_name} ${m.last_name} ${m.personal_nr} ${m.objekte || ''}`.toLowerCase().includes(q.trim().toLowerCase())), [data, q, aktiv]);

  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('ma.title')}</h1><p>{data ? t('ma.subtitle', { n: list.length }) : <Skeleton w={100} h={16} />}</p></div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <label className="ck-search" style={{ cursor: 'text', minWidth: 240 }}><Search size={18} />
            <input style={{ border: 0, outline: 0, background: 'transparent', flex: 1 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('ma.search')} aria-label={t('ma.search')} /></label>
          <div className="ck-seg" role="group">
            {['aktiv', 'inaktiv', 'alle'].map((k) => <button key={k} className={aktiv === k ? 'is-on' : ''} onClick={() => setAktiv(k)}>{k === 'alle' ? t('heute.filter_all') : t(`status.${k}`)}</button>)}
          </div>
        </div>
      </div>
      {error ? <div className="ck-card"><ErrorBox text={error} onRetry={reload} /></div> : loading ? (
        <div className="ck-tiles">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="ck-card ck-tile"><Skeleton w="60%" h={18} /><Skeleton w="80%" h={14} /><Skeleton w={80} h={24} r={999} /></div>)}</div>
      ) : list.length === 0 ? <div className="ck-card"><Empty icon={Users} title={t('ma.empty_title')} text={t('ma.empty')} /></div> : (
        <div className="ck-tiles">
          {list.map((m) => (
            <Link key={m.id} to={`/cockpit/mitarbeiter/${m.id}`} className="ck-card ck-tile">
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <div className="ck-avatar" style={{ width: 42, height: 42, fontSize: 15 }}>{initials(`${m.first_name} ${m.last_name}`)}</div>
                <div style={{ minWidth: 0 }}><div style={{ fontWeight: 650, fontSize: 17 }}>{m.first_name} {m.last_name}</div>
                  <div className="ck-subtle">{m.personal_nr} · {t(`kat.${m.category || 'C'}`)}</div></div>
              </div>
              <div className="ck-muted" style={{ fontSize: 15 }}>{m.objekte || t('ma.no_objects')}</div>
              <div><Status s={m.is_active ? 'aktiv' : 'inaktiv'} /></div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}

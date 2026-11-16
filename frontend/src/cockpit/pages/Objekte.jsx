import React, { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Building2, Users, CalendarCheck2, MapPin } from 'lucide-react';
import { t, useApi, Status, Skeleton, Empty, ErrorBox } from '../core';

export default function Objekte() {
  const { data, loading, error, reload } = useApi('/objekte');
  const hash = useLocation().hash;
  useEffect(() => { if (data && hash) document.querySelector(hash)?.scrollIntoView({ block: 'center', behavior: 'smooth' }); }, [data, hash]);
  const list = (data || []).filter((o) => o.is_active);

  return (
    <>
      <div className="ck-page-head"><div><h1>{t('obj.title')}</h1><p>{data ? t('obj.subtitle', { n: list.length }) : <Skeleton w={100} h={16} />}</p></div></div>
      {error ? <div className="ck-card"><ErrorBox text={error} onRetry={reload} /></div> : loading ? (
        <div className="ck-tiles">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="ck-card ck-tile"><Skeleton w="60%" h={18} /><Skeleton w="80%" h={14} /><Skeleton w={120} h={24} r={999} /></div>)}</div>
      ) : list.length === 0 ? <div className="ck-card"><Empty icon={Building2} title={t('obj.empty_title')} text={t('obj.empty')} /></div> : (
        <div className="ck-tiles">
          {list.map((o) => (
            <article key={o.id} id={`o${o.id}`} className={`ck-card ck-tile${hash === `#o${o.id}` ? ' is-today' : ''}`} style={hash === `#o${o.id}` ? { outline: '2px solid var(--ck-accent)' } : undefined}>
              <div style={{ fontWeight: 650, fontSize: 17, display: 'flex', gap: 8, alignItems: 'center' }}><Building2 size={18} />{o.name}</div>
              <div className="ck-muted" style={{ fontSize: 15 }}>{o.kunde || '–'}</div>
              {o.address && <div className="ck-subtle" style={{ display: 'flex', gap: 6 }}><MapPin size={15} style={{ flex: 'none', marginTop: 3 }} />{o.address}</div>}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
                <span className="ck-tag"><Users size={14} />{t('obj.ma', { n: o.ma })}</span>
                <span className="ck-tag"><CalendarCheck2 size={14} />{o.schichten_heute ? t('obj.today', { n: o.schichten_heute }) : t('obj.none_today')}</span>
              </div>
              <div>{o.ohne_km > 0 ? <Status s="fehlt" label={t('obj.km_missing', { n: o.ohne_km })} /> : <Status s="da" label={t('obj.km_ok')} />}</div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}

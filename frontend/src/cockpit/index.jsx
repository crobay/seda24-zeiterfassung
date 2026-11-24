import React, { Suspense, lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import './cockpit.css';
import { AppProvider, useApp, SkeletonRows, t } from './core';
import Shell from './Shell';
import Heute from './pages/Heute';

const Dienstplan = lazy(() => import('./pages/Dienstplan'));
const Vorlage = lazy(() => import('./pages/Vorlage'));
const Mitarbeiter = lazy(() => import('./pages/Mitarbeiter'));
const Akte = lazy(() => import('./pages/Akte'));
const Objekte = lazy(() => import('./pages/Objekte'));
const ObjektDetail = lazy(() => import('./pages/ObjektDetail'));
const Zeiten = lazy(() => import('./pages/Zeiten'));
const Abrechnung = lazy(() => import('./pages/Abrechnung'));
const Abschluss = lazy(() => import('./pages/Abschluss'));
const Material = lazy(() => import('./pages/Material'));
const Terminal = lazy(() => import('./pages/Terminal'));
const Einstellungen = lazy(() => import('./pages/Einstellungen'));

function Guard({ right, children }) {
  const { me } = useApp();
  if (me === null) return <SkeletonRows n={5} />;
  if (me === false) return <Navigate to="/login" replace />;
  if (right && !me.rechte?.[right]) return <Navigate to="/cockpit" replace />;
  return children;
}

export default function Cockpit() {
  return (
    <AppProvider>
      <Shell>
        <Suspense fallback={<div className="ck-card"><SkeletonRows n={5} /></div>}>
          <Guard>
            <Routes>
              <Route index element={<Heute />} />
              <Route path="dienstplan" element={<Dienstplan />} />
              <Route path="vorlage" element={<Vorlage />} />
              <Route path="mitarbeiter" element={<Mitarbeiter />} />
              <Route path="mitarbeiter/:id" element={<Akte />} />
              <Route path="objekte" element={<Objekte />} />
              <Route path="objekte/:id" element={<ObjektDetail />} />
              <Route path="zeiten" element={<Zeiten />} />
              <Route path="abrechnung" element={<Guard right="verwalten"><Abrechnung /></Guard>} />
              <Route path="abschluss" element={<Guard right="abschluss"><Abschluss /></Guard>} />
              <Route path="material" element={<Guard right="material"><Material /></Guard>} />
              <Route path="terminal" element={<Guard right="terminal"><Terminal /></Guard>} />
              <Route path="einstellungen" element={<Guard right="verwalten"><Einstellungen /></Guard>} />
              <Route path="*" element={<Navigate to="/cockpit" replace />} />
            </Routes>
          </Guard>
        </Suspense>
      </Shell>
    </AppProvider>
  );
}

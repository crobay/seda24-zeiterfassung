import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import axios from 'axios'
import { API_URL } from './config.js'
import { installiereServerPruefung } from './services/stempelStatus'

// Nur Antworten unseres Servers zaehlen (Gast-WLAN mit Anmeldeseite = kein Netz)
installiereServerPruefung(axios, API_URL)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

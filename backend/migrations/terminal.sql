-- Terminal-Modus (Drazen 24.11.2026): festes Tablet je Objekt, MA stempeln mit Name + 4-stelliger PIN.
-- Idempotent. Auf LIVE erst nach GO Drazen (als postgres einspielen, Eigentuemer danach seda24_user).

-- Stempel-Quelle in der Buchung (NULL = bisher: App/Admin wie gehabt, 'terminal' = Terminal-Tablet)
ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS quelle VARCHAR(20);

-- Registrierte Terminals: nur der SHA-256-Hash des Geraete-Tokens wird gespeichert
CREATE TABLE IF NOT EXISTS terminal_geraete (
    id SERIAL PRIMARY KEY,
    object_id INTEGER NOT NULL REFERENCES objects(id),
    name VARCHAR(80) NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    erstellt_am TIMESTAMP NOT NULL DEFAULT now(),
    erstellt_von INTEGER REFERENCES users(id),
    zuletzt_gesehen TIMESTAMP,
    zuletzt_ip VARCHAR(45),
    pin_fehler INTEGER NOT NULL DEFAULT 0,          -- Fehlversuche am Geraet (Sperre gegen Durchprobieren)
    gesperrt_bis TIMESTAMP,
    widerrufen_am TIMESTAMP,
    widerrufen_von INTEGER REFERENCES users(id)
);

-- Persoenliche Terminal-PIN je MA (bcrypt), Fehlversuche je MA
CREATE TABLE IF NOT EXISTS terminal_pin (
    employee_id INTEGER PRIMARY KEY REFERENCES employees(id),
    pin_hash VARCHAR(100) NOT NULL,
    gesetzt_am TIMESTAMP NOT NULL DEFAULT now(),
    gesetzt_von INTEGER REFERENCES users(id),
    fehler INTEGER NOT NULL DEFAULT 0,
    gesperrt_bis TIMESTAMP
);

ALTER TABLE terminal_geraete OWNER TO seda24_user;
ALTER TABLE terminal_pin OWNER TO seda24_user;


CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, csrf TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS enrollments (token TEXT PRIMARY KEY, name TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS nodes (
 id TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 region TEXT DEFAULT '', group_name TEXT DEFAULT '默认分组', hostname TEXT DEFAULT '',
 platform TEXT DEFAULT '', version TEXT DEFAULT '', seen REAL DEFAULT 0,
 created REAL NOT NULL, metrics TEXT DEFAULT '{}', policy TEXT NOT NULL,
 capabilities TEXT DEFAULT '[]', last_scheduled REAL DEFAULT 0,
 offline_alert INTEGER DEFAULT 0, revoked INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, node_id TEXT NOT NULL, action TEXT NOT NULL,
 status TEXT NOT NULL, created REAL NOT NULL, started REAL, finished REAL,
 lease TEXT, lease_expires REAL, result TEXT, source TEXT DEFAULT 'manual'
);
CREATE INDEX IF NOT EXISTS jobs_node ON jobs(node_id, status, created);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL, kind TEXT, node_id TEXT,
 message TEXT, notify INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0
);

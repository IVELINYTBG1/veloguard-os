"""The AI's persistent memory — what's trusted, and what the user decided before.

Two stores, each for what it's actually good at:

  * SQLite (stdlib)  — the structured trust store: "is THIS network/process
    trusted?" Exact lookups, instant, zero dependencies. The right tool for
    yes/no facts. This is the source of truth.

  * ChromaDB (optional) — semantic recall: "have we seen a *situation like* this
    before?" Stores the narrative of past decisions so the AI can reason over
    fuzzy similarity. Nice-to-have; the guard works fully without it.

Lives next to the rest of VeloGuard state (~/.config/veloguard/), so it inherits
the same 0700 directory.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from . import state

TRUST_VALUES = ("trusted", "untrusted", "blocked", "unknown")


def _db_path() -> Path:
    return state.state_dir() / "memory.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_db_path())
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
      CREATE TABLE IF NOT EXISTS networks(
        id TEXT PRIMARY KEY, ssid TEXT, bssid TEXT, security TEXT,
        trust TEXT NOT NULL, updated REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS processes(
        id TEXT PRIMARY KEY, name TEXT, path TEXT,
        trust TEXT NOT NULL, updated REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS prefs(key TEXT PRIMARY KEY, value TEXT);
      CREATE TABLE IF NOT EXISTS decisions(
        ts REAL NOT NULL, kind TEXT, subject TEXT, decision TEXT, note TEXT);
    """)
    return c


# --- networks --------------------------------------------------------------

def _net_id(ssid: str | None, bssid: str | None) -> str:
    # BSSID (the AP's MAC) is the strong identifier; SSID is the label.
    return (bssid or ssid or "?").lower()


def set_network_trust(ssid, bssid, security, trust: str) -> None:
    assert trust in TRUST_VALUES
    with _conn() as c:
        c.execute("INSERT INTO networks(id,ssid,bssid,security,trust,updated) "
                  "VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                  "trust=excluded.trust, updated=excluded.updated, "
                  "ssid=excluded.ssid, security=excluded.security",
                  (_net_id(ssid, bssid), ssid, bssid, security, trust, time.time()))


def get_network_trust(ssid, bssid) -> str | None:
    with _conn() as c:
        row = c.execute("SELECT trust FROM networks WHERE id=?",
                        (_net_id(ssid, bssid),)).fetchone()
    return row[0] if row else None


# --- processes -------------------------------------------------------------

def set_process_trust(key: str, name, path, trust: str) -> None:
    assert trust in TRUST_VALUES
    with _conn() as c:
        c.execute("INSERT INTO processes(id,name,path,trust,updated) "
                  "VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                  "trust=excluded.trust, updated=excluded.updated",
                  (key, name, path, trust, time.time()))


def get_process_trust(key: str) -> str | None:
    with _conn() as c:
        row = c.execute("SELECT trust FROM processes WHERE id=?", (key,)).fetchone()
    return row[0] if row else None


# --- preferences + decision log -------------------------------------------

def set_pref(key: str, value: str) -> None:
    with _conn() as c:
        c.execute("INSERT INTO prefs(key,value) VALUES(?,?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def get_pref(key: str, default: str | None = None) -> str | None:
    with _conn() as c:
        row = c.execute("SELECT value FROM prefs WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def log_decision(kind: str, subject: str, decision: str, note: str = "") -> None:
    with _conn() as c:
        c.execute("INSERT INTO decisions(ts,kind,subject,decision,note) "
                  "VALUES(?,?,?,?,?)", (time.time(), kind, subject, decision, note))
    SemanticMemory().add(
        f"{kind}: {subject} -> {decision}. {note}",
        {"kind": kind, "subject": subject, "decision": decision})


class SemanticMemory:
    """Optional ChromaDB-backed recall. No-ops cleanly if chromadb isn't installed
    (e.g. before provision, or on a Python the wheels don't cover yet)."""

    _client = None

    def __init__(self) -> None:
        self.available = False
        try:
            import chromadb
        except Exception:
            return
        try:
            if SemanticMemory._client is None:
                SemanticMemory._client = chromadb.PersistentClient(
                    path=str(state.state_dir() / "chroma"))
            self._col = SemanticMemory._client.get_or_create_collection("veloguard")
            self.available = True
        except Exception:
            self.available = False

    def add(self, text: str, metadata: dict) -> None:
        if not self.available:
            return
        try:
            self._col.add(documents=[text], metadatas=[metadata],
                          ids=[f"{metadata.get('kind','x')}-{time.time_ns()}"])
        except Exception:
            pass

    def recall(self, query: str, n: int = 5) -> list[str]:
        if not self.available:
            return []
        try:
            res = self._col.query(query_texts=[query], n_results=n)
            return res.get("documents", [[]])[0]
        except Exception:
            return []

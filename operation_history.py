"""Histórico local por conta do Windows; não armazena imagens nem credenciais."""
import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime


class History:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'HEICLite' / 'historico.sqlite3'

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        db.execute('CREATE TABLE IF NOT EXISTS operations (id INTEGER PRIMARY KEY, started TEXT, data TEXT)')
        return db

    def start(self, data):
        db = self.connect()
        try:
            with db:
                cursor = db.execute('INSERT INTO operations(started,data) VALUES (?,?)',
                                    (datetime.now().isoformat(timespec='seconds'), json.dumps(data, ensure_ascii=False)))
                return cursor.lastrowid
        finally: db.close()

    def finish(self, key, data):
        db = self.connect()
        try:
            with db: db.execute('UPDATE operations SET data=? WHERE id=?', (json.dumps(data, ensure_ascii=False), key))
        finally: db.close()

    def list(self, limit=200, offset=0):
        db = self.connect()
        try:
            return [dict(id=key, started=started, **json.loads(data)) for key, started, data in
                    db.execute('SELECT id,started,data FROM operations ORDER BY id DESC LIMIT ? OFFSET ?', (limit, offset))]
        finally: db.close()

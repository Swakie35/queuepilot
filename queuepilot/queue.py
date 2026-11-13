"""SQLite-backed at-least-once task execution primitives."""
from __future__ import annotations
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass

@dataclass(frozen=True)
class Job:
    id: str
    kind: str
    payload: dict
    attempts: int
    lease_owner: str

class Queue:
    def __init__(self,path=':memory:',clock=time.time):
        self.con=sqlite3.connect(path,isolation_level=None,timeout=10,check_same_thread=False)
        self.con.row_factory=sqlite3.Row
        self.clock=clock
        self.con.execute('PRAGMA busy_timeout=10000')
        self.con.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,
          idem_key TEXT UNIQUE,status TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL,
          available_at REAL NOT NULL,lease_until REAL,lease_owner TEXT,
          last_error TEXT,created_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS jobs_pickup ON jobs(status,available_at);
        """)
    def enqueue(self,kind:str,payload:dict,idem_key:str|None=None,max_attempts:int=3)->str:
        if not kind.strip() or not isinstance(payload,dict) or max_attempts<1:
            raise ValueError('invalid task')
        encoded=json.dumps(payload,sort_keys=True,separators=(',',':'))
        self.con.execute('BEGIN IMMEDIATE')
        try:
            existing=self.con.execute('SELECT id,kind,payload FROM jobs WHERE idem_key=?',(idem_key,)).fetchone() if idem_key else None
            if existing:
                if existing['kind']!=kind or existing['payload']!=encoded:
                    raise ValueError('idempotency key reused with different task')
                self.con.commit();return existing['id']
            jid=str(uuid.uuid4())
            self.con.execute('INSERT INTO jobs(id,kind,payload,idem_key,status,max_attempts,available_at,created_at) VALUES(?,?,?,?,?,?,?,?)',
                             (jid,kind,encoded,idem_key,'pending',max_attempts,self.clock(),self.clock()))
            self.con.commit();return jid
        except Exception:
            self.con.rollback();raise
    def claim(self,owner:str,lease_seconds:float=30)->Job|None:
        if not owner or lease_seconds<=0:raise ValueError('invalid lease')
        now=self.clock()
        self.con.execute('BEGIN IMMEDIATE')
        try:
            # A lost worker's lease is eligible for redelivery; counts as an attempt.
            row=self.con.execute("""SELECT * FROM jobs WHERE
                (status='pending' AND available_at<=?) OR
                (status='running' AND lease_until<=?)
                ORDER BY created_at,id LIMIT 1""",(now,now)).fetchone()
            if not row:
                self.con.commit();return None
            if row['attempts']>=row['max_attempts']:
                self.con.execute("UPDATE jobs SET status='dead',last_error='lease expired after maximum attempts',lease_owner=NULL WHERE id=?",(row['id'],))
                self.con.commit();return self.claim(owner,lease_seconds)
            attempt=row['attempts']+1
            self.con.execute('UPDATE jobs SET status=?,attempts=?,lease_until=?,lease_owner=? WHERE id=?',
                             ('running',attempt,now+lease_seconds,owner,row['id']))
            self.con.commit()
            return Job(row['id'],row['kind'],json.loads(row['payload']),attempt,owner)
        except Exception:
            self.con.rollback();raise
    def _owned(self,jid:str,owner:str):
        row=self.con.execute('SELECT status,lease_owner,lease_until,attempts,max_attempts FROM jobs WHERE id=?',(jid,)).fetchone()
        if not row or row['status']!='running' or row['lease_owner']!=owner or row['lease_until']<=self.clock():
            raise ValueError('job is not held under an active lease by this worker')
        return row
    def complete(self,jid:str,owner:str):
        self.con.execute('BEGIN IMMEDIATE')
        try:
            self._owned(jid,owner)
            self.con.execute("UPDATE jobs SET status='done',lease_owner=NULL,lease_until=NULL WHERE id=?",(jid,))
            self.con.commit()
        except Exception:self.con.rollback();raise
    def fail(self,jid:str,owner:str,error:str,base_delay:float=2):
        if base_delay<0: raise ValueError('negative delay')
        self.con.execute('BEGIN IMMEDIATE')
        try:
            row=self._owned(jid,owner)
            dead=row['attempts']>=row['max_attempts']
            # Capped exponential backoff; no jitter to keep tests reproducible.
            delay=min(300,base_delay*2**(row['attempts']-1))
            self.con.execute("""UPDATE jobs SET status=?, available_at=?, lease_owner=NULL,lease_until=NULL,last_error=? WHERE id=?""",
                             ('dead' if dead else 'pending',self.clock()+delay,error[:300],jid))
            self.con.commit()
        except Exception:self.con.rollback();raise
    def status(self,jid:str)->dict|None:
        r=self.con.execute('SELECT id,kind,status,attempts,max_attempts,available_at,last_error FROM jobs WHERE id=?',(jid,)).fetchone()
        return dict(r) if r else None
    def counts(self)->dict:
        return dict(self.con.execute('SELECT status,COUNT(*) AS n FROM jobs GROUP BY status').fetchall())

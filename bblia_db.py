"""SQLite-compatible minimal adapter for BBLIA auth/wallet PostgreSQL.
Use BBLIA_DATABASE_URL (Render internal URL). No credentials in source code.
"""
import os,sqlite3,re

try:
 import psycopg
 IntegrityError=(sqlite3.IntegrityError,psycopg.errors.UniqueViolation)
 Error=(sqlite3.Error,psycopg.Error)
except ImportError:
 IntegrityError=sqlite3.IntegrityError
 Error=sqlite3.Error

class PgConnection:
 def __init__(self,url,autocommit=False):
  import psycopg
  self.conn=psycopg.connect(url,autocommit=autocommit,connect_timeout=10)
 def execute(self,sql,params=()):
  sql=sql.strip()
  if sql.upper().startswith('PRAGMA '):return self.conn.cursor()
  sql=sql.replace('BEGIN IMMEDIATE','BEGIN')
  sql=sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT','BIGSERIAL PRIMARY KEY')
  sql=re.sub(r'\bBLOB\b','BYTEA',sql,flags=re.I)
  sql=re.sub(r'INSERT OR IGNORE INTO (\w+)\s*\(([^)]*)\) VALUES\s*\(([^)]*)\)',r'INSERT INTO \1(\2) VALUES(\3) ON CONFLICT DO NOTHING',sql,flags=re.I)
  sql=sql.replace('?', '%s')
  return self.conn.execute(sql,params)
 def commit(self):self.conn.commit()
 def rollback(self):self.conn.rollback()
 def close(self):self.conn.close()

def connect(path,timeout=10,isolation_level='DEFERRED'):
 url=os.getenv('BBLIA_DATABASE_URL','').strip()
 if url:
  return PgConnection(url,autocommit=(isolation_level is None))
 return sqlite3.connect(path,timeout=timeout,isolation_level=isolation_level)

def using_postgres():return bool(os.getenv('BBLIA_DATABASE_URL','').strip())

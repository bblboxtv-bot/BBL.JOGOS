"""Safe startup smoke test for BBLIA PostgreSQL. Run only with BBLIA_DATABASE_URL configured.
Creates a dedicated, harmless healthcheck table and verifies persistence.
Never logs the URL or credentials.
"""
import os,sys,secrets
def main():
 if not os.getenv('BBLIA_DATABASE_URL'):
  print('BLOCKED: BBLIA_DATABASE_URL is missing');return 2
 try:
  import psycopg
  with psycopg.connect(os.environ['BBLIA_DATABASE_URL'],connect_timeout=10) as con:
   con.execute('CREATE TABLE IF NOT EXISTS bblia_stage6_db_check (id TEXT PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())')
   token='stage6_'+secrets.token_hex(12)
   con.execute('INSERT INTO bblia_stage6_db_check(id) VALUES (%s)',(token,))
   row=con.execute('SELECT id FROM bblia_stage6_db_check WHERE id=%s',(token,)).fetchone()
   assert row and row[0]==token
   con.execute('DELETE FROM bblia_stage6_db_check WHERE id=%s',(token,))
  print('PASS: PostgreSQL connected, wrote, read, and cleaned up test record')
  return 0
 except Exception as e:
  print('FAIL: PostgreSQL test failed ('+type(e).__name__+')')
  return 1
if __name__=='__main__':sys.exit(main())

"""Temporary opt-in PostgreSQL smoke check for the isolated stage-6 Render service.
Only runs when BBLIA_STAGE6_DB_SMOKE=1; never prints secrets.
"""
import os
if os.environ.get('BBLIA_STAGE6_DB_SMOKE')=='1':
 try:
  from bblia_postgres_smoke import main
  status=main()
  print('BBLIA_STAGE6_SMOKE_RESULT='+('PASS' if status==0 else 'FAIL'),flush=True)
 except Exception as exc:
  print('BBLIA_STAGE6_SMOKE_RESULT=FAIL ('+type(exc).__name__+')',flush=True)

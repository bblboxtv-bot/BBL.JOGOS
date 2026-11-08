"""Stage 6 isolated email-auth PostgreSQL test; no credentials printed."""
import os,secrets
def main():
 import bblia_email_auth as auth
 import psycopg
 email='stage6-'+secrets.token_hex(8)+'@example.invalid'
 password=secrets.token_urlsafe(32)
 old=os.environ.get('BBLIA_EMAIL_REGISTRATION')
 os.environ['BBLIA_EMAIL_REGISTRATION']='enabled'
 try:
  auth.register(email,password,'Stage6 Test')
  result,cookie=auth.login(email,password)
  assert result['authenticated']
  session=auth.session(cookie)
  assert session and session['user']['email']==email
  auth.logout(cookie)
  assert auth.session(cookie) is None
  print('BBLIA_STAGE6_AUTH_RESULT=PASS',flush=True)
 except Exception as e:
  print('BBLIA_STAGE6_AUTH_RESULT=FAIL ('+type(e).__name__+')',flush=True)
 finally:
  if old is None:os.environ.pop('BBLIA_EMAIL_REGISTRATION',None)
  else:os.environ['BBLIA_EMAIL_REGISTRATION']=old
  with psycopg.connect(os.environ['BBLIA_DATABASE_URL']) as db:
   db.execute('DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE email=%s)',(email,))
   db.execute('DELETE FROM users WHERE email=%s',(email,))
if os.getenv('BBLIA_STAGE6_AUTH_SMOKE')=='1' and os.getenv('BBLIA_DATABASE_URL'):
 main()

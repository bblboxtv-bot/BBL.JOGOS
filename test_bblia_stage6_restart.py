"""BBLIA stage 6 restart durability smoke test. Run on isolated test databases."""
import os,tempfile,subprocess,sys,json,secrets
from pathlib import Path

def run(code,env):
 p=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=30)
 if p.returncode:raise RuntimeError(p.stderr)
 return json.loads(p.stdout.strip())
with tempfile.TemporaryDirectory() as tmp:
 env=os.environ.copy()
 env['BBLIA_AUTH_DB']=str(Path(tmp)/'auth.sqlite3')
 env['BBLIA_CREDITS_DB']=str(Path(tmp)/'credits.sqlite3')
 env['BBLIA_EMAIL_REGISTRATION']='enabled'
 email=secrets.token_hex(8)+'@example.com'
 password=secrets.token_urlsafe(24)
 first=run("import bblia_email_auth as a,bblia_wallet as w,json,os; a.register(os.environ['TEST_EMAIL'],os.environ['TEST_PASS'],'Tester'); r,c=a.login(os.environ['TEST_EMAIL'],os.environ['TEST_PASS']); o=w.create_order('test-user',1000); w.settle_verified(o['order_id'],'test-payment',True); print(json.dumps({'cookie':c,'balance':w.balance('test-user')['balance']}))",dict(env,TEST_EMAIL=email,TEST_PASS=password))
 assert first['balance']==100
 second=run("import bblia_email_auth as a,bblia_wallet as w,json,os; print(json.dumps({'user':a.session(os.environ['TEST_COOKIE'])['user']['email'],'balance':w.balance('test-user')['balance']}))",dict(env,TEST_COOKIE=first['cookie']))
 assert second=={'user':email,'balance':100},second
 print('PASS: auth session and wallet persisted across independent Python processes')
print('WARNING: local disk test does not prove Render redeploy persistence')

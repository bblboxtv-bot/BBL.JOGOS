"""Local BBLIA email/password login. Requires durable BBLIA_AUTH_DB before production."""
import os,bblia_db as sqlite3,time,secrets,hashlib,hmac,re,threading
from http.cookies import SimpleCookie
from pathlib import Path
LOCK=threading.RLock()
ATTEMPTS={}

TTL=30*24*3600
class AuthError(Exception):
 def __init__(self,message,status=400):super().__init__(message);self.status=status
def _db():
 path=Path(os.getenv('BBLIA_AUTH_DB','bblia_auth.sqlite3'));path.parent.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(str(path),timeout=10)
 db.execute('PRAGMA busy_timeout=10000')
 db.execute('CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,salt BLOB NOT NULL,password_hash BLOB NOT NULL,created_at INTEGER NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires INTEGER NOT NULL)')
 db.commit();return db
def _email(value):
 if not isinstance(value,str):raise AuthError('E-mail inválido.')
 value=value.strip().casefold()
 if len(value)>254 or not re.fullmatch(r'[^\s@]{1,64}@[^\s@]+\.[^\s@]{2,}',value):raise AuthError('E-mail inválido.')
 return value
def _password(value):
 if not isinstance(value,str) or not 12<=len(value)<=128:raise AuthError('Use uma senha de 12 a 128 caracteres.')
 return value
def _hash(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode(),salt,310000)
def _cookie(token,age=TTL):return '__Host-bblia_email='+token+'; Path=/; Max-Age='+str(age)+'; Secure; HttpOnly; SameSite=Lax'
def register(email,password,name):
 if os.getenv('BBLIA_EMAIL_REGISTRATION','disabled')!='enabled':raise AuthError('Cadastro por e-mail ainda não liberado.',503)
 email=_email(email);password=_password(password)
 if not isinstance(name,str) or not 1<=len(name.strip())<=100:raise AuthError('Informe seu nome.')
 salt=secrets.token_bytes(24);uid='email:'+secrets.token_hex(16)
 with LOCK:
  db=_db()
  try:
   db.execute('INSERT INTO users VALUES(?,?,?,?,?,?)',(uid,email,name.strip(),salt,_hash(password,salt),int(time.time())));db.commit()
  except Exception as exc:
   if getattr(exc,'sqlstate',None)=='23505' or isinstance(exc,sqlite3.IntegrityError):raise AuthError('Este e-mail já está cadastrado.',409)
   raise
  finally:db.close()
 return {'created':True}
def login(email,password):
 email=_email(email)
 if not isinstance(password,str):raise AuthError('E-mail ou senha incorretos.',401)
 with LOCK:
  now=time.time();recent=[t for t in ATTEMPTS.get(email,[]) if t>now-900]
  if len(recent)>=8:raise AuthError('Muitas tentativas. Aguarde 15 minutos.',429)
  db=_db()
  try:
   row=db.execute('SELECT id,salt,password_hash FROM users WHERE email=?',(email,)).fetchone()
   salt=row[1] if row else b'\0'*24
   valid=hmac.compare_digest(_hash(password[:129],salt),row[2] if row else b'\0'*32)
   if not row or not valid:
    ATTEMPTS[email]=(recent+[now])[-8:]
    raise AuthError('E-mail ou senha incorretos.',401)
   ATTEMPTS.pop(email,None)
   token=secrets.token_urlsafe(40);digest=hashlib.sha256(token.encode()).hexdigest()
   db.execute('DELETE FROM sessions WHERE expires<?',(int(time.time()),))
   db.execute('INSERT INTO sessions VALUES(?,?,?)',(digest,row[0],int(time.time())+TTL));db.commit()
   return {'authenticated':True},_cookie(token)
  finally:db.close()
def session(cookie):
 try:
  c=SimpleCookie();c.load(cookie or '');item=c.get('__Host-bblia_email')
  if not item:return None
  digest=hashlib.sha256(item.value.encode()).hexdigest()
  with LOCK:
   db=_db()
   try:
    row=db.execute('SELECT u.id,u.email,u.name FROM sessions s JOIN users u ON s.user_id=u.id WHERE s.token_hash=? AND s.expires>?',(digest,int(time.time()))).fetchone()
    return {'user':{'id':row[0],'email':row[1],'name':row[2]},'token':'email_session','scopes':['openid'],'expires':time.time()+TTL} if row else None
   finally:db.close()
 except (ValueError,sqlite3.Error):return None
def logout(cookie):
 try:
  c=SimpleCookie();c.load(cookie or '');item=c.get('__Host-bblia_email')
  if item:
   with LOCK:
    db=_db()
    try:db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(item.value.encode()).hexdigest(),));db.commit()
    finally:db.close()
 except (ValueError,sqlite3.Error):pass
 return {'disconnected':True},_cookie('',0)

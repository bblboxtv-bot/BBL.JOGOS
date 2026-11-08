"""BBLIA etapa 4: ledger de creditos. Pagamentos reais permanecem desativados."""
import os,sqlite3,threading,time,secrets
from pathlib import Path

DB=Path(os.getenv('BBLIA_CREDITS_DB','bblia_credits.sqlite3'))
LOCK=threading.RLock()
PACKAGES={1000:100,2000:230,4000:500,8000:1100}

class WalletError(Exception):
 def __init__(self,message,status=400):
  super().__init__(message);self.status=status

def _db():
 DB.parent.mkdir(parents=True,exist_ok=True)
 con=sqlite3.connect(str(DB),timeout=15,isolation_level=None)
 con.execute('PRAGMA busy_timeout=15000')
 con.execute('PRAGMA journal_mode=WAL')
 con.execute('CREATE TABLE IF NOT EXISTS wallets (user_id TEXT PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0 CHECK(balance>=0))')
 con.execute('CREATE TABLE IF NOT EXISTS payments (id TEXT PRIMARY KEY,user_id TEXT NOT NULL,amount_cents INTEGER NOT NULL,credits INTEGER NOT NULL,status TEXT NOT NULL,provider_ref TEXT UNIQUE,created_at INTEGER NOT NULL,paid_at INTEGER)')
 con.execute('CREATE TABLE IF NOT EXISTS movements (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,delta INTEGER NOT NULL,reason TEXT NOT NULL,ref TEXT NOT NULL UNIQUE,created_at INTEGER NOT NULL)')
 return con

def _id(user_id):
 if not isinstance(user_id,str) or not 1<=len(user_id)<=200:raise WalletError('Conta invalida.',401)
 return user_id

def balance(user_id):
 user_id=_id(user_id)
 with LOCK:
  con=_db()
  try:
   row=con.execute('SELECT balance FROM wallets WHERE user_id=?',(user_id,)).fetchone()
   return {'balance':row[0] if row else 0,'currency':'BRL'}
  finally:con.close()

def packages():
 return [{'amount_cents':a,'credits':c} for a,c in PACKAGES.items()]

def create_order(user_id,amount_cents):
 user_id=_id(user_id)
 if type(amount_cents)!=int or amount_cents not in PACKAGES:raise WalletError('Pacote invalido.')
 order='bblia_'+secrets.token_urlsafe(18)
 with LOCK:
  con=_db()
  try:
   con.execute('INSERT INTO payments(id,user_id,amount_cents,credits,status,created_at) VALUES(?,?,?,?,?,?)',(order,user_id,amount_cents,PACKAGES[amount_cents],'awaiting_provider',int(time.time())))
  finally:con.close()
 return {'order_id':order,'status':'awaiting_provider','amount_cents':amount_cents,'credits':PACKAGES[amount_cents],'pix_available':False}

def history(user_id,limit=30):
 user_id=_id(user_id)
 with LOCK:
  con=_db()
  try:
   payments=con.execute('SELECT id,amount_cents,credits,status,created_at,paid_at FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT ?', (user_id,min(max(int(limit),1),100))).fetchall()
   movements=con.execute('SELECT delta,reason,ref,created_at FROM movements WHERE user_id=? ORDER BY id DESC LIMIT 50',(user_id,)).fetchall()
   return {'payments':[dict(zip(('id','amount_cents','credits','status','created_at','paid_at'),r)) for r in payments],'movements':[dict(zip(('delta','reason','ref','created_at'),r)) for r in movements]}
  finally:con.close()

def _move(con,user_id,delta,reason,ref):
 con.execute('INSERT OR IGNORE INTO wallets(user_id,balance) VALUES(?,0)',(user_id,))
 if delta<0:
  cur=con.execute('UPDATE wallets SET balance=balance+? WHERE user_id=? AND balance>=?', (delta,user_id,-delta))
  if not cur.rowcount:raise WalletError('Creditos insuficientes.',402)
 else:con.execute('UPDATE wallets SET balance=balance+? WHERE user_id=?',(delta,user_id))
 con.execute('INSERT INTO movements(user_id,delta,reason,ref,created_at) VALUES(?,?,?,?,?)',(user_id,delta,reason,ref,int(time.time())))

def settle_verified(order_id,provider_ref,verified=False):
 """Internal only. Never expose as HTTP route. Caller must verify payment with provider server-side."""
 if verified is not True:raise WalletError('Pagamento nao verificado.',403)
 if not isinstance(provider_ref,str) or not provider_ref or len(provider_ref)>200:raise WalletError('Referencia invalida.')
 with LOCK:
  con=_db()
  try:
   con.execute('BEGIN IMMEDIATE')
   row=con.execute('SELECT user_id,credits,status,provider_ref FROM payments WHERE id=?',(order_id,)).fetchone()
   if not row:raise WalletError('Pedido nao encontrado.',404)
   user,credits,status,old_ref=row
   if status=='paid':
    if old_ref!=provider_ref:raise WalletError('Pagamento ja conciliado.',409)
    con.commit();return {'status':'paid','credited':False}
   if status!='awaiting_provider':raise WalletError('Pedido indisponivel.',409)
   _move(con,user,credits,'pix_verified','payment:'+order_id)
   con.execute("UPDATE payments SET status='paid',provider_ref=?,paid_at=? WHERE id=?",(provider_ref,int(time.time()),order_id))
   con.commit();return {'status':'paid','credited':True}
  except Exception:
   con.rollback();raise
  finally:con.close()

def spend(user_id,credits,ref):
 user_id=_id(user_id)
 if type(credits)!=int or credits<=0 or credits>100000:raise WalletError('Valor invalido.')
 if not isinstance(ref,str) or not 1<=len(ref)<=200:raise WalletError('Referencia invalida.')
 with LOCK:
  con=_db()
  try:
   con.execute('BEGIN IMMEDIATE')
   if con.execute('SELECT 1 FROM movements WHERE ref=?',('spend:'+ref,)).fetchone():
    con.commit();return {'charged':False,**balance(user_id)}
   _move(con,user_id,-credits,'usage','spend:'+ref)
   con.commit();return {'charged':True,**balance(user_id)}
  except Exception:
   con.rollback();raise
  finally:con.close()

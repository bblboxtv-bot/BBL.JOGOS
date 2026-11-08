"""Mercado Pago Pix: verify every settlement against the provider API."""
import os,json,urllib.request,urllib.error
from decimal import Decimal
import bblia_wallet as wallet

API='https://api.mercadopago.com'
def configured():
 return bool(os.getenv('BBLIA_MP_ACCESS_TOKEN','').strip())
def _request(path,method='GET',body=None,key=None):
 token=os.getenv('BBLIA_MP_ACCESS_TOKEN','').strip()
 if not token:raise wallet.WalletError('Mercado Pago ainda nao configurado.',503)
 headers={'Authorization':'Bearer '+token,'Accept':'application/json'}
 if body is not None:headers['Content-Type']='application/json'
 if key:headers['X-Idempotency-Key']=key
 data=json.dumps(body).encode() if body is not None else None
 req=urllib.request.Request(API+path,data=data,headers=headers,method=method)
 try:
  with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)
 except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ValueError):
  raise wallet.WalletError('Falha de comunicacao com o provedor de pagamento.',502)

def create_pix(user_id,email,amount_cents):
 if not configured():raise wallet.WalletError('Pix nao configurado.',503)
 if not isinstance(email,str) or '@' not in email:raise wallet.WalletError('Email do pagador indisponivel.',400)
 result=wallet.create_order(user_id,amount_cents)
 order_id=result['order_id']
 payload={'transaction_amount':float(Decimal(amount_cents)/100),'description':'Creditos BBLIA','payment_method_id':'pix','payer':{'email':email},'external_reference':order_id,'notification_url':os.getenv('BBLIA_MP_WEBHOOK_URL','https://bblia-teste.onrender.com/api/payments/webhook')}
 p=_request('/v1/payments','POST',payload,key=order_id)
 if not p.get('id') or str(p.get('external_reference'))!=order_id:
  raise wallet.WalletError('Provedor retornou um pedido inconsistente.',502)
 provider_id=str(p['id'])
 wallet.provider_link(order_id,provider_id)
 info=p.get('point_of_interaction') or {}
 transaction=info.get('transaction_data') or {}
 return {'order_id':order_id,'status':p.get('status'),'amount_cents':amount_cents,'credits':result['credits'],'pix_copy_paste':transaction.get('qr_code'),'pix_qr_base64':transaction.get('qr_code_base64'),'payment_id':provider_id}

def reconcile(payment_id):
 if not str(payment_id).isdigit():raise wallet.WalletError('Identificador invalido.',400)
 p=_request('/v1/payments/'+str(payment_id))
 order_id=p.get('external_reference')
 if not isinstance(order_id,str) or not order_id.startswith('bblia_'):return {'status':'ignored'}
 order=wallet.order(order_id)
 if str(p.get('id'))!=str(payment_id) or order['provider_ref']!=str(payment_id):
  raise wallet.WalletError('Pagamento nao corresponde ao pedido.',409)
 if p.get('currency_id')!='BRL' or int((Decimal(str(p.get('transaction_amount','0')))*100).quantize(Decimal('1')))!=order['amount_cents']:
  raise wallet.WalletError('Valor do pagamento divergente.',409)
 if p.get('status')!='approved':return {'status':p.get('status','pending'),'credited':False}
 return wallet.settle_verified(order_id,str(payment_id),verified=True)

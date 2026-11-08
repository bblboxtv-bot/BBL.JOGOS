"""Server-side preflight for paid OpenAI requests.

The client paid_authorized flag is consent only, never proof of sufficient funds.
This module deliberately does not alter live endpoints until prices are approved.
"""
import os
import bblia_wallet as wallet

class CreditGateError(Exception):
    def __init__(self,message,status):
        super().__init__(message)
        self.status=status

def configured_cost(feature):
    if not isinstance(feature,str) or feature not in ("chat","voice","transcribe","realtime"):
        raise CreditGateError("Recurso desconhecido.",400)
    raw=os.getenv("BBLIA_COST_"+feature.upper()+"_CREDITS")
    if raw is None:
        raise CreditGateError("Preco deste recurso ainda nao configurado.",503)
    try:cost=int(raw)
    except (TypeError,ValueError):raise CreditGateError("Preco invalido no servidor.",503)
    if not 1<=cost<=100000:raise CreditGateError("Preco invalido no servidor.",503)
    return cost

def preflight(user_id,feature,consented,admin=False):
    if consented is not True:
        raise CreditGateError("Autorize o uso pago antes de continuar.",403)
    if admin:return {"allowed":True,"charge":0,"admin":True}
    cost=configured_cost(feature)
    try:available=wallet.balance(user_id)["balance"]
    except (OSError,RuntimeError,ValueError, wallet.WalletError):
        raise CreditGateError("Saldo temporariamente indisponivel.",503)
    if available<cost:raise CreditGateError("Creditos insuficientes.",402)
    return {"allowed":True,"charge":cost,"admin":False}

def charge(user_id,feature,request_ref,consented,admin=False):
    """Atomic debit; call before paid API execution. Unique request_ref prevents double debit."""
    result=preflight(user_id,feature,consented,admin)
    if admin:return {"charged":False,"balance":None}
    if not isinstance(request_ref,str) or not 1<=len(request_ref)<=120:
        raise CreditGateError("Identificador invalido.",400)
    try:return wallet.spend(user_id,result["charge"],feature+":"+request_ref)
    except wallet.WalletError as exc:raise CreditGateError(str(exc),exc.status)

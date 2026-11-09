"""Optional Twilio SMS transport for isolated BBLIA phone authentication.

Only sends when explicitly configured with a Twilio account and approved sender.
No credentials or OTP values are returned to the browser.
"""
import base64
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

class SmsConfigError(ValueError):
    pass

def send_sms(phone, message):
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    sender = os.environ.get("TWILIO_FROM_NUMBER", "").strip()
    if not (sid.startswith("AC") and len(sid) == 34 and token and sender.startswith("+")):
        raise SmsConfigError("Envio SMS ainda não configurado.")
    url = "https://api.twilio.com/2010-04-01/Accounts/" + sid + "/Messages.json"
    payload = urlencode({"To": phone, "From": sender, "Body": message}).encode()
    authorization = base64.b64encode((sid + ":" + token).encode()).decode()
    req = Request(url, data=payload, headers={
        "Authorization": "Basic " + authorization,
        "Content-Type": "application/x-www-form-urlencoded",
    }, method="POST")
    try:
        with urlopen(req, timeout=15) as response:
            if response.status not in (200, 201):
                raise SmsConfigError("Falha no envio SMS.")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SmsConfigError("Não foi possível enviar SMS.") from exc

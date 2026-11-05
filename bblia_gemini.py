"""Provedor Gemini para a BBLIA. Sem fallback pago automático."""
import json, os, time, urllib.request, urllib.error

class GeminiError(Exception):
    pass

def responder(messages, model=None):
    key=os.environ.get('GEMINI_API_KEY','')
    if not key:
        raise GeminiError('Gemini não configurado no servidor. Configure GEMINI_API_KEY.')
    model=model or os.environ.get('BBLIA_GEMINI_MODEL','gemini-3.5-flash-lite')
    if not model.replace('-','').replace('.','').isalnum():
        raise GeminiError('Modelo Gemini inválido.')
    contents=[]
    for message in messages[-24:]:
        if not isinstance(message,dict): continue
        role='model' if message.get('role')=='assistant' else 'user'
        raw=message.get('content','')
        if isinstance(raw,list):
            text='\n'.join(str(part.get('text','')) for part in raw if isinstance(part,dict) and part.get('type') in ('input_text','text'))
        else: text=str(raw)
        if text.strip(): contents.append({'role':role,'parts':[{'text':text[:30000]}]})
    if not contents: raise GeminiError('Envie uma mensagem de texto.')
    payload={'systemInstruction':{'parts':[{'text':'Você é a BBLIA, assistente brasileira. Responda em português brasileiro, a menos que o usuário peça outro idioma. Responda de forma direta e natural. Para perguntas simples, use respostas breves. Não diga que executou tarefas sem confirmação real.'}]},'contents':contents,'generationConfig':{'maxOutputTokens':4096}}
    url='https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent'
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key},method='POST')
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req,timeout=25) as res: result=json.load(res)
            break
        except urllib.error.HTTPError as exc:
            if attempt==0 and exc.code in (500,502,503,504):
                time.sleep(0.4);continue
            if exc.code==429:raise GeminiError('Limite gratuito do Gemini atingido. Aguarde e tente novamente.') from exc
            raise GeminiError('Gemini indisponível (HTTP %s).'%exc.code) from exc
        except (OSError,TimeoutError) as exc:
            if attempt==0:time.sleep(0.4);continue
            raise GeminiError('Não foi possível acessar o Gemini.') from exc
    answer='\n'.join(p.get('text','') for c in result.get('candidates',[]) for p in c.get('content',{}).get('parts',[]) if isinstance(p,dict))
    if not answer:raise GeminiError('Gemini não retornou texto nesta solicitação.')
    return {'answer':answer,'artifacts':[],'sources':[],'web_used':False,'usage':{}}


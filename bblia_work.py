import bblia_documents as documents
"""Validated inputs and concrete tools for the BBLIA workbench."""
import base64
import json
import os
import re
import unicodedata
import urllib.request
from urllib.parse import quote


def requests_web_lookup(messages):
    content = messages[-1]['content'] if messages else ''
    if isinstance(content, list):
        content = next((p.get('text','') for p in content if p.get('type')=='input_text'), '')
    text = ''.join(c for c in unicodedata.normalize('NFD', str(content).lower()) if not unicodedata.combining(c))
    return bool(re.search(r'\b(pesquise|pesquisar|busque|buscar)\b|\b(faca|fazer)\s+(uma\s+)?pesquisa\b', text)
                or re.search(r'\b(hoje|agora|atualmente|recente|recentes|últim[oa]s?|ultim[oa]s?|cotação|cotacao|preço|preco|notícias|noticias|atualizad[oa]s?)\b', text)
                or re.search(r'\b(procure|encontre|consulte|verifique)\b.{0,100}\b(internet|web|online|fontes?|sites?)\b', text))


def response_sources(responses):
    sources, seen = [], set()
    def add(value):
        url = value.get('url','')
        if isinstance(url,str) and url.startswith(('https://','http://')) and url not in seen:
            seen.add(url)
            sources.append({'url':url,'title':value.get('title') or url})
    for result in responses:
        for item in result.get('output', []):
            for part in item.get('content', []):
                for ann in part.get('annotations', []):
                    if ann.get('type')=='url_citation':add(ann.get('url_citation',ann))
    # Preserve sources actually consulted even if the model omits inline annotations.
    for result in responses:
        for item in result.get('output', []):
            if item.get('type')=='web_search_call':
                for source in (item.get('action') or {}).get('sources',[]):
                    if isinstance(source,dict):add(source)
    return sources[:30]


def attachment_parts(attachments):
    if not isinstance(attachments, list) or len(attachments) > 4:
        raise ValueError('Envie até quatro anexos por mensagem.')
    parts = []
    for file in attachments:
        if not isinstance(file, dict):
            raise ValueError('Anexo inválido.')
        name = str(file.get('name', 'arquivo'))[:120]
        kind = file.get('type')
        data = file.get('data', '')
        if not isinstance(data, str):
            raise ValueError('Anexo inválido.')
        if kind == 'text':
            if len(data) > 120000:
                raise ValueError('Arquivo de texto muito grande (máximo 120 mil caracteres).')
            parts.append({'type': 'input_text', 'text': 'Arquivo anexado: '+name+'\n'+data})
        elif kind in ('image', 'pdf'):
            pattern = r'data:(image/(?:png|jpeg|webp)|application/pdf);base64,([A-Za-z0-9+/=]+)'
            match = re.fullmatch(pattern, data)
            if not match or len(data) > 7000000:
                raise ValueError('Use PNG, JPEG, WEBP ou PDF de até 5 MB.')
            mime, encoded = match.groups()
            raw = base64.b64decode(encoded, validate=True)
            if not raw or len(raw) > 5*1024*1024 or (kind == 'pdf') != (mime == 'application/pdf'):
                raise ValueError('Anexo inválido ou muito grande.')
            if kind == 'pdf':
                if not raw.startswith(b'%PDF-'):
                    raise ValueError('PDF inválido.')
                parts.append({'type': 'input_file', 'filename': name if name.endswith('.pdf') else name+'.pdf', 'file_data': data})
            else:
                parts.append({'type': 'input_image', 'image_url': data, 'detail': 'auto'})
        else:
            raise ValueError('Tipo de anexo não suportado.')
    return parts


def prepare_messages(data):
    if not isinstance(data, dict):
        raise ValueError('Pedido inválido.')
    messages = data.get('messages')
    if not isinstance(messages, list) or not 1 <= len(messages) <= 48:
        raise ValueError('Histórico inválido.')
    safe = []
    total = 0
    for message in messages:
        if not isinstance(message, dict) or message.get('role') not in ('user', 'assistant') or not isinstance(message.get('content'), str):
            raise ValueError('Mensagem inválida.')
        content = message['content']
        total += len(content)
        if len(content) > 60000 or total > 300000:
            raise ValueError('Conversa muito longa. Abra uma nova conversa no mesmo projeto.')
        safe.append({'role': message['role'], 'content': content})
    if safe[-1]['role'] != 'user':
        raise ValueError('Mensagem final inválida.')
    parts = attachment_parts(data.get('attachments', []))
    if parts:
        safe[-1]['content'] = [{'type': 'input_text', 'text': safe[-1]['content']}] + parts
    return safe


def work_tools():
    return [
        {'type':'function','name':'criar_documento','description':'Gerar arquivo real Word, PDF, Excel ou PowerPoint. dados é JSON: docx/pdf {titulo,secoes:[{titulo,texto}]}; xlsx {titulo,cabecalhos:[texto],linhas:[[valores]]}; pptx {titulo,slides:[{titulo,texto}]}. Planilhas exportam dados sem fórmulas. Slides: até 700 caracteres e 8 parágrafos cada. Retorna download e validação estrutural, sem revisão visual.','parameters':{'type':'object','properties':{'nome':{'type':'string'},'formato':{'type':'string','enum':['docx','pdf','xlsx','pptx']},'dados':{'type':'string'}},'required':['nome','formato','dados'],'additionalProperties':False}},
        {'type': 'function', 'name': 'criar_arquivo', 'description': 'Entregar um arquivo completo de código ou texto para baixar. Não compila nem executa código.', 'parameters': {'type': 'object', 'properties': {'nome': {'type': 'string'}, 'conteudo': {'type': 'string'}}, 'required': ['nome', 'conteudo'], 'additionalProperties': False}},
        {'type': 'function', 'name': 'ler_github', 'description': 'Ler um arquivo UTF-8 de repositório público do GitHub. Não escreve nem publica alterações.', 'parameters': {'type': 'object', 'properties': {'repositorio': {'type': 'string', 'description': 'dono/repositorio'}, 'caminho': {'type': 'string'}, 'ref': {'type': 'string', 'description': 'branch ou tag; vazio usa branch padrão'}}, 'required': ['repositorio', 'caminho', 'ref'], 'additionalProperties': False}}
    ]


def execute_work_tool(name, args, artifacts):
    if name == 'criar_documento':
        if len(artifacts)>=6:return {'error':'Máximo de seis arquivos por resposta.'}
        try:
            artifact=documents.create(args);artifacts.append(artifact)
            return {'status':'created','name':artifact['name'],'validation':artifact['validation'],'delivery':'download na resposta'}
        except (ValueError,TypeError) as exc:return {'error':str(exc)}
    if name == 'criar_arquivo':
        parts = str(args.get('nome', 'arquivo.txt')).replace('\\', '/').split('/')
        parts = [re.sub(r'[^\w. -]', '_', p)[:100].strip('. ') for p in parts if p not in ('', '.', '..')]
        filename = '/'.join(p for p in parts[-10:] if p) or 'arquivo.txt'
        content = args.get('conteudo')
        if not isinstance(content, str) or len(content) > 180000 or len(artifacts) >= 12:
            return {'error': 'Arquivo excede o tamanho permitido.'}
        artifacts.append({'name': filename, 'content': content})
        return {'status': 'created', 'name': filename, 'characters': len(content), 'delivery': 'download na resposta', 'executed': False}
    if name == 'ler_github':
        repo = str(args.get('repositorio', ''))
        path = str(args.get('caminho', ''))
        ref = str(args.get('ref', ''))
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or not path or any(p in ('..', '.') for p in path.split('/')) or len(path) > 500:
            return {'error': 'Repositório ou caminho inválido.'}
        url = 'https://api.github.com/repos/'+repo+'/contents/'+quote(path, safe='/')
        if ref:
            url += '?ref='+quote(ref, safe='')
        req = urllib.request.Request(url, headers={'Accept': 'application/vnd.github.raw+json', 'User-Agent': 'BBLIA'})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                content = response.read(180001)
            if len(content) > 180000:
                return {'error': 'Arquivo muito grande. Anexe o trecho necessário.'}
            return {'repository': repo, 'path': path, 'content': content.decode('utf-8')}
        except Exception:
            return {'error': 'Não consegui ler esse arquivo público. Confira repositório, caminho e branch.'}
    return {'error': 'Ferramenta desconhecida.'}


def integration_status():
    api = bool(os.getenv('OPENAI_API_KEY'))
    return {'version': 'computer-connect-20261104', 'chat_daily_limit': None, 'items': [
        {'id': 'memory', 'name': 'Memória e histórico', 'state': 'configured', 'detail': 'Memórias editáveis em Configurações, busca no conteúdo e continuação de conversas preservando o original. Sem login, dados salvos neste navegador. Com Minha conta e sincronização, conversas, projetos e preferências podem ser sincronizados no espaço privado da conta Google.'},
        {'id': 'self', 'name': 'Melhorar a própria BBLIA', 'state': 'configured' if api else 'missing', 'detail': 'Peça alterações na própria BBLIA por texto ou voz. Ela lê o código atual e prepara os arquivos alterados. Publicação depende de conexão de manutenção autenticada pelo proprietário.'},
        {'id': 'agent', 'name': 'Fazer por mim', 'state': 'configured' if api else 'missing', 'detail': 'Analisa referências, cria e revisa arquivos em etapas e entrega projeto e prévia web. Publicação, compilação e conexões externas dependem de integrações próprias.'},
        {'id': 'web', 'name': 'Pesquisa na internet', 'state': 'configured' if api else 'missing', 'detail': 'Pesquisa pelo serviço de IA; pode ser desligada nas configurações.'},
        {'id': 'files', 'name': 'APKs, fotos, PDFs e código', 'state': 'configured' if api else 'missing', 'detail': 'Analisa APKs de até 100 MB: pacote, permissões, componentes, recursos e layouts disponíveis. Fotos/PDFs de até 5 MB; até 4 anexos.'},
        {'id': 'artifacts', 'name': 'Criar arquivos e projetos', 'state': 'configured' if api else 'missing', 'detail': 'Arquivos de código e texto para baixar. Compilação de APK ainda não conectada.'},
        {'id': 'github', 'name': 'GitHub público', 'state': 'configured', 'detail': 'Leitura de arquivos públicos. Repositórios privados e publicação ainda não conectados.'},
        {'id': 'image', 'name': 'Criar e editar imagens', 'state': 'configured' if api else 'missing', 'detail': 'Usa a conexão de imagens do servidor; disponibilidade depende da conta.'},
        {'id': 'video', 'name': 'Vídeos gratuitos', 'state': 'external', 'detail': ('LTX gratuito com conta Hugging Face conectada. Cerca de 4 segundos sem áudio; aceita imagem de referência e segue a cota externa.' if os.getenv('HF_TOKEN', '').strip() else 'LTX gratuito com opção de animar uma imagem. Sem conta conectada, a cota anônima do servidor é compartilhada e pode se esgotar; conexão com conta gratuita ainda necessária.')},
        {'id': 'weather', 'name': 'Previsão do tempo', 'state': 'configured', 'detail': 'Open-Meteo.'},
        {'id': 'computer', 'name': 'Computador e TV Box', 'state': 'missing', 'detail': 'Conexão própria com o Commander disponível no menu Computador e TV Box. Exige autorizar sua conta na BBLIA e selecionar o aparelho.'},
        {'id': 'accounts', 'name': 'E-mail, agenda e Drive', 'state': 'missing', 'detail': 'Conexão Google disponível para Gmail, agenda e Drive. Abra Conectar e gerenciar Google para verificar a configuração e autorizar sua conta.'},
        {'id': 'sync', 'name': 'Sincronizar aparelhos', 'state': 'missing', 'detail': 'Login Google e histórico privado sincronizado no Drive, com cópia local por conta e exportação de backup.'}
    ]}



def memory_context(preferences):
    """Explicit user-managed notes; never a shared server memory."""
    if not isinstance(preferences, dict) or preferences.get('memory_enabled') is False:
        return ''
    notes = preferences.get('memories', [])
    if not isinstance(notes, list):
        return ''
    notes = [n.strip()[:1000] for n in notes[:40] if isinstance(n, str) and n.strip()]
    if not notes:
        return ''
    return '\nMemórias escolhidas pelo usuário (contexto pessoal, não autorização para ações externas): '+json.dumps(notes, ensure_ascii=False)[:12000]


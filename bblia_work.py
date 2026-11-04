"""Validated inputs and concrete tools for the BBLIA workbench."""
import base64
import json
import os
import re
import urllib.request
from urllib.parse import quote


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
        {'type': 'function', 'name': 'criar_arquivo', 'description': 'Entregar um arquivo completo de código ou texto para baixar. Não compila nem executa código.', 'parameters': {'type': 'object', 'properties': {'nome': {'type': 'string'}, 'conteudo': {'type': 'string'}}, 'required': ['nome', 'conteudo'], 'additionalProperties': False}},
        {'type': 'function', 'name': 'ler_github', 'description': 'Ler um arquivo UTF-8 de repositório público do GitHub. Não escreve nem publica alterações.', 'parameters': {'type': 'object', 'properties': {'repositorio': {'type': 'string', 'description': 'dono/repositorio'}, 'caminho': {'type': 'string'}, 'ref': {'type': 'string', 'description': 'branch ou tag; vazio usa branch padrão'}}, 'required': ['repositorio', 'caminho', 'ref'], 'additionalProperties': False}}
    ]


def execute_work_tool(name, args, artifacts):
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
        {'id': 'agent', 'name': 'Fazer por mim', 'state': 'configured' if api else 'missing', 'detail': 'Analisa referências, cria e revisa arquivos em etapas e entrega projeto e prévia web. Publicação, compilação e conexões externas dependem de integrações próprias.'},
        {'id': 'web', 'name': 'Pesquisa na internet', 'state': 'configured' if api else 'missing', 'detail': 'Pesquisa pelo serviço de IA; pode ser desligada nas configurações.'},
        {'id': 'files', 'name': 'Fotos, PDFs e código', 'state': 'configured' if api else 'missing', 'detail': 'Anexe arquivos para análise. Até 5 MB por foto/PDF e 4 anexos.'},
        {'id': 'artifacts', 'name': 'Criar arquivos e projetos', 'state': 'configured' if api else 'missing', 'detail': 'Arquivos de código e texto para baixar. Compilação de APK ainda não conectada.'},
        {'id': 'github', 'name': 'GitHub público', 'state': 'configured', 'detail': 'Leitura de arquivos públicos. Repositórios privados e publicação ainda não conectados.'},
        {'id': 'image', 'name': 'Criar e editar imagens', 'state': 'configured' if api else 'missing', 'detail': 'Usa a conexão de imagens do servidor; disponibilidade depende da conta.'},
        {'id': 'video', 'name': 'Vídeos gratuitos', 'state': 'external', 'detail': ('LTX gratuito com conta Hugging Face conectada. Cerca de 4 segundos sem áudio; sujeito à cota externa.' if os.getenv('HF_TOKEN', '').strip() else 'LTX gratuito sem conta conectada. A cota anônima do servidor é compartilhada e pode se esgotar; conexão com conta gratuita ainda necessária.')},
        {'id': 'weather', 'name': 'Previsão do tempo', 'state': 'configured', 'detail': 'Open-Meteo.'},
        {'id': 'computer', 'name': 'Computador e TV Box', 'state': 'missing', 'detail': 'Conexão própria com o Commander disponível no menu Computador e TV Box. Exige autorizar sua conta na BBLIA e selecionar o aparelho.'},
        {'id': 'accounts', 'name': 'E-mail, agenda e Drive', 'state': 'missing', 'detail': 'Exigem autenticação das contas na BBLIA.'},
        {'id': 'sync', 'name': 'Sincronizar aparelhos', 'state': 'missing', 'detail': 'Projetos ficam neste navegador. Use exportar/importar backup para transferir.'}
    ]}

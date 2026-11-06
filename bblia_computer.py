"""User-owned Desktop Commander OAuth and scoped MCP client.

Credentials arrive only on authenticated-by-possession requests over HTTPS.
They are never global, added to prompts, placed in job snapshots, or logged.
"""
import copy
import base64
import os
import secrets
import tempfile
from pathlib import Path
import json
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlsplit, quote

MCP_URL = 'https://mcp.desktopcommander.app/mcp'
REDIRECT_URI = 'https://bblia-teste.onrender.com/computer-callback'
TRUSTED_HOSTS = {'mcp.desktopcommander.app', 'auth.desktopcommander.app'}
ALLOWED_TOOLS = {'list_devices', 'list_directory', 'get_file_info', 'read_file', 'write_file',
    'create_directory', 'move_file', 'start_process', 'read_process_output', 'interact_with_process',
    'force_terminate', 'start_search', 'get_more_search_results', 'stop_search', 'get_tool_result'}
_METADATA = None
_METADATA_AT = 0
_LOCK = threading.Lock()
_CLIENT_FILE = Path(tempfile.gettempdir()) / "bblia-commander-clients.json"
_CLIENTS = {}
try:
    if _CLIENT_FILE.is_file():
        _CLIENTS = json.loads(_CLIENT_FILE.read_text())
except (OSError, ValueError):
    _CLIENTS = {}


class ComputerError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def configured_client():
    client_id=os.getenv('BBLIA_COMMANDER_CLIENT_ID','').strip()
    if not client_id:return None
    method=os.getenv('BBLIA_COMMANDER_CLIENT_AUTH_METHOD','none').strip()
    secret=os.getenv('BBLIA_COMMANDER_CLIENT_SECRET','')
    if method not in ('none','client_secret_basic','client_secret_post') or (method!='none' and not secret):
        raise ComputerError('O cadastro permanente do Commander está incompleto.',503)
    return {'client_id':client_id,'client_secret':secret,'token_endpoint_auth_method':method}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def trusted_url(url):
    parsed = urlsplit(url) if isinstance(url, str) else None
    if not parsed or parsed.scheme != 'https' or parsed.hostname not in TRUSTED_HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ComputerError('O serviço retornou um endereço de autenticação não permitido.', 502)
    return url


def open_request(request, timeout=35):
    trusted_url(request.full_url)
    # Identifies this application; never impersonates a browser or changes identity
    # in response to an access-control block.
    request.add_header('User-Agent', 'BBLIA/1.0 (Desktop Commander MCP client)')
    try:
        return urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise ComputerError('A autorização do Commander expirou. Reconecte sua conta na BBLIA.', 401)
        if exc.code == 403:
            raise ComputerError('O Commander recusou o acesso desta conexão. A autorização ou a liberação do serviço precisa ser conferida.', 403)
        if exc.code == 429:
            raise ComputerError('O Commander atingiu o limite de chamadas. Aguarde antes de tentar novamente.', 429)
        raise ComputerError('O Commander não concluiu a conexão (HTTP %s).' % exc.code, 502)
    except (TimeoutError, OSError):
        raise ComputerError('Não foi possível alcançar o Commander neste momento.', 502)


def json_request(url, payload=None, form=False, basic_auth=None):
    headers = {'Accept': 'application/json'}
    if basic_auth:
        encoded = base64.b64encode((quote(basic_auth[0], safe='')+':'+quote(basic_auth[1], safe='')).encode()).decode()
        headers['Authorization'] = 'Basic '+encoded
    data = None
    if payload is not None:
        data = urlencode(payload).encode() if form else json.dumps(payload).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    request = urllib.request.Request(trusted_url(url), data=data, headers=headers)
    with open_request(request) as response:
        body = response.read(1000001)
    if len(body) > 1000000:
        raise ComputerError('Resposta de autenticação muito grande.', 502)
    try:
        result = json.loads(body)
    except ValueError:
        raise ComputerError('O Commander não retornou os dados esperados.', 502)
    if not isinstance(result, dict):
        raise ComputerError('Resposta de autenticação inválida.', 502)
    return result


def oauth_metadata():
    global _METADATA, _METADATA_AT
    with _LOCK:
        if _METADATA and time.time()-_METADATA_AT < 600:
            return copy.deepcopy(_METADATA)
    resource = json_request('https://mcp.desktopcommander.app/.well-known/oauth-protected-resource')
    issuers = resource.get('authorization_servers') or []
    if not issuers:
        raise ComputerError('O Commander não informou seu servidor de autorização.', 502)
    issuer = trusted_url(issuers[0]).rstrip('/')
    parsed = urlsplit(issuer)
    metadata_url = parsed.scheme+'://'+parsed.netloc+'/.well-known/oauth-authorization-server'+parsed.path
    metadata = json_request(metadata_url)
    for name in ('authorization_endpoint', 'token_endpoint'):
        trusted_url(metadata.get(name))
    if metadata.get('registration_endpoint'):
        trusted_url(metadata['registration_endpoint'])
    if 'S256' not in metadata.get('code_challenge_methods_supported', []):
        raise ComputerError('O Commander não anunciou o pareamento seguro exigido por esta conexão.', 502)
    metadata['resource'] = trusted_url(resource.get('resource', MCP_URL))
    with _LOCK:
        _METADATA, _METADATA_AT = copy.deepcopy(metadata), time.time()
    return metadata


def oauth_start(data):
    state, challenge = data.get('state'), data.get('code_challenge')
    if not isinstance(state, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', state) or not isinstance(challenge, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', challenge):
        raise ComputerError('Pareamento inválido. Inicie novamente na BBLIA.')
    metadata = oauth_metadata()
    permanent=configured_client()
    if not permanent and not metadata.get('registration_endpoint'):
        raise ComputerError('O Commander exige registrar a BBLIA como cliente antes de conectar. O cadastro automático não está disponível.', 503)
    client = permanent or json_request(metadata['registration_endpoint'], {
        'client_name': 'BBLIA', 'redirect_uris': [REDIRECT_URI],
        'grant_types': ['authorization_code', 'refresh_token'], 'response_types': ['code'],
        'token_endpoint_auth_method': 'none'})
    client_id = client.get('client_id')
    if not isinstance(client_id, str) or not client_id:
        raise ComputerError('O Commander não registrou a BBLIA para autenticação.', 502)
    method = client.get('token_endpoint_auth_method', 'none')
    binding = None
    if method != 'none' and not permanent:
        secret = client.get('client_secret')
        if method not in ('client_secret_post', 'client_secret_basic') or not isinstance(secret, str) or not secret:
            raise ComputerError('O serviço exige uma configuração adicional de autenticação para a BBLIA.', 503)
        binding = secrets.token_urlsafe(32)
        expires = client.get('client_secret_expires_at') or time.time()+30*86400
        with _LOCK:
            for key in list(_CLIENTS):
                if _CLIENTS[key].get('expires', 0) < time.time():
                    del _CLIENTS[key]
            if len(_CLIENTS) >= 1000:
                raise ComputerError('Muitas conexões foram preparadas. Tente novamente mais tarde.', 429)
            _CLIENTS[binding] = {'client_id': client_id, 'client_secret': secret, 'method': method, 'expires': expires}
            # Only the opaque handle goes to the browser. The confidential client
            # secret stays in the server's private runtime file, not in source.
            temporary = _CLIENT_FILE.with_suffix('.tmp')
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(_CLIENTS, stream)
            os.replace(temporary, _CLIENT_FILE)
            os.chmod(_CLIENT_FILE, 0o600)
    params = {'client_id': client_id, 'redirect_uri': REDIRECT_URI, 'response_type': 'code',
              'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
              'resource': metadata['resource']}
    if 'offline_access' in metadata.get('scopes_supported', []):
        params['scope'] = 'offline_access'
    return {'authorization_url': metadata['authorization_endpoint']+'?'+urlencode(params),
            'client_id': client_id, 'client_binding': binding, 'redirect_uri': REDIRECT_URI}


def oauth_token(data, refresh=False):
    client_id = data.get('client_id')
    if not isinstance(client_id, str) or not 1 <= len(client_id) <= 500:
        raise ComputerError('Cliente de autenticação inválido.')
    metadata = oauth_metadata()
    params = {'client_id': client_id, 'resource': metadata['resource']}
    if refresh:
        value = data.get('refresh_token')
        if not isinstance(value, str) or not 1 <= len(value) <= 20000:
            raise ComputerError('Reconecte sua conta Commander.', 401)
        params.update(grant_type='refresh_token', refresh_token=value)
    else:
        code, verifier = data.get('code'), data.get('code_verifier')
        if not isinstance(code, str) or not 1 <= len(code) <= 20000 or not isinstance(verifier, str) or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}', verifier):
            raise ComputerError('Autorização inválida. Inicie novamente na BBLIA.')
        params.update(grant_type='authorization_code', code=code, code_verifier=verifier, redirect_uri=REDIRECT_URI)
    basic_auth = None
    binding = data.get('client_binding')
    permanent=configured_client()
    if permanent and client_id==permanent['client_id']:
        if permanent['token_endpoint_auth_method']=='client_secret_post':params['client_secret']=permanent['client_secret']
        elif permanent['token_endpoint_auth_method']=='client_secret_basic':basic_auth=(client_id,permanent['client_secret'])
    elif binding:
        with _LOCK:
            private = _CLIENTS.get(binding)
        if not private or private['client_id'] != client_id or private['expires'] < time.time():
            raise ComputerError('A conexão precisa ser autorizada novamente após a atualização da BBLIA.', 401)
        if private['method'] == 'client_secret_post':
            params['client_secret'] = private['client_secret']
        else:
            basic_auth = (client_id, private['client_secret'])
    result = json_request(metadata['token_endpoint'], params, form=True, basic_auth=basic_auth)
    access_token = result.get('access_token')
    if not isinstance(access_token, str) or not 1 <= len(access_token) <= 20000:
        raise ComputerError('O Commander não concluiu a autorização da BBLIA.', 401)
    return {'access_token': access_token, 'refresh_token': result.get('refresh_token'),
            'expires_in': result.get('expires_in', 3600), 'token_type': 'Bearer'}


class CommanderClient:
    def __init__(self, connection):
        if not isinstance(connection, dict) or not isinstance(connection.get('access_token'), str) or not 1 <= len(connection['access_token']) <= 20000:
            raise ComputerError('Conecte sua conta Commander no menu Computador e TV Box.', 401)
        self.token = connection['access_token']
        self.device_id = connection.get('device_id', '')
        self.session_id = None
        self.counter = 0
        self.definitions = {}
        self.call_ids = set()
        self.actions = []
        self.pending_calls = set()
        self.pending_processes = set()

    def rpc(self, method, params=None, notification=False):
        self.counter += 1
        message = {'jsonrpc': '2.0', 'method': method}
        if not notification:
            message['id'] = self.counter
        if params is not None:
            message['params'] = params
        headers = {'Authorization': 'Bearer '+self.token, 'Content-Type': 'application/json',
                   'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': '2025-03-26'}
        if self.session_id:
            headers['Mcp-Session-Id'] = self.session_id
        request = urllib.request.Request(MCP_URL, data=json.dumps(message).encode(), headers=headers)
        with open_request(request, timeout=45) as response:
            session_id = response.headers.get('Mcp-Session-Id')
            if session_id:
                self.session_id = session_id
            if notification:
                return {}
            if 'text/event-stream' in response.headers.get('Content-Type', ''):
                total = 0
                result = None
                for line in response:
                    total += len(line)
                    if total > 2000000:
                        raise ComputerError('A resposta do computador excedeu o tamanho permitido.', 502)
                    if line.startswith(b'data:'):
                        try:
                            item = json.loads(line[5:])
                        except ValueError:
                            continue
                        if item.get('id') == message['id']:
                            result = item
                            break
            else:
                raw = response.read(2000001)
                if len(raw) > 2000000:
                    raise ComputerError('A resposta do computador excedeu o tamanho permitido.', 502)
                result = json.loads(raw)
        if not isinstance(result, dict) or result.get('id') != message['id']:
            raise ComputerError('O Commander não confirmou a resposta desta chamada.', 502)
        if 'error' in result:
            raise ComputerError('A ferramenta do computador não concluiu a operação.', 502)
        return result.get('result', {})

    def initialize(self):
        self.rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                               'clientInfo': {'name': 'BBLIA', 'version': '1.0'}})
        self.rpc('notifications/initialized', notification=True)
        listing = self.rpc('tools/list')
        self.definitions = {item['name']: item for item in listing.get('tools', []) if item.get('name') in ALLOWED_TOOLS}
        return self

    def model_tools(self):
        if not isinstance(self.device_id, str) or not self.device_id:
            raise ComputerError('Selecione o computador autorizado no menu Computador e TV Box.')
        tools = []
        for name, definition in self.definitions.items():
            schema = copy.deepcopy(definition.get('inputSchema', {'type': 'object', 'properties': {}}))
            # Device selection is enforced by this server, not chosen by the model.
            schema.get('properties', {}).pop('deviceId', None)
            if 'required' in schema:
                schema['required'] = [key for key in schema['required'] if key != 'deviceId']
            tools.append({'type': 'function', 'name': 'pc_'+name,
                          'description': 'No computador selecionado: '+definition.get('description', name)[:4000],
                          'parameters': schema})
        return tools

    def call(self, name, args):
        if name not in self.definitions:
            raise ComputerError('Ferramenta de computador não autorizada.')
        if not isinstance(args, dict):
            raise ComputerError('Parâmetros da ferramenta inválidos.')
        arguments = copy.deepcopy(args)
        properties = self.definitions[name].get('inputSchema', {}).get('properties', {})
        if 'deviceId' in properties:
            arguments['deviceId'] = self.device_id
        elif 'deviceId' in arguments:
            arguments.pop('deviceId')
        if name == 'get_tool_result' and arguments.get('call_id') not in self.call_ids:
            raise ComputerError('Consulte apenas uma chamada iniciada neste trabalho.')
        result = self.rpc('tools/call', {'name': name, 'arguments': arguments})
        def collect(value):
            if isinstance(value, dict):
                if isinstance(value.get('call_id'), str):
                    self.call_ids.add(value['call_id'])
                for nested in value.values():
                    collect(nested)
            elif isinstance(value, list):
                for nested in value:
                    collect(nested)
            elif isinstance(value, str) and len(value) < 50000:
                # Some MCP servers include their asynchronous status in text.
                for match in re.findall(r'call_id[=":\s]+([a-zA-Z0-9-]{16,100})', value):
                    self.call_ids.add(match)
        collect(result)
        metadata=result.get('structuredContent') or {}
        asynchronous=metadata.get('async_call') or metadata
        call_id=asynchronous.get('call_id')
        state=asynchronous.get('status')
        if call_id and state in ('pending','queued','running','executing'):
            self.pending_calls.add(call_id)
        elif call_id and state in ('completed','failed','cancelled','terminated'):
            self.pending_calls.discard(call_id)
        output='\n'.join(c.get('text','') for c in result.get('content',[]) if c.get('type')=='text')
        for pid in re.findall(r'Process started with PID\s+(\d+)',output,re.I):
            self.pending_processes.add(int(pid))
        finished=re.findall(r'Process\s+(\d+)\s+has finished execution',output,re.I)
        for pid in finished:self.pending_processes.discard(int(pid))
        exit_match=re.search(r'Process completed with exit code\s+(-?\d+)',output,re.I)
        if exit_match and name=='read_process_output':self.pending_processes.discard(arguments.get('pid'))
        pending=bool(state in ('pending','queued','running','executing') or (name=='start_process' and not finished and self.pending_processes))
        confirmed=not result.get('isError',False) and not pending and not (exit_match and int(exit_match[1])!=0)
        self.actions.append({'tool': name, 'confirmed': confirmed,'pending':pending})
        result = copy.deepcopy(result)
        for content in result.get('content', []):
            if content.get('type') in ('image', 'audio'):
                content.pop('data', None)
                content['note'] = 'Mídia binária omitida da resposta textual.'
        text = json.dumps(result, ensure_ascii=False)
        return result if len(text) <= 60000 else {'truncated': True, 'text': text[:60000]}


def list_computers(data):
    client = CommanderClient(data).initialize()
    if 'list_devices' not in client.definitions:
        raise ComputerError('O Commander não informou a ferramenta de listar computadores.', 502)
    result = client.rpc('tools/call', {'name': 'list_devices', 'arguments': {}})
    return {'result': result, 'tools_available': sorted(client.definitions)}

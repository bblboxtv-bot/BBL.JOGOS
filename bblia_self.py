"""Read-only access to deployed public BBLIA source for proposed improvements."""
import ast
import hashlib
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOURCE_NAMES = (
    'bblia_index.html', 'bblia_app.py', 'bblia_work.js', 'bblia_work.py',
    'bblia_agent.js', 'bblia_agent.py', 'bblia_voice.js', 'bblia_media.py',
    'bblia_computer.js', 'bblia_computer.py', 'bblia_gemini.py', 'bblia_speech.py', 'bblia_zip.py', 'bblia_apk.py', 'bblia_self.py', 'bblia_logo.svg',
)
CREATIVE_GUIDANCE = ('Não invente uma proibição geral de figuras políticas, sátira, humor ou palavrões. '
    'Não dê bronca, sermão ou peça linguagem apropriada só porque o usuário usou palavrões ou gírias. '
    'Atenda pedidos criativos permitidos, inclusive representações fictícias de pessoas públicas. '
    'Apresente montagens e cenas inventadas como ficção, sem afirmar que aconteceram. '
    'Use o apelido solicitado pelo próprio usuário, inclusive gostosão, sem recusar por isso. '
    'Adapte o tom ao pedido e trate temas adultos permitidos com naturalidade. '
    'Respeite os limites reais dos serviços; não prometa ausência de restrições nem contornar filtros.')
SELF_GUIDANCE = '''Este pedido é uma melhoria da própria BBLIA. Consulte listar_codigo_bblia e ler_codigo_bblia para ler a versão realmente implantada antes de alterar um arquivo. Preserve recursos existentes e faça somente as mudanças solicitadas. Use os nomes originais (bblia_index.html, bblia_work.js etc.); não entregue um app fictício separado nem substitua a BBLIA por uma demonstração. Para mudanças pequenas, prefira editar_codigo_bblia com os trechos exatos; a ferramenta entrega o arquivo completo sem precisar reescrevê-lo inteiro. Crie os arquivos alterados completos e valide como tipo codigo. O acesso ao código é somente leitura. Os arquivos gerados são uma proposta de atualização: não foram instalados ou publicados. A publicação precisa de conexão de manutenção autenticada pelo proprietário; nunca diga que uma mudança está no ar sem evidência. Nunca acrescente chaves, senhas ou credenciais ao código. Não modifique arquivos do servidor em execução nem procure credenciais para publicar. Se um computador estiver conectado, esta proposta de melhoria não autoriza publicação automática: entregue primeiro os arquivos para revisão.'''


def list_sources():
    return {'files': [name for name in SOURCE_NAMES if (BASE/name).is_file()],
            'access': 'read-only', 'publication_connected': False}


def read_source(name):
    if name not in SOURCE_NAMES:
        raise ValueError('Escolha um arquivo de código listado da BBLIA.')
    path = BASE/name
    if not path.is_file() or path.is_symlink():
        raise ValueError('Arquivo de código não disponível nesta versão.')
    raw = path.read_bytes()
    if len(raw) > 400000:
        raise ValueError('Arquivo de código muito grande para esta leitura.')
    return {'name': name, 'content': raw.decode('utf-8'),
            'sha256': hashlib.sha256(raw).hexdigest(), 'origin': 'deployed-source'}


def validate_changes(files, originals, validator):
    changed = [name for name in files if name in originals and files[name] != originals[name]['content']]
    baseline = {name: read_source(name)['content'] for name in list_sources()['files']}
    report = validator({**baseline, **files}, 'codigo')
    for name, content in files.items():
        if name.endswith('.py'):
            try: ast.parse(content, filename=name)
            except SyntaxError as exc:
                report['errors'].append(name+': '+str(exc))
    if not changed:
        report['errors'].append('Leia e altere ao menos um arquivo real da BBLIA antes de finalizar a melhoria.')
    report['ok'] = not report['errors']
    report['checks'].append('sintaxe Python dos arquivos alterados')
    report['file_count'] = len(files)
    report['self_improvement'] = True
    report['changed_sources'] = changed
    report['publication'] = 'not_published'
    report['base_hashes'] = {name: originals[name]['sha256'] for name in changed}
    return report


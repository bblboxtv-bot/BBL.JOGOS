"""Adapt ordinary generated Activity code to the installed SDK, preserving event logic."""
import json
import re

IMPORTS = ('import android.app.Activity;import android.os.Bundle;import android.view.*;'
           'import android.widget.*;import android.content.*;import android.graphics.Color;import java.util.*;\n')
WIDGETS = {'TextView', 'Button', 'EditText', 'CheckBox', 'Switch', 'RadioButton', 'SeekBar', 'Spinner', 'ListView'}


def adapt_java(source, package, request=''):
    if not isinstance(source, str) or not source.strip() or len(source) > 150000:
        raise ValueError('Código Android vazio ou grande demais.')
    changes = []
    source = re.sub(r'^\s*package\s+[\w.]+\s*;', '', source, flags=re.M)
    source = re.sub(r'import\s+androidx\.appcompat\.app\.AppCompatActivity\s*;', '', source)
    source, count = re.subn(r'\b(?:androidx\.appcompat\.app\.)?AppCompatActivity\b', 'Activity', source)
    if count:
        changes.append('Activity padrão substituiu a classe de compatibilidade ausente.')
    if 'androidx.' in source:
        raise ValueError('Este aplicativo exige bibliotecas externas ainda não integradas ao compilador Java.')
    bindings = {}
    declarations = {name: kind for kind, name in re.findall(r'\b(' + '|'.join(WIDGETS) + r')\s+(\w+)\s*[;=]', source)}
    pattern = r'(?:(?:final\s+)?(?P<kind>\w+)\s+)?(?P<name>\w+)\s*=\s*(?:\(\s*\w+\s*\)\s*)?findViewById\s*\(\s*R\.id\.(?P<id>\w+)\s*\)'
    for match in re.finditer(pattern, source):
        kind = match.group('kind') or declarations.get(match.group('name'))
        if kind not in WIDGETS:
            raise ValueError('Tipo de componente não confirmado para ' + match.group('id'))
        if match.group('id') in bindings and bindings[match.group('id')] != kind:
            raise ValueError('O mesmo identificador foi usado com componentes diferentes.')
        bindings[match.group('id')] = kind
    layout_pattern = r'setContentView\s*\(\s*R\.layout\.\w+\s*\)\s*;'
    if re.search(layout_pattern, source):
        if len(re.findall(layout_pattern, source)) != 1 or not bindings:
            raise ValueError('Layout com múltiplas telas ou componentes não identificados precisa dos recursos completos.')
        lines = ['LinearLayout bbliaGeneratedLayout=new LinearLayout(this);',
                 'bbliaGeneratedLayout.setOrientation(LinearLayout.VERTICAL);',
                 'bbliaGeneratedLayout.setPadding(24,32,24,24);']
        is_counter = bool(re.search(r'contador|counter', request, re.I))
        initial = re.search(r'\b(?:int|long|double)\s+\w+\s*=\s*(-?\d+(?:\.\d+)?)\s*;', source)
        button_label = re.search(r'bot[aã]o\s+["“]?([A-Za-zÀ-ÿ]+)', request, re.I)
        for index, (ident, kind) in enumerate(bindings.items(), 0x010001):
            variable = 'bbliaGenerated_' + ident
            lines += [f'final {kind} {variable}=new {kind}(this);', f'{variable}.setId({index});']
            if kind == 'Button':
                label = button_label.group(1) if button_label and is_counter else ident.replace('_', ' ')
                lines.append(f'{variable}.setText({json.dumps(label, ensure_ascii=True)});')
            elif kind == 'TextView' and is_counter:
                lines.append(f'{variable}.setText({json.dumps(initial.group(1) if initial else "0")});')
                lines.append(f'{variable}.setTextSize(28);')
            lines.append(f'bbliaGeneratedLayout.addView({variable});')
        lines.append('setContentView(bbliaGeneratedLayout);')
        source = re.sub(layout_pattern, lambda _: '\n'.join(lines), source, count=1)
        for ident, kind in bindings.items():
            source = re.sub(r'(?:\(\s*' + kind + r'\s*\)\s*)?findViewById\s*\(\s*R\.id\.' + re.escape(ident) + r'\s*\)',
                            'bbliaGenerated_' + ident, source)
        for index, ident in enumerate(bindings, 0x010001):
            source = re.sub(r'\bR\.id\.' + re.escape(ident) + r'\b', str(index), source)
        changes.append('As views referenciadas no layout foram criadas em Java com os mesmos tipos e identificadores.')
    if re.search(r'\bR\s*\.', source):
        raise ValueError('O código ainda depende de recursos não entregues. Forneça o projeto Android completo.')
    if re.search(r'class\s+MainActivity\b', source):
        if not re.search(r'class\s+MainActivity\s+extends\s+Activity\b', source):
            raise ValueError('A atividade principal precisa estender Activity.')
        return 'package ' + package + ';\n' + IMPORTS + source, changes
    source = re.sub(r'^\s*import\s+[^;]+;', '', source, flags=re.M)
    if re.search(r'\bvoid\s+onCreate\b', source):
        raise ValueError('Corpo de atividade incompleto.')
    return ('package ' + package + ';\n' + IMPORTS + 'public class MainActivity extends Activity {'
            '@Override public void onCreate(Bundle savedInstanceState){super.onCreate(savedInstanceState);\n'
            + source + '\n}}'), changes

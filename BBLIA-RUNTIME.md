# Testes reais da lógica JavaScript

O modo Fazer por mim possui a ferramenta testar_javascript. Ela recebe nomes de arquivos já criados no projeto e um arquivo separado de testes. Os arquivos permanecem disponíveis para download. O servidor executa somente JavaScript no QuickJS-NG em processo separado, sem funções Python, módulos nativos, arquivos, DOM, rede ou variáveis do servidor expostas ao código.

Limites: uma execução por vez, 32 MB de heap JS, 256 KB de stack, 0,7 segundo por avaliação e quatro segundos de processo, até 8 fontes, 250 mil caracteres e 100 testes. O processo filho recebe ambiente mínimo, sem credenciais. Limites de CPU, memória e tamanho de arquivo do processo são aplicados no Linux. Não é um ambiente de navegador, Node, Python ou compilação Android.

O engine é instalado em diretório temporário dedicado a partir de rodas binárias quickjs-ng 0.18.0.1 do PyPI, com hashes SHA-256 fixados. Instalação em segundo plano no início do servidor mantém as funções existentes acessíveis. Se instalação/verificação falhar, a BBLIA informa indisponibilidade e não afirma execução. Não executar nenhum código recebido em Python nem usar subprocesso com código do projeto.

Exemplo logica.js:

```javascript
function total(itens) { return itens.reduce((n, i) => n + i.preco * i.quantidade, 0); }
```

Exemplo testes.js:

```javascript
test('carrinho vazio', () => assert.equal(total([]), 0));
test('quantidade em centavos', () => assert.equal(total([{preco:3500, quantidade:2}]), 7000));
```

Ao finalizar um projeto web com engine disponível, o agente precisa de testes aprovados correspondentes ao hash dos arquivos atuais. Mudanças após o teste invalidam o resultado. O relatório distingue testes de lógica, revisão estrutural e sintaxe; nunca comprova interface visual, API externa, banco, publicação, build ou instalação. Testes são escritos pelo agente e não provam correção completa.

Verificado localmente: sucesso e erro reais, timeout, limite de memória, ausência de bindings de rede/host, separação de contextos, indisponibilidade, invalidar resultado após alterações e ciclo do agente detectar falha/corrigir/retestar.

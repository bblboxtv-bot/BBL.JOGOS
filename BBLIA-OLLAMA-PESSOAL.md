# BBLIA pessoal: Google existente e processamento no computador

Esta alteração prepara a interface já publicada para usar o Ollama e as ferramentas Android do computador do proprietário. Não cria uma nova interface nem novos logins. `bblia_google.py` e `bblia_sync.py` permanecem intactos: autenticação e sincronização no Drive continuam nas rotas existentes.

## Componentes

- `bblia_local_relay.py`: fila autenticada no servidor; aceita pedidos somente da conta administradora já verificada pelo Google.
- `bblia_local_worker.py`: executor no Windows, com conexões de saída HTTPS. A porta do Ollama não é publicada.
- O executor usa a cópia local existente em `BBLIA-UNIFICADA-OLLAMA-TESTE/interface-original-local`, com Ollama, voz Windows/Vosk e compilador Android já instalados.
- `bblia_android_compat.py`: adapta Activity e views geradas para o SDK instalado, preservando a lógica dos eventos. Recursos não entregues e bibliotecas não suportadas geram erro explícito.
- `bblia_android_local_job.py`: geração, compilação, verificação de assinatura e entrega do APK. Projetos avançados com dependências e atualização de anexos não estão aprovados nessa rota.

## Ativação da versão de testes

1. Manter o serviço `bblia-teste` e o callback Google existentes. A branch ligada ao auto deploy não deve receber alterações sem aprovação do proprietário.
2. Disponibilizar os arquivos desta branch na versão de testes aprovada.
3. Configurar `BBLIA_LOCAL_RELAY_ENABLED=1` e uma chave aleatória privada `BBLIA_LOCAL_WORKER_KEY` com pelo menos 40 caracteres, idêntica no servidor e no executor Windows. Não salvar a chave no Git nem enviá-la em conversa.
4. No Windows, executar `python bblia_local_worker.py --runtime CAMINHO_DA_COPIA_LOCAL`. Essa cópia deve conter os módulos locais já preparados, as dependências de voz e o modelo português.
5. Entrar com o Google existente e validar chat, voz e APK nos aparelhos reais. O computador precisa ficar ligado para processar os pedidos.

Sem as duas variáveis de ativação, as rotas e o provedor anteriores continuam como estavam. Com a ponte habilitada, falhas do computador retornam erro explícito; não há fallback pago.

## Verificação

- 15 testes da ponte passaram: identidade do proprietário, segredo do executor, vínculo de lease, duplicação, modo offline, cancelamento, origem do navegador, upload/download com hash, proteção do download e provedor gratuito no executor.
- 5 testes do adaptador Android passaram, incluindo preservação do incremento e rejeição de recursos ausentes. Mais 3 testes verificaram progresso, cancelamento e integridade do stream de geração.
- Python compilou e os três arquivos JavaScript modificados passaram em `node --check`.
- Na suíte legada selecionada, 35 de 37 testes passaram. Os dois testes restantes também falham no código original do commit base: o fixture Google não cria identidade OpenID e o fixture de upload usa uma chamada sem autenticação. Não foram alterados para mascarar o resultado.

O fluxo local completo com `qwen2.5-coder:1.5b` gerou, compilou, assinou e entregou o APK de um contador em 201,62 segundos no computador autorizado. O hash do download foi conferido. O modelo de conversa foi preservado; o modelo de programação fica selecionável por `BBLIA_ANDROID_MODEL`. A instalação Android e o funcionamento no aparelho ainda não foram testados.

Os testes de autenticação e transporte usam identidades simuladas e arquivos de fixture onde indicado. Não comprovam login Google ao vivo, sincronização entre três aparelhos, qualidade do microfone real ou instalação Android. A aplicação em uso e a produção não foram alteradas nesta preparação.

Para preparar o modelo de programação, use `python bblia_prepare_coder.py` no computador com Ollama já instalado. O executor lê sua chave privada em `%LOCALAPPDATA%/BBLIA/worker-private.json`; esse arquivo não pertence ao repositório. `bblia_start_worker.py` inicia uma única instância e usa a cópia local existente.

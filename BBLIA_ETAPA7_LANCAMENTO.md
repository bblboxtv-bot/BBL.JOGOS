# BBLIA — Etapa 7: lançamento controlado

Estado: EM PREPARAÇÃO. Não liberar clientes ou cobranças reais antes de passar todos os critérios.

## Critérios de aceite

- [ ] Banco exclusivo da BBLIA persistente, com backup e teste de recuperação.
- [ ] Login Google e login por e-mail testados no celular e na TV Box; cadastro e recuperação de senha operacionais.
- [ ] Contas isoladas, sessão revogável, limitação de tentativas, administração protegida.
- [ ] Pagamento Pix aprovado e conciliado com provedor real, sem duplicar créditos; fluxo de reembolso definido.
- [ ] Custos por usuário e limites de uso configurados e testados; não prometer ilimitado sem orçamento.
- [ ] Compilação e assinatura de APK de produção; hash, versão, instalação e atualização testados.
- [ ] Android TV Box SDK 24 e celular testados, incluindo login, áudio, interrupção de fala e comandos autorizados.
- [ ] Fluxo completo do agente: pedido, execução, validação e entrega de arquivo APK.
- [ ] Telemetria, logs sem segredos, monitoramento, alertas e recuperação de indisponibilidade.
- [ ] Política de privacidade, termos, suporte, cancelamento e consentimentos preparados.
- [ ] Piloto com contas de teste e aprovação explícita antes de abertura pública.

## Isolamento

Não alterar BBL Box TV Launcher, painel, Oracle nem banco de dados da launcher.

## Situação verificada em 2026-11-07

- Testes locais de login e carteira passaram.
- Login por e-mail ainda não implantado na BBLIA pública.
- Banco persistente e Pix real não validados.
- APK SDK24 de teste instalado na TV Box, mas fluxo de login e autonomia não comprovados.

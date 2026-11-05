# Login e sincronização BBLIA

A conta da BBLIA usa a identidade Google (openid, email, profile) e o escopo drive.appdata para salvar dados no appDataFolder privado. Gmail, agenda e leitura do Drive continuam opcionais. O cadastro Google existente é reutilizado, com a mesma URL de callback.

## Fluxo do usuário

1. Menu → Minha conta e sincronização → Entrar com Google e ativar sincronização.
2. Autorizar identidade e armazenamento dos dados da BBLIA. Não é necessário autorizar Gmail/agenda para usar a conta.
3. Um espaço local separado é aberto para essa identidade. O histórico anterior do navegador não é enviado automaticamente: usar Importar conversas anteriores deste navegador quando desejar.
4. No outro aparelho, entrar na mesma conta. Usar Sincronizar agora e aguardar a confirmação.
5. A sincronização ocorre após alterações, ao voltar à janela, ao recuperar a internet e a cada minuto enquanto visível. Manter o app aberto até aparecer sincronizado. Falhas preservam os dados locais.

## Dados e isolamento

Cada conta usa uma chave IndexedDB account:<sub>. Visitantes usam state. Tokens permanecem no servidor e cookie HttpOnly; não entram nos backups. No Google Drive, cada navegador tem um snapshot privado no appDataFolder, contendo conversas, projetos, anexos vinculados e preferências. Limite de 18 MB, 200 projetos, 2000 conversas e 100 snapshots de aparelhos. Não há backup de arquivos externos apenas mencionados por URL.

Snapshots são unidos antes da gravação. Conversas simultâneas divergentes ganham cópia preservada; continuações normais não duplicam. Exclusões de conversas são registradas para evitar reaparecimento em outro aparelho. Preferências usam a atualização mais recente. Não há exclusão permanente dos snapshots antigos dos demais aparelhos pela interface; exportar backup permite recuperação manual de registros antigos que ainda estejam neles. Sair da conta neste aparelho encerra somente a sessão local; desconectar Google na central de conexões tenta revogar a autorização Google.

## Limitações operacionais

- Sessão Google em memória por até 12 horas; reinícios exigem novo login, mas os dados persistem no Google Drive.
- Um processo e uma instância Render. O lock de sincronização é local ao processo. Não escalar horizontalmente sem implementar coordenação distribuída/controle de versões.
- Armazenamento local não é criptografado com chave própria. Não compartilhar perfil do navegador. Dados no Drive obedecem às proteções e quota da conta Google.
- Não substitui login por senha, autenticação empresarial ou administração comercial de clientes.
- Google em modo de teste: manter usuários de teste cadastrados. Se solicitado pelo console, incluir openid, userinfo.email, userinfo.profile e drive.appdata nos acessos da aplicação.

## Validação

Testes de merge entre dispositivos, divergência, exclusão, credenciais excluídas, falha remota, identidade verificada por userinfo, alvo de escrita privado, isolamento local entre contas e rejeição de resposta atrasada de outra conta. Testes com Google real e dois aparelhos exigem a nova autorização do proprietário; não considerar concluídos só por aprovação dos testes automatizados.

Referências: https://developers.google.com/workspace/drive/api/guides/appdata e https://developers.google.com/identity/openid-connect/openid-connect

# Conexão Google da BBLIA

Implementado: OAuth com PKCE e estado vinculado ao navegador, cookies HttpOnly/Secure, sessões privadas, consulta e leitura de Gmail, próximos eventos da agenda principal, busca de arquivos e leitura de documentos Google/texto no Drive. Ferramentas disponíveis no chat após autorização. Botões de teste e desconexão em Ferramentas e conexões.

## Configuração externa pendente

1. No Google Cloud Console, selecionar/criar projeto para a BBLIA.
2. Ativar Gmail API, Google Calendar API e Google Drive API.
3. Configurar Google Auth Platform: nome BBLIA, contato do proprietário, público em teste e adicionar a conta do proprietário como usuário de teste. Não publicar acesso geral antes de cumprir os requisitos Google.
4. Criar cliente OAuth do tipo aplicação web. Cadastrar exatamente:
   - Origem: `https://bblia-teste.onrender.com`
   - Redirecionamento: `https://bblia-teste.onrender.com/google-callback`
5. No ambiente do serviço Render `bblia-teste`, cadastrar `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e `GOOGLE_REDIRECT_URI` (o redirecionamento acima). Nunca colocar segredo no repositório ou no chat. Implantar novamente após alterar o ambiente.
6. Na BBLIA, abrir Ferramentas e conexões → Conectar e gerenciar Google. Selecionar serviços, conectar e aceitar as permissões na tela Google. Usar Safari/Chrome externo, evitando navegador interno do Telegram.
7. Testar Gmail, agenda e Drive pelos botões; testar no chat “Consulte meus próximos compromissos”, “Busque meus e-mails” e “Procure no Drive o arquivo …”. Verificar acesso negado, desconexão e nova autorização.

Permissões solicitadas individualmente por serviço: `gmail.readonly`, `calendar.readonly`, `drive.readonly`. A autorização de teste do Google pode expirar. APIs Google e políticas de verificação podem impedir o acesso até a configuração ser concluída.

## Limites explícitos

- Não envia e-mails nem modifica eventos/arquivos. Leitura de anexos do Gmail não incluída.
- Sessões ficam em memória, por até 12 horas. Reinício do servidor exige reconectar. Tokens não entram em localStorage, backups ou respostas do chat.
- Dados consultados pelo chat são enviados ao provedor de IA para responder ao pedido, conforme aviso na interface.
- Sincronização de histórico/projetos entre aparelhos ainda não implementada. Não confundir conectar Drive com sincronização automática.
- Para sessões permanentes e sincronização, é necessário armazenamento persistente, identidade de usuário e armazenamento criptografado de credenciais.

Referência oficial: https://developers.google.com/identity/protocols/oauth2/web-server

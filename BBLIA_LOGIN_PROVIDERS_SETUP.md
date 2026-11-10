# BBLIA — ativação real dos três provedores (stage isolado)

Host: https://bblia-login-integrado-stage-20261109.onrender.com

**Atenção:** o código já possui rotas de login, mas não é possível completar OAuth/SMS sem credenciais válidas emitidas pelas plataformas. Nunca publicar segredos no GitHub, em mensagens ou em capturas de tela.

## Google Cloud Console
1. Selecionar/criar projeto Google Cloud e configurar tela de consentimento OAuth.
2. Criar **ID do cliente OAuth 2.0 → Aplicativo da Web**.
3. Em *Origens JavaScript autorizadas*, cadastrar:
   `https://bblia-login-integrado-stage-20261109.onrender.com`
4. Em *URIs de redirecionamento autorizados*, cadastrar exatamente:
   `https://bblia-login-integrado-stage-20261109.onrender.com/auth/google/callback`
5. Inserir no Render (Environment) `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `BBLIA_ISOLATED_GOOGLE_ORIGIN` e `BBLIA_ISOLATED_GOOGLE_OAUTH_ENABLED=1`.
6. Caso o aplicativo esteja em modo teste, adicionar os usuários de teste permitidos.

## Meta for Developers — Facebook Login
1. Criar/selecionar aplicativo Meta e habilitar Facebook Login para Web.
2. Em *Valid OAuth Redirect URIs*, cadastrar exatamente:
   `https://bblia-login-integrado-stage-20261109.onrender.com/auth/facebook/callback`
3. Inserir no Render `BBLIA_FACEBOOK_APP_ID`, `BBLIA_FACEBOOK_APP_SECRET`, `BBLIA_FACEBOOK_REDIRECT_URI`.
4. Verificar permissões, modo de desenvolvimento e usuários de teste antes do login.

## SMS — Twilio
1. Configurar conta Twilio e remetente SMS habilitado para os destinos de teste.
2. Inserir no Render `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`.
3. Gerar segredo aleatório de pelo menos 32 caracteres e inserir `BBLIA_OTP_SECRET` no Render.
4. Não habilitar o SMS real sem verificar custos, países permitidos e limites antifraude.

## Segurança, persistência e aceite
- O SQLite atual só é persistente com disco durável. No plano gratuito Render, **não presumir persistência após deploy/restart**; migrar sessões para armazenamento persistente antes de declarar 'manter login'.
- Estado de OAuth Facebook e OTP em memória não funciona corretamente com múltiplas instâncias/restarts. Migrar para armazenamento compartilhado antes de escala.
- Verificar isolamento de contas, cookie HttpOnly/Secure, logout e invalidação da sessão.
- Testar com **contas reais** cada provedor: iniciar login, concluir callback/OTP, verificar sessão, fechar/reabrir, sair e entrar novamente.
- `GET /api/auth/readiness` comprova apenas presença de configuração, não sucesso de autenticação.
- Manter `autoDeploy=no` até aprovação e não alterar serviços BBL.BOXTV.

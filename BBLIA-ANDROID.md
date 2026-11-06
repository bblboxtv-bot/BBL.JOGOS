# Compilação Android no computador conectado

A BBLIA pode obter a ferramenta confiável bblia_android_build.py no modo computador e usá-la pelo Commander selecionado. O helper usa Python e o Android SDK/JDK instalados, sem executar scripts Gradle de anexos. Pedidos por texto de execução no computador passam a encaminhar use_computer=true; criação de Android/APK/launcher usa o computador quando conectado e mantém criação de fontes quando não há conexão.

## Suporte desta versão

Java nativo (até 200 arquivos Java) ou projetos Gradle/Kotlin com Gradle, SDK/JDK e dependências disponíveis. O helper detecta o formato do projeto ou aceita --engine java/gradle. Para Java simples: manifesto em AndroidManifest.xml com Java em src/, ou app/src/main/AndroidManifest.xml com Java em app/src/main/java; recursos em res/ e assets/ opcionais. Prefere plataforma estável a preview. Em projetos com lambdas, usa o core-lambda-stubs.jar fornecido pelo SDK na compilação Java, sem empacotar esses stubs no aplicativo.

Pipeline real: AAPT2 recursos/manifesto → javac → D8 → zipalign → assinatura debug → verificar assinatura/alinhamento → verificar ZIP/DEX → hash SHA-256 e build-result.json. Cada execução usa pasta build-bblia/run-... nova. Não sobrescreve fontes nem limpa projetos. --smoke cria um aplicativo de diagnóstico próprio e rejeita sobrescrever um projeto existente. Não usar --smoke como substituto do aplicativo solicitado.

A chave debug é criada em uma pasta privada do usuário do computador, com credenciais padrão de teste. Não é chave de produção. O helper não instala aplicativos, não altera launcher, não formata, não limpa dados nem muda ROM. Instalação/execução usa ADB separadamente quando autorizada pela tarefa.

## Validação desta implementação

Em 05/11/2026, no computador Windows autorizado: Android SDK e JDK do Android Studio encontrados. Compilação real do aplicativo isolado com.bblia.compilacao.teste produziu APK de 8595 bytes; assinatura e alinhamento aprovados. O APK foi instalado via ADB na TV Box Android 9.0 e sua Activity iniciou com Status: ok. Processo confirmado vivo após a abertura. O aplicativo de diagnóstico não substitui a BBLIA ou a launcher existente.

O teste confirma o pipeline do helper e do aparelho. A autorização Commander é particular de cada navegador/usuário; não copiar tokens da conexão ChatGPT para a BBLIA. Resultados de chamadas iniciadas em background não são conclusão: acompanhar PID até final e conferir relatório/arquivo. A integração por texto possui teste de encaminhamento, bloqueio sem conexão e fallback para fontes.

Em 06/11/2026, o helper foi testado novamente com o código real da BBLIA Android 1.0.2, incluindo lambdas Java. A primeira tentativa identificou falta dos stubs de compilação; após a correção, produziu APK debug de 2.204.703 bytes, com assinatura e alinhamento verificados, pacote com.bbl.bblia, Android SDK 35 e build-tools 36.0.0. Esse APK debug é uma verificação do compilador, não a atualização a instalar sobre a versão assinada originalmente.

Separadamente, a BBLIA 1.0.2 de distribuição foi compilada com o script do aplicativo e a chave original preservada: 2.204.704 bytes, código de versão 3 e SHA-256 ed9557b1b475af50cc123dc1292729379002be5f17ccaae34ab716a203669534. O arquivo atravessou o envio e download da BBLIA com o mesmo hash. Nenhum aparelho estava conectado ao ADB nessa entrega, portanto não houve instalação nem teste funcional do OAuth num Android. O APK de distribuição e o código atualizado foram disponibilizados separadamente.

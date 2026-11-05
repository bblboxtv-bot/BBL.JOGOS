# Compilação Android no computador conectado

A BBLIA pode obter a ferramenta confiável bblia_android_build.py no modo computador e usá-la pelo Commander selecionado. O helper usa Python e o Android SDK/JDK instalados, sem executar scripts Gradle de anexos. Pedidos por texto de execução no computador passam a encaminhar use_computer=true; criação de Android/APK/launcher usa o computador quando conectado e mantém criação de fontes quando não há conexão.

## Suporte desta versão

Java nativo, sem Kotlin ou bibliotecas externas; até 200 arquivos Java. Manifesto em AndroidManifest.xml com Java em src/, ou app/src/main/AndroidManifest.xml com Java em app/src/main/java. Recursos em res/ e assets/ opcionais. Requer SDK, build-tools, JDK com javac e Python. Prefere plataforma estável a preview. Projetos Gradle/Kotlin/dependências precisam do ambiente Gradle adequado; não são compilados por este helper.

Pipeline real: AAPT2 recursos/manifesto → javac → D8 → zipalign → assinatura debug → verificar assinatura/alinhamento → verificar ZIP/DEX → hash SHA-256 e build-result.json. Cada execução usa pasta build-bblia/run-... nova. Não sobrescreve fontes nem limpa projetos. --smoke cria um aplicativo de diagnóstico próprio e rejeita sobrescrever um projeto existente. Não usar --smoke como substituto do aplicativo solicitado.

A chave debug é criada em uma pasta privada do usuário do computador, com credenciais padrão de teste. Não é chave de produção. O helper não instala aplicativos, não altera launcher, não formata, não limpa dados nem muda ROM. Instalação/execução usa ADB separadamente quando autorizada pela tarefa.

## Validação desta implementação

Em 05/11/2026, no computador Windows autorizado: Android SDK e JDK do Android Studio encontrados. Compilação real do aplicativo isolado com.bblia.compilacao.teste produziu APK de 8595 bytes; assinatura e alinhamento aprovados. O APK foi instalado via ADB na TV Box Android 9.0 e sua Activity iniciou com Status: ok. Processo confirmado vivo após a abertura. O aplicativo de diagnóstico não substitui a BBLIA ou a launcher existente.

O teste confirma o pipeline do helper e do aparelho. A autorização Commander é particular de cada navegador/usuário; não copiar tokens da conexão ChatGPT para a BBLIA. Resultados de chamadas iniciadas em background não são conclusão: acompanhar PID até final e conferir relatório/arquivo. A integração por texto possui teste de encaminhamento, bloqueio sem conexão e fallback para fontes.

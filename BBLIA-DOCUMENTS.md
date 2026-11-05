# Exportação de documentos

A ferramenta criar_documento no chat gera arquivos binários reais DOCX, XLSX, PPTX e PDF com bibliotecas dedicadas. Recebe apenas dados JSON estruturados, sem Python, templates ou execução de código do usuário. O arquivo é entregue com download, preservado no histórico e incluído corretamente em ZIPs. Alterações futuras podem usar os dados estruturados registrados na mensagem do artefato.

- Word/PDF: título e até 80 seções com título/texto.
- Excel: cabeçalhos, até 30 colunas e 2000 linhas, valores tipados, cabeçalho formatado e filtro. Não gera fórmulas nesta versão; conteúdo começando com = é texto.
- PowerPoint: até 30 slides 16:9, título de até 80 caracteres e corpo de até 700 caracteres/8 parágrafos. Tema escuro e texto editável.

Bibliotecas de formato são instaladas em segundo plano no diretório dedicado, via wheels com hashes SHA-256 e versões fixadas. Instalação indisponível retorna erro em vez de um documento falso. Criação acontece em subprocesso com ambiente mínimo, limite de CPU/memória e timeout. Máximo de 4 MB por arquivo. A criação usa o serviço de IA existente para elaborar conteúdo; não cria assinaturas externas novas.

Validação: DOCX, XLSX e PPTX reabertos pelas respectivas bibliotecas; contêiner ZIP verificado. PDF verifica estrutura. Testes locais extraem texto do PDF e verificam valores/células/slides. Não existe revisão visual automática da diagramação: fonte PDF padrão para texto latino, slides simples, sem gráficos, fórmulas, fotos ou modelos avançados. Integrações de Google Docs/Sheets/Slides não estão incluídas nesta exportação de arquivos.

Testes cobrem geração real dos quatro formatos, conteúdo em português, fórmulas neutralizadas, limites, caminhos, indisponibilidade e preservação dos bytes no download e ZIP.

# JURISRESUMO — Versão Nativa Portátil JavaScript (100% Offline)
**Autor:** FChNeto

Esta pasta contém a aplicação **JURISRESUMO** portada para arquitetura cliente 100% autônoma (HTML5 / CSS3 / JavaScript moderno), sem necessidade de instalação de Python, banco de dados ou terminal.

## Como Executar
1. Dê dois cliques em `index.html` ou em `ABRIR_APLICATIVO_DIRETO.html` (ou use o atalho `ABRIR_VERSAO_JAVASCRIPT.html` na raiz).
2. O aplicativo abrirá instantaneamente em qualquer navegador moderno (Chrome, Edge, Firefox).
3. Arraste o PDF dos autos integrais do PJe para a área de upload.
4. O motor analisa as peças (denúncia, decisões, mandados, histórico e rol de testemunhas) e gera a minuta com formatação Word e pré-visualização em tempo real.
5. Clique em **"Baixar Word (.docx)"** para obter o documento pronto.

## Estrutura da Pasta
- `index.html`: Aplicativo completo com interface Google Stitch / Nano Banana e motor de análise.
- `ABRIR_APLICATIVO_DIRETO.html`: Atalho de inicialização direta.
- `vendor/`:
  - `pdf.min.js` e `pdf.worker.min.js`: Motor de leitura e indexação de PDF.
  - `jszip.min.js`: Construtor de pacotes Word OpenXML (.docx).

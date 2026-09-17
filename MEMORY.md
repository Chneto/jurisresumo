# JURISRESUMO — MEMÓRIA TÉCNICA E GUIA DO PROJETO (AGENT MEMORY)

> **Documento Vivo de Memória e Conhecimento Técnico**  
> **Finalidade:** Orientar desenvolvedores e subagentes em futuras modificações, manutenções, refatorações e auditorias da aplicação.  
> **Última Atualização:** 17/09/2026 (Versão 2.5 — Folha A4 de Pré-Visualização Contínua sem Fundo Azul, Frontend Python com CSS Embutido e Integração Nativa Desktop Eel)
> **Autor e Desenvolvedor:** FChNeto

---

## 1. Visão Geral e Contexto de Negócio

### 1.1. Propósito da Aplicação
O **JURISRESUMO** é um sistema completo (Full-Stack / Desktop-Web) desenvolvido para auxiliar magistrados e assessores de Varas Criminais (com foco no TJRN / PJe) na **condução de audiências judiciais** (Instrução e Julgamento - AIJ, Acordo de Não Persecução Penal - ANPP, Produção Antecipada de Provas - PAnP e Audiência de Custódia).

A ferramenta recebe os **autos completos do processo em PDF** (gerados pelo sistema PJe) e gera uma minuta estruturada em **`.docx` (Microsoft Word)**, servindo como guia em tempo real para o magistrado durante o ato solene.

### 1.2. Regras de Domínio Inegociáveis (Diretrizes do Magistrado)
1. **Fatos da Denúncia (99% dos Casos):** O resumo dos fatos é rigorosamente o que consta na seção fática da denúncia ministerial. Não inventar ou alterar a narrativa fática. Realizar síntese concisa **apenas quando a denúncia for excessivamente longa**, preservando data, hora, local, dinâmica delitiva, apreensões de armas/bens, laudos periciais e interrogatório/confissão em sede policial com os respectivos IDs.
2. **Histórico Processual Cronológico:** Deve ser estritamente formatado como:
   `DD/MM/AA: [Descrição do Ato/Decisão/Manifestação] (ID [número])`
   - O texto da data e da descrição é **sempre regular (NUNCA em negrito)**.
   - O número do ID do PJe deve ser envelopado em um **hiperlink azul nativo** apontando diretamente para o documento no PJe.
3. **Rol de Testemunhas:**
   - Acusação e Defesa separadas e numeradas (`01) [Nome] - [Papel] - [Situação: Intimado / Ofício enviado / Contrafé negativa] (ID [número])`).
   - Se a defesa apenas reiterou o rol da acusação ou não indicou testemunhas, registrar a fórmula padrão: `A defesa requereu a oitiva de todas as testemunhas arroladas na denúncia.` ou `Não há testemunhas de defesa arroladas.`.
4. **Fechamento Formal:** Sempre terminar com a fórmula canônica judicial:
   `Cordial e respeitosamente,` (com recuo de primeira linha de 1,27 cm).

---

## 2. Engenharia Reversa dos Modelos DOCX (Especificação OpenXML Mined)

Com base na engenharia reversa dos 9 processos reais fornecidos na pasta (`Proc. 0801889-53`, `Proc. 0802487-75`, `Proc. 0804041-57`, `Proc. 0806049-87`, `Proc. 0820550-12`, `Proc. 0821902-39`, `Proc. 0844118-57`, `Proc. 0860849-94`, `Proc. 0876503-58`), a formatação física e tipográfica deve respeitar estritamente os seguintes parâmetros:

| Parâmetro | Valor Exato OpenXML | Valor Físico / Humano | Observações / Regra |
|---|---|---|---|
| **Tamanho da Página** | `w:w="11906" w:h="16838"` | **A4 Retrato** (21,0 x 29,7 cm) | Definido no `<w:sectPr>` de todas as seções. |
| **Margens** | `w:top="1134" w:bottom="1134" w:left="1134" w:right="1134"` | **2,00 cm** em todos os lados | Header e footer = 0. |
| **Família Tipográfica** | `w:rFonts w:ascii="Verdana" ...` | **Verdana** | Aplicado em 100% dos runs de texto. |
| **Tamanho da Fonte** | `w:sz w:val="24"` | **12 pt** | Tamanho fixo para títulos e corpo; hierarquia é feita por negrito e sublinhado. |
| **Entrelinhas Padrão** | `w:spacing w:line="454" w:lineRule="auto"` | **~1,89x (Amplo)** | Equivale a 22.7 pt de altura de linha. |
| **Espaçamento Posterior (Histórico e Testemunhas)** | `w:spacing w:after="283"` | **0,50 cm** (14.15 pt) | Dispensa parágrafos em branco intermediários. |
| **Recuo de Primeira Linha** | `w:ind w:firstLine="720"` | **1,27 cm** (0,5 polegada) | Aplicado na Qualificação, Fatos e Fechamento. |
| **Alinhamento Global** | `w:jc w:val="both"` | **Justificado** | 96% dos parágrafos do documento. |
| **Cor de Hiperlink** | `<w:color w:val="0000ff"/>` | **Azul (#0000ff)** | Sublinhado simples (`w:u w:val="single"`). |

### Estrutura Visual do Cabeçalho
1. **Título (P0):** `Proc. [Num] [Tipo] [Data] às [Hora]` — texto normal, **sublinhado simples**.
2. **Link (P1):** URL completa da sala do Teams/Meet em azul sublinhado (ou `Audiência Presencial` se não houver link virtual).
3. **Parágrafo em branco.**
4. **Chamada de Resumo (P3):** `Segue o resumo da audiência:` — texto **sublinhado simples**.
5. **Promotor:** `PROMOTOR: Dr. [Nome]` — **Negrito integral**.
6. **Réu(s):** `Réu: [Nome] - [situação] - Intimado ID [ID]` — **Negrito integral**, com o ID em hiperlink azul. Se múltiplos réus, encabeçado por `Réus:`.
7. **Defesa:** `Assistido pela Defensoria Pública - Dr. [Nome]` ou `Representado por advogado particular, Dr. [Nome] - OAB/[UF] [Num]` — **Negrito integral**.
8. **Parágrafo em branco.**

---

## 3. Engenharia de Ingestão de PDFs do PJe

### 3.1. Estrutura dos Autos Eletrônicos no PJe (TJRN)
- **Capa de Processo (Página 1):** Contém a tabela de partes e procuradores:
  - `(AUTOR)`: Ministério Público / Promotoria.
  - `(REU)` ou `(RÉU)`: Nome dos acusados.
  - `(VÍTIMA)`: Nome das vítimas.
  - `(TESTEMUNHA)`: Testemunhas arroladas na capa.
  - `(ADVOGADO)` ou `(DEFENSOR)`: Defensores habilitados.
- **Tabela de Documentos (TOC - Páginas 1..N):**
  - Colunas: `Id.`, `Data`, `Documento`, `Tipo`.
  - Mapeia cada ID de peça processual para sua data de protocolo e nome do ato.
- **Carimbos de Rodapé do PJe:**
  - Padrão oficial: `Num. <ID> - Pág. <P>` (ex.: `Num. 101573748 - Pág. 1`).
  - Permite mapear com exatidão a página inicial e final de cada peça jurídica dentro do PDF compilado.
- **Páginas Digitalizadas vs. Texto Vetorial:**
  - O PJe intercala documentos digitais nativos com peças escaneadas (inquéritos policiais físicos, laudos do ITEP, termos de busca e apreensão).
  - O módulo `app/core/ocr_engine.py` detecta dinamicamente a densidade de caracteres vetoriais e aciona OCR local (RapidOCR / Tesseract) sob demanda.

---

## 4. Arquitetura do Software e Layout de Arquivos

```
c:\Users\f201503\Documents\Resumo para audiência\
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI entrypoint, middleware CORS e montagem estática
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py               # Schemas Pydantic canônicos (HearingSummaryData, etc.)
│   │   ├── pje_indexer.py          # Parser de TOC, carimbos 'Num. ID' e poda seletiva
│   │   └── ocr_engine.py           # RapidOCR/Tesseract híbrido com detecção de scan
│   ├── engines/
│   │   ├── __init__.py             # Factory get_engine(mode, api_key)
│   │   ├── base.py                 # Classe base abstrata BaseExtractionEngine
│   │   ├── offline_engine.py       # Modo 2: Motor 100% Offline com regex e Capa PJe
│   │   └── gemini_engine.py        # Modo 1: Google Gemini AI com fallback seguro
│   ├── generators/
│   │   ├── __init__.py
│   │   └── docx_generator.py       # Construtor OpenXML/DOCX de alta fidelidade
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py               # Rotas REST (/upload, /extract, /generate-docx, /samples)
│   └── static/
│       ├── index.html              # Interface SPA (Google Stitch & Nano Banana)
│       ├── css/style.css           # Estilos visuais de alto contraste e simulação A4
│       └── js/app.js               # Gestão de estado reativo, edição e download
├── tests/
│   ├── conftest.py                 # Fixtures, constantes de namespace XML e metadados dos 9 casos
│   ├── test_pje_indexer.py         # 25 testes unitários do indexador
│   ├── test_docx_generator.py      # 2 testes de conformidade OpenXML/Word
│   ├── test_offline_engine.py      # 3 testes do motor offline e fallback
│   ├── test_api.py                 # 4 testes de integração dos endpoints FastAPI
│   ├── run_all_tests.py            # Dashboard CLI de execução de testes com métricas
│   └── e2e/
│       ├── test_e2e_tier1_features.py   # 100 testes cobrindo F01-F20
│       ├── test_e2e_tier2_boundaries.py # 16 testes de limites (ANPP, PAnP, multi-réu)
│       ├── test_e2e_tier3_cross_features.py # 9 testes cruzados de pipelines
│       └── test_e2e_tier4_workloads.py  # 10 testes de carga sobre os 9 processos
├── run.py                          # Launcher da aplicação (abre navegador e inicia Uvicorn)
├── recovery.py                     # Sistema nativo de checkpoints e restauração
├── MEMORY.md                       # Este documento (Memória Técnica Permanente)
├── PROJECT.md                      # Especificação arquitetural do projeto
└── requirements.txt                # Dependências Python
```

---

## 5. Como Operar o Sistema de Recuperação (`recovery.py`)

Como o ambiente Windows local não dispõe do Git, foi implementado o `recovery.py`, um sistema autônomo, seguro e de alta velocidade para criação de checkpoints e rollback instantâneo.

### Comandos Essenciais:

1. **Criar um novo Checkpoint:**
   ```powershell
   python recovery.py save "nome_do_ponto" -d "Descrição da alteração realizada"
   ```
   *Exemplo:* `python recovery.py save "feat_nova_secao" -d "Adicionada secao de antecedentes criminais"`

2. **Listar todos os Checkpoints salvos:**
   ```powershell
   python recovery.py list
   ```

   **Histórico de Checkpoints do Projeto:**
   | ID do Checkpoint | Rótulo | Finalidade / Escopo | Tamanho |
   |---|---|---|---|
   | `20260916_101709` | `v2.1_strict_formatting_highlights_fixed` | **Versão Atual Ativa**: Realces estritos amarelo/verde, negrito/itálico, hyperlinks PJe e motor offline aprimorado | ~111 KB |
   | `20260916_100805` | `pre_format_strict_highlight_fix` | Backup preventivo antes da padronização estrita de realces | ~108 KB |
   | `20260916_100020` | `v2.0_standalone_hamburger_dualscroll_fchneto` | Versão 2.0: Standalone HTML portátil, menu hambúrguer, dual scroll e autoria FChNeto | ~108 KB |
   | `20260916_095542` | `pre_user_enhancements` | Backup pré-solicitações de aprimoramento de UI do usuário | ~104 KB |
   | `20260916_093926` | `v1.1_memory_and_recovery_ready` | Implementação do sistema de recovery e arquivo MEMORY.md | ~104 KB |
   | `20260916_093852` | `v1.0_baseline_aprovada` | Versão baseline aprovada inicialmente pelo usuário | ~98 KB |

3. **Restaurar o projeto para um Checkpoint:**
   ```powershell
   python recovery.py restore "nome_do_ponto_ou_id"
   ```
   > **Garantia de Segurança Antiperda:** Antes de sobrescrever qualquer arquivo, o comando cria **automaticamente** um backup preventivo (`pre_restore_backup`), permitindo desfazer até mesmo restaurações acidentais.

4. **Comparar o estado atual com um Checkpoint (Diff):**
   ```powershell
   python recovery.py diff "nome_do_ponto_ou_id"
   ```
   *Mostra exatamente quais arquivos foram modificados, adicionados ou removidos.*

---

## 6. Como Executar a Suíte de Testes

O projeto conta com **170 testes automatizados** cobrindo todos os módulos com 100% de sucesso.

- **Execução completa via Runner com Dashboard:**
  ```powershell
  python tests/run_all_tests.py
  ```
- **Execução via Pytest padrão:**
  ```powershell
  python -m pytest tests/
  ```
- **Execução apenas dos testes de ponta a ponta (E2E):**
  ```powershell
  python -m pytest tests/e2e/
  ```

---

## 7. Recomendações para Subagentes e Futuros Desenvolvedores

1. **Antes de fazer qualquer alteração estrutural:**
   - Execute sempre: `python recovery.py save "pre_modificacao" -d "Antes de alterar componente X"`.
2. **Ao modificar a geração de DOCX:**
   - Nunca altere a fonte `Verdana` ou o tamanho `12pt`.
   - Lembre-se que no Histórico Processual, datas e textos são sempre **sem negrito**.
   - Mantenha o recuo de primeira linha de `1,27 cm` (`firstLine="720"`) nos blocos narrativos.
3. **Ao ajustar a leitura de PDFs:**
   - Sempre utilize `parse_capa_parties` para obter os nomes limpos das partes da Página 1, evitando confundir órgãos institucionais com réus.
   - Utilize `prune_documents` para descartar anexos pesados e focar nas decisões, denúncias e mandados.
4. **Após qualquer edição:**
   - Execute `python -m pytest tests/` para garantir que os testes continuem 100% aprovados.
   - Atualize este `MEMORY.md` com novos aprendizados ou comportamentos observados.

---

## 8. Recursos da Versão 2.0 (Desenvolvida por FChNeto)

### 8.1. Assinatura e Autoria Permanente
- **Autor Oficial:** `FChNeto`.
- A assinatura está registrada de forma perene no rodapé visual da aplicação web (`Desenvolvido por FChNeto • JURISRESUMO • TJRN`), nas tags `<meta name="author">` do HTML, e nas constantes `__author__ = "FChNeto"` e `DEVELOPED_BY = "FChNeto"` nos módulos:
  - `app/core/models.py`
  - `app/engines/offline_engine.py`
  - `app/generators/docx_generator.py`
  - `app/main.py`
  - `run.py`
  - `ABRIR_APLICATIVO_DIRETO.html`
  - `Iniciar_JURISRESUMO.vbs`

### 8.2. Versão Nativa Portátil Zero-Install (`ABRIR_APLICATIVO_DIRETO.html`)
- **Portabilidade Total:** Arquivo HTML nativo independente que roda em **qualquer dispositivo** (Windows, macOS, Linux, iPadOS, Android) sem requerer Python, Node.js, terminais ou telas pretas de carregamento.
- **Motor Client-Side Integrado:**
  - Extração de texto e metadados PJe via **PDF.js** diretamente no navegador.
  - Geração e empacotamento do documento `.docx` OpenXML binário nativo via **JSZip**, aplicando as mesmas regras de formatação (Verdana 12pt, margens 2,0cm, espaçamentos e links PJe).
  - Suporte aos modos 100% Offline (heurístico local em JavaScript) e IA Gemini (via chave de API configurada no drawer).

### 8.3. Inicializador Silencioso do Servidor Python (`Iniciar_JURISRESUMO.vbs`)
- Para usuários que desejam rodar o backend FastAPI local sem ver janelas pretas de prompt de comando (`cmd.exe`), o script `Iniciar_JURISRESUMO.vbs` inicializa o servidor em segundo plano de forma 100% silenciosa e abre o navegador na porta apropriada.

### 8.4. Correção Visual da Folha A4 e Rolagem Dupla Independente (Dual Scroll)
- **Viewport Fixo:** Altura travada em `calc(100vh - 92px); overflow: hidden;` eliminando barras de rolagem globais indesejadas.
- **Rolagem Independente:**
  - Coluna esquerda (`.editor-pane`): Rolagem vertical autônoma para edição de formulários longos.
  - Coluna direita (`.preview-pane`): O contêiner `.desk-scroller` rola verticalmente a folha A4.
- **Folha A4 Estrita Sem Sangramento Azul:**
  - `.word-paper-sheet` com fundo branco absoluto (`#ffffff !important`), `min-height: 1123px`, `height: auto`, e `padding: 20mm` (2,0 cm em todos os lados).
  - Texto longo expande a folha verticalmente sem cortes (`overflow: visible`), mantendo contraste preto no branco com sombra realista sobre a escrivaninha escura.

### 8.5. Menu Hambúrguer e Modal de Instruções
- **Menu Hambúrguer Superior Direito (`☰`):**
  - Abre gaveta deslizante (`.hamburger-drawer`) com seletor de motor (Modo IA vs. Modo Offline), inserção de chave Gemini API, backup/restauração de rascunhos em JSON e limpeza de dados.
- **Modal Explicativo ("Sobre o JURISRESUMO & Manual"):**
  - Explica detalhadamente o propósito judiciário, arquitetura híbrida, estrutura OpenXML fiel, privacidade dos dados e orientações de uso para magistrados e assessores criminais.
- **Área de Upload Expandida:** Remoção da seção de exemplos para deixar a tela 100% limpa para os processos reais do usuário.

---

## 9. Recursos da Versão 2.1 — Formatação Estrita Rigorosa e Motor Offline Aprimorado

### 9.1. Gramática Visual Estrita (Engenharia Reversa dos 9 Modelos Reais)
A partir da auditoria minuciosa de 100% dos arquivos de referência `.docx` fornecidos pelo magistrado, o sistema consolidou a seguinte padronização tipográfica e de cores, implementada tanto no gerador Python (`docx_generator.py`) quanto no gerador JSZip puro do navegador (`ABRIR_APLICATIVO_DIRETO.html`) e no preview web (`app.js`):

1. **Realce Amarelo (`w:highlight w:val="yellow"` / CSS `#ffff00`):**
   - Todos os títulos de seção: `QUALIFICAÇÃO`, `IMPUTAÇÃO`, `RESUMO DOS FATOS`, `HISTÓRICO PROCESSUAL`, `TESTEMUNHAS DE ACUSAÇÃO:`, `TESTEMUNHAS DE DEFESA:`.
   - Linha de chamada de horário/caso em audiências agendadas (ex.: `11h25min - 0860849-94.2026.8.20.5001 - ANPP`).
   - Nota padrão de testemunhas da defesa quando não há arrolamento novo (`A defesa requereu a oitiva de todas as testemunhas arroladas na denúncia.` ou `Não há testemunhas de defesa arroladas.`).

2. **Realce Verde Vivo (`w:highlight w:val="green"` / CSS `#00ff00`):**
   - Identificação dos atores da audiência:
     - `PROMOTOR: Dr. [Nome]` (ou `PROMOTORES:`)
     - `Réu: [Nome] - [situação] - Intimado ID [ID]` (ou `Réus:`)
     - Linha da Defesa (`Defesa: Dr. ...` / `Assistido pela Defensoria...` / `Representado por advogado...`)

3. **Negrito Estratégico (`<w:b/>`):**
   - Cabeçalhos de seção e linhas dos atores do ato solene.
   - Nome completo dos réus na abertura de sua qualificação, em caixa alta (ex.: `MANOEL PAULINO DA SILVA SOBRINHO`).
   - Artigos penais e normas jurídicas na imputação (ex.: `(art. 157, § 2º, II, e § 2º-A, I, do Código Penal)`).

4. **Itálico (`<w:i/>`):**
   - Notas e observações narrativas no resumo dos fatos (ex.: `OBS: este processo foi oriundo de um desmembramento...`).

5. **Hiperlinks Nativos em Todos os IDs:**
   - Todos os IDs numéricos (7 a 10 dígitos) no histórico processual, intimações de réus e rol de testemunhas são gerados como hiperlinks azuis (`#0000ff`) sublinhados apontando diretamente para o visualizador oficial do PJe TJRN.
   - No gerador client-side do navegador (`ABRIR_APLICATIVO_DIRETO.html`), os relacionamentos OpenXML são construídos dinamicamente em `word/_rels/document.xml.rels`, garantindo compatibilidade total com o Microsoft Word sem erros de integridade.

### 9.2. Aprimoramentos Críticos no Motor Offline
- **Resolução do Bug de Ancoragem de Regex:**
  - Em denúncias criminais do PJe, a qualificação frequentemente traz expressões como `"com 29 anos de idade à época dos fatos"`. Expressões regulares sem ancoragem de linha que buscavam por `DOS\s+FATOS` interceptavam indevidamente essa frase no meio da qualificação, truncando os dados civis do réu e sujando o resumo dos fatos.
  - O motor foi refatorado com âncoras estritas `(?:^|\n)\s*` e padrões específicos de cabeçalho (`DOS FATOS`, `HISTÓRICO DOS FATOS`, `DA IMPUTAÇÃO`), separando com precisão cirúrgica a qualificação, a tipificação penal e a narrativa ministerial.
- **Higienização Profunda de Textos do PJe (`_clean_legal_text`):**
  - Elimina carimbos verticais de margem, avisos de validação de assinatura digital (`Assinado eletronicamente por...`, `https://pje1g.tjrn.jus.br/...`), cabeçalhos de página e contagens de folhas que poluíam as minutas.
- **Rastreamento de Mandados de Intimação e Citação:**
  - Extração inteligente de IDs de mandados cumpridos e certidões de oficial de justiça a partir da tabela de documentos (TOC) e do corpo dos autos, mapeando o status de intimação de réus e testemunhas.

### 9.3. Checkpoint Salvo no Repositório
- **ID do Checkpoint:** `20260916_101709_v2_1_strict_formatting_highlights_fixed`
- **Rótulo:** `v2.1_strict_formatting_highlights_fixed`
- **Validação de Testes:** 170 testes unitários, de integração e ponta a ponta (E2E) aprovados com 100% de sucesso.

---

## 10. Matriz dos 9 Processos Reais da Pasta de Trabalho

Esta tabela consolida os 9 casos de teste e modelos de referência reais minerados no repositório, servindo como base de validação e calibração de futuros testes:

| Processo PJe | Ato | Data / Hora | Réu(s) | Situação Prisional | Total Págs | % Digitalizado | Peculiaridades Jurídicas |
|---|---|---|---|---|---|---|---|
| **0801889-53.2023.8.20.5001** | AIJ | 31.07.26 às 10h | JUCIMARCIA SOARES DA SILVA | Em liberdade | 119 págs | 10.1% | Furto qualificado, réu solto, Defensoria Pública |
| **0802487-75.2026.8.20.5300** | AIJ | 31.07.26 às 11h | GEAN | Réu preso | 209 págs | 14.4% | Tráfico de drogas, réu preso em estabelecimento prisional |
| **0804041-57.2022.8.20.5600** | PAnP | 23.07.26 às 13h | BERANILDO | Citado por edital | 212 págs | 20.3% | Produção Antecipada de Provas (Art. 366 CPP), citação ficta por edital |
| **0806049-87.2024.8.20.5001** | AIJ | 17.07.26 às 10h | LAIS, GUSTAVO, BIANCA, GIOVANNA | Em liberdade | 3.250 págs | 2.5% | Mega-processo GAECO / Operação policial, 4 acusados, 10 volumes |
| **0820550-12.2025.8.20.5001** | AIJ | 17.07.26 às 09h | HEVERTON DOUGLAS, ADRIANO MARTINS | Preso / Não localizado | 190 págs | 41.6% | Roubo majorado em concurso, alta densidade escaneada (41% OCR) |
| **0821902-39.2024.8.20.5001** | AIJ | 13.07.26 às 14h | LUANNA | Em liberdade | 1.166 págs | 19.5% | Inquérito policial extenso, múltiplos laudos periciais |
| **0844118-57.2025.8.20.5001** | AIJ | 24.07.26 às 11h | ABNER BARBOSA DA SILVA | Em liberdade | 336 págs | 2.4% | Receptação qualificada, histórico cronológico com 11 marcos processuais |
| **0860849-94.2026.8.20.5001** | ANPP | 24.07.26 às 11h25 | SAMARA TARGINO DE LIMA | Intimada | 480 págs | 0.6% | Acordo de Não Persecução Penal (Art. 28-A CPP), linha de chamada de horário |
| **0876503-58.2025.8.20.5001** | AIJ | 10.07.26 às 11h | MANOEL, JOSUEL, FELIPE | Intimados | 510 págs | 15.5% | Coautoria (3 réus), rol extenso de 17 IDs chave de certidões e mandados |

---

## 11. Protocolo Operacional para Subagentes e Desenvolvedores

Sempre que receber uma nova demanda de modificação do magistrado ou usuário, siga este protocolo rigoroso:

1. **Passo 1 — Criar Checkpoint de Segurança:**
   ```powershell
   python recovery.py save "pre_<tarefa>" -d "Backup preventivo antes de iniciar <tarefa>"
   ```
2. **Passo 2 — Preservar a Gramática Visual:**
   - Nunca remova os realces `<w:highlight w:val="yellow"/>` dos cabeçalhos ou `<w:highlight w:val="green"/>` dos participantes.
   - Sempre garanta que todo ID numérico de 7 a 10 dígitos gere um elemento `<w:hyperlink>` com a cor azul `#0000ff` e sublinhado.
   - Na versão autônoma (`ABRIR_APLICATIVO_DIRETO.html`), sempre espelhe as modificações do backend (`docx_generator.py` e `app.js`) para que o aplicativo portátil funcione com a mesma precisão.
3. **Passo 3 — Executar a Suíte de Testes:**
   ```powershell
   pytest tests/
   ```
   *Certifique-se de que todos os testes passem com 100% de sucesso.*
4. **Passo 4 — Atualizar Este Documento e Salvar o Checkpoint Final:**
   - Adicione o que foi aprendido em `MEMORY.md`.
   - Crie o checkpoint estável: `python recovery.py save "pos_<tarefa>" -d "<Descricao da solucao>"`.

---

## 12. Revisão e Aperfeiçoamento do Motor Offline (Versão 2.2)

### 12.1. Causa Raiz do Erro de Classificação de Audiência (AIJ vs. ANPP)
1. **O Falso Positivo "ANPP" e a Menção a Não Persecução:**
   - Na prática criminal brasileira (TJRN/PJe), quase a totalidade das denúncias e cotas ministeriais traz menções ao Acordo de Não Persecução Penal, comumente para **negar sua aplicação** (ex.: *"Deixo de propor o ANPP em razão da reincidência..."*, *"Incabível o ANPP diante da violência da conduta..."*, *"Não sendo caso de ANPP..."*).
   - O motor portátil (`ABRIR_APLICATIVO_DIRETO.html`) possuía anteriormente uma regra ingênua: `if (/anpp|não persecução/i.test(text)) actType = 'ANPP';`. Qualquer processo crime ordinário que citasse a negativa de ANPP era equivocadamente rebaixado para "ANPP", mesmo estando com denúncia recebida e audiência de instrução aprazada.
2. **O Truncamento em 100 Páginas no Frontend:**
   - No arquivo `ABRIR_APLICATIVO_DIRETO.html`, a leitura de PDF continha `const numPages = Math.min(pdf.numPages, 100);`.
   - Processos criminais com inquérito têm usualmente de 150 a 500 páginas. As primeiras 100 páginas contêm apenas o APF/IP e a Denúncia; o despacho judicial que efetivamente designa a Audiência de Instrução e Julgamento, bem como os mandados de intimação das testemunhas, ficam nas páginas finais (ex.: páginas 110-180). Cortar em 100 páginas impedia a leitura do ato judicial que marcou a audiência!
3. **Datas por Extenso em Português:**
   - Decisões judiciais frequentemente redigem a pauta por extenso (ex.: *"designo o dia 24 de julho de 2026 às 11:25"*). Expressões numéricas simples (`dd/mm/yyyy`) falhavam em capturar esses atos solenes.

### 12.2. Soluções Implementadas no Motor Offline e Frontend
1. **Hierarquia Jurídica Estrita para Tipificação do Ato:**
   - Se os autos contêm o recebimento da denúncia (`"recebo a denúncia"`, `"recebida a denúncia"`, `"art. 396"`, `"art. 399"`), o instituto do ANPP é juridicamente incompatível; o processo já ingressou na ação penal e a audiência é estritamente **AIJ**.
   - O tipo **ANPP** só é admitido se houver designação afirmativa unívoca de audiência de homologação do Art. 28-A do CPP, **sem qualquer recebimento posterior de denúncia** e **sem termos de recusa ou inadmissibilidade**.
   - O padrão seguro para processos criminais com denúncia recebida é **AIJ**.
2. **Leitura Completa de 100% das Páginas do PDF:**
   - Em `ABRIR_APLICATIVO_DIRETO.html`, a restrição de 100 páginas foi extirpada (`numPages = pdf.numPages`).
   - Implementado carregamento assíncrono em lotes paralelos (`Promise.all` em blocos de 10 páginas), permitindo leitura rápida e fluida de PDFs com 300-500 páginas em poucos segundos, exibindo o percentual exato ao usuário.
   - Em `app/core/pje_indexer.py`, implementada interpolação de páginas para peças da tabela de documentos com `start_page == 0`, garantindo cobertura de 100% dos autos.
   - Removido qualquer teto de retrocesso em `offline_engine.py` (anteriormente 60 páginas), varrendo agora todo o arquivo até a página 0.
3. **Varredura Reversa (Do Mais Recente para o Mais Antigo):**
   - No PJe, os despachos e pautas de audiência mais recentes estão no final dos autos. O motor agora varre as páginas de trás para frente para capturar prioritariamente o despacho que agendou a audiência ativa.
4. **Parser Nativo de Datas em Português:**
   - Reconhecimento completo de meses por extenso em português (`janeiro` a `dezembro`) com conversão para o padrão visual canônico: `24 de julho de 2026 às 11:25` $\rightarrow$ `24.07.26 às 11h25min`.
5. **Preservação Integral dos Fatos da Denúncia:**
   - Os fatos são extraídos sempre a partir da peça acusatória ministerial (denúncia), sem truncamentos arbitrários (`slice(0, 5)` ou `clean_den[200:1500]`), incorporando ainda menções de comprovação de materialidade e interrogatório/confissão em sede policial.

### 12.3. Checkpoint Salvo no Repositório
- **ID do Checkpoint:** `20260916_134935_v2_2_final_validated_all_cases`
- **Rótulo:** `v2.2_final_validated_all_cases`
- **Validação de Testes:** 173 testes unitários e de integração aprovados com 100% de sucesso.
- **Validação Cruzada em 100% dos Processos Reais da Pasta:**
  - `Proc. 0801889-53.2023.8.20.5001`: **AIJ**, 31.07.26 às 10h00min, Jucimarcia Soares da Silva
  - `Proc. 0802487-75.2026.8.20.5300`: **AIJ**, 31.07.26 às 11h00min, Gean de Lima Ferreira
  - `Proc. 0804041-57.2022.8.20.5600`: **PAnP**, 23.07.26 às 13h00min, Beranildo Alves Soares
  - `Proc. 0806049-87.2024.8.20.5001`: **AIJ**, 17.07.26 às 10h00min, 4 acusados
  - `Proc. 0844118-57.2025.8.20.5001`: **AIJ**, 24.07.26 às 11h00min, Glauco Barbosa da Silva
  - `Proc. 0820550-12.2025.8.20.5001`: **AIJ**, 17.07.26 às 09h00min, Heverton Douglas, Adriano
  - `Proc. 0821902-39.2024.8.20.5001`: **AIJ**, 10.07.26 às 09h30min, Luanna Karla
  - `Proc. 0860849-94.2026.8.20.5001`: **ANPP**, 24.07.26 às 11h25min, Samara Targino de Lima
  - `Proc. 0876503-58.2025.8.20.5001`: **AIJ**, 10.07.26 às 11h00min, Manoel, Josuel, Felipe

---

## 13. Padronização Estrita de Marcatexto e Eliminação de Fatos Desnecessários (Versão 2.3)

### 13.1. Regras de Marcação com Marcatexto (Highlighting Standards)
A partir da análise rigorosa dos modelos de resumo adotados pela magistratura criminal, foram estabelecidas as seguintes diretrizes estritas:
1. **Réus Múltiplos:**
   - Apenas o rótulo **`Réus:`** recebe realce verde-claro brilhante (`w:val="green"`, negrito).
   - As linhas individuais de cada acusado abaixo têm recuo (`left="720" hanging="360"` ou `padding-left: 1.27cm;`), texto regular (sem negrito) e **SEM NENHUM REALCE** (`highlight=None`). Apenas o número de ID de intimação/citação mantém o hiperlink azul sublinhado.
2. **Réu Único:**
   - A linha inteira `Réu: [Nome] - [situação] - Intimado ID [ID]` (ou `Ré:`) recebe realce verde (`w:val="green"`, negrito), com o ID preservado em azul.
3. **Corpo das Seções do Resumo:**
   - Os títulos das seções recebem realce amarelo (`QUALIFICAÇÃO`, `IMPUTAÇÃO`, `RESUMO DOS FATOS`, `HISTÓRICO PROCESSUAL`, `TESTEMUNHAS DE ACUSAÇÃO:`, `TESTEMUNHAS DE DEFESA:`).
   - O corpo das seções (parágrafos da qualificação, tipificação penal, narrativa dos fatos, itens cronológicos do histórico e lista de testemunhas) **NÃO POSSUI NENHUM REALCE**.
4. **Nota Defensiva de Testemunhas:**
   - Quando não há testemunhas de defesa ou houve reiteração do rol da acusação, a nota (ex.: `A defesa requereu a oitiva de todas as testemunhas arroladas na denúncia.`) recebe realce amarelo (`w:val="yellow"`, negrito).
5. **Estrutura Canônica de ANPP:**
   - Nos processos de Acordo de Não Persecução Penal (ANPP), as seções de **Qualificação, Imputação, Histórico Processual e Testemunhas são estritamente omitidas**, gerando um documento limpo e conciso voltado exclusivamente à homologação do acordo.

### 13.2. Eliminação de Fatos Desnecessários e Síntese Canônica
1. **Seleção Reversa da Denúncia Oficial do MP:**
   - Identifica a peça inaugural de acusação protocolada pelo Ministério Público, descartando manifestações avulsas de advogados privados e cotas preliminares.
2. **Delimitadores Rígidos de Início e Término:**
   - **Início:** Captura pontos de partida como `Consta nos/dos inclusos/referidos autos...`, `DOS FATOS`, `NARRATIVA FÁTICA` e `CONTEXTUALIZAÇÃO DA INVESTIGAÇÃO`.
   - **Parada:** Interrompe imediatamente ao encontrar fórmulas de encerramento (`Termos em que, pede...`, `pede e aguarda deferimento`, `Nestes termos`, `ROL DE TESTEMUNHAS`, `COTA`, `DOS PEDIDOS`, `REQUERIMENTOS`, `Diante do exposto requer`, `Assinaturas do Documento`).
3. **Limpeza de Cabeçalhos e Metadados Institucionais:**
   - Remove dados institucionais que poluíam o resumo (`MINISTÉRIO PÚBLICO`, `PROMOTORIA`, endereços de fórum/promotoria, telefones, links de validação e carimbos). Expressões como `Inquérito Policial nº`, `Autos nº` e `TCO nº` são ancoradas no início de linha para não corromper menções substantivas na narrativa.
4. **Refluxo e Condensação Inteligente:**
   - Reúne sentenças fragmentadas que encerram com pontuação canônica (`[.:;]`), garantindo que o resumo dos fatos mantenha entre 3 e 6 parágrafos substantivos de alta densidade informativa, acompanhados de notas periciais e interrogatório/confissão policial.
5. **Construtor Especializado para ANPP:**
   - Para audiências de ANPP, constrói exatamente os 6 parágrafos de referência: observação de desmembramento com número do processo originário, artigo do indiciamento com ID do IP, data e ID do termo firmado, condições pactuadas (prestação pecuniária, prestação de contas e não reiteração), data e ID da decisão de cisão, e data/horário e ID do despacho de designação da audiência.

### 13.3. Paridade Plena entre Ambientes (Python, Web e HTML Autônomo)
Todas as melhorias foram sincronizadas e validadas integralmente em:
- `app/generators/docx_generator.py` (Backend Python OpenXML)
- `app/engines/offline_engine.py` (Motor Heurístico Local)
- `app/static/js/app.js` (Interface Web FastAPI)
- `index.html` e `ABRIR_APLICATIVO_DIRETO.html` (Versão Portátil Zero-Instalação)
- Repositório de publicação `gitpost/` (GitHub Release)

---

## 14. Separação Física dos Aplicativos e Motor JavaScript Analítico de Alto Nível (Versão 2.4)

### 14.1. Separação Física em Pastas Distintas
Para garantir isolamento, autonomia e clareza de uso, o ecossistema JURISRESUMO foi reestruturado em dois ambientes independentes:

1. **`versao_python/` (Backend Completo Autônomo):**
   - Contém a aplicação Python integral com backend FastAPI, servidor Uvicorn, indexador de autos PJe (`pje_indexer.py`), motor analítico offline (`offline_engine.py`), motor Gemini (`gemini_engine.py`), gerador OpenXML (.docx) com estilos TJRN (`docx_generator.py`), frontend estático (`app/static/`), e suíte de testes completa (`tests/`).
   - Inicialização silenciosa via `Iniciar_JURISRESUMO.vbs` ou terminal via `python run.py`.
   - 100% autônomo e testado com 100% de aprovação (exit code 0 em todos os Tiers 1-4).

2. **`versao_javascript/` (Versão Nativa Portátil Zero-Instalação):**
   - Contém o aplicativo autônomo em HTML5 / CSS3 / JavaScript com bibliotecas locais em `vendor/` (`pdf.min.js`, `pdf.worker.min.js`, `jszip.min.js`), `index.html` e `ABRIR_APLICATIVO_DIRETO.html`.
   - Opera 100% no navegador do usuário sem necessidade de Python, Node.js ou terminal.

3. **Atalhos e Inicializadores na Raiz do Workspace:**
   - `ABRIR_VERSAO_PYTHON.vbs`: Inicializador silencioso do backend Python na pasta `versao_python`.
   - `ABRIR_VERSAO_JAVASCRIPT.html`: Redirecionador imediato para a versão portátil em `versao_javascript/index.html`.

### 14.2. Motor JavaScript Analítico de Alta Fidelidade (Análise Real dos Autos)
O motor JavaScript portátil foi profundamente reformulado para replicar a inteligência analítica jurídica desenvolvida no motor Python:
1. **Reconstrução Fidedigna de Linhas por Coordenadas (PDF.js):**
   - O extrator de texto do PDF.js agora agrupa os itens de texto com base no eixo Y e no eixo X de cada página, preservando quebras de linha essenciais para análise de parágrafos e cabeçalhos.
2. **Catalogação Completa (TOC) e Correlação com Carimbos Marginais:**
   - Analisa a Tabela de Documentos das páginas inaugurais (capa e índice de peças) para mapear `doc_id`, `date_str`, `doc_name` e `doc_type`.
   - Correlaciona com os carimbos de rodapé `Num. <ID> - Pág. <P>` de cada página, calculando o intervalo exato de páginas (`start_page` a `end_page`) e o texto integral de cada documento individual.
3. **Localização Precisa da Denúncia Ministerial:**
   - Varredura reversa no catálogo priorizando a peça inaugural do Ministério Público (`Denúncia`, `Queixa`, `Petição Inicial`), descartando expressamente cotas ministeriais, petições avulsas de defesa, certidões, antecedentes e extratos BNMP/SEEU.
4. **Análise e Síntese dos Fatos:**
   - Extração da narrativa ministerial delimitada rigidamente por termos de início (`Consta nos autos...`, `DOS FATOS`) e encerramento (`ROL DE TESTEMUNHAS`, `PEDIDOS`, `COTA`).
   - Identificação e incorporação automática de confissão/interrogatório policial e de laudos periciais e boletins de ocorrência que comprovam autoria e materialidade.
5. **Classificação Jurídica do Tipo de Ato (Hierarquia Processual Penal):**
   - Aplica a hierarquia estrita: PAnP (art. 366 CPP) $\rightarrow$ ANPP (homologação de acordo com exclusão de rejeição por `ANPP_NEGATION_REGEX`) $\rightarrow$ AIJ (designação de instrução e julgamento ou recebimento de denúncia + atos instrutórios) $\rightarrow$ Custódia $\rightarrow$ Sursis Processual.
6. **Estrutura Canônica de ANPP (6 Parágrafos Analíticos):**
   - Gera os 6 parágrafos analíticos de referência com identificação do processo originário desmembrado, indiciamento penal e ID do IP, data e ID do termo de acordo firmado, condições detalhadas do acordo (prestação pecuniária, prestação de contas e não reiteração), data e ID da decisão de cisão, e data/horário e ID do despacho de designação da audiência.
7. **Análise de Réus, Estabelecimentos Prisionais e Mandados:**
   - Varredura de estabelecimentos prisionais em todo o feito (`custodiado na...`, `penitenciária...`) para classificar réus presos com respectiva unidade prisional, réus soltos, citados por edital ou não localizados.
   - Cruzamento de nomes com mandados e certidões para preenchimento exato dos IDs de citação e intimação.
8. **Análise do Rol de Testemunhas e Situação Cumprida:**
   - Extração direta do `ROL DE TESTEMUNHAS` da denúncia ministerial com classificação do papel da testemunha (vítima, PM condutor, testemunha presencial).
   - Cruzamento com mandados e certidões para certificar cumprimento (`Intimada ID`, `Intimado ID`, `Ofício enviado ID` ou `Certidão contrafé negativa IDs ...`).
9. **Histórico Processual Substantivo:**
   - Poda documentos secundários e constrói resumo jurídico claro para cada marco processual relevante no formato canônico `DD/MM/AA: [Ato] (ID [número])`.
10. **Padrões Estritos de Marcatexto:**
    - Múltiplos réus: apenas o cabeçalho `Réus:` recebe realce verde (`w:val="green"`, negrito); itens individuais abaixo com recuo, sem negrito, sem realce e ID em azul.
    - Réu único: linha inteira com realce verde e ID em azul.
    - Títulos de seções em amarelo (`w:val="yellow"`) e corpo sem realce.
    - Nota defensiva em negrito com realce amarelo.
    - ANPP omite estritamente Qualificação, Imputação, Histórico e Testemunhas.

### 14.3. Correções Críticas de Extração e Validação nos 9 Processos Reais
1. **Caracteres Acentuados Maiúsculos em Nomes Próprios:**
   - A classe de caracteres foi atualizada para `[A-Za-záàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ]`, corrigindo o truncamento ou descarte de nomes com acentos maiúsculos (ex.: `FRANÇA`, `FÁTIMA`, `LÚCIA`, `JOSÉ`, `ÂNGELO MÁRCIO`).
2. **Cabeçalhos Quebrados em Múltiplas Linhas do ROL:**
   - Suporte a cabeçalhos como `Rol de\ndeclarante(s)\ne\ntestemunha(s)` comuns na comarca de Natal via `\s+` flexível e busca delimitada por tokens de parada (`COTA`, `Termos em que`, `Pede deferimento`).
3. **Tratamento Seguro de 'Requerimento de Denúncia':**
   - Ajuste no filtro de exclusão para não ignorar peças como `REQUERIMENTO DE DENÚNCIA` (`Proc. 0821902`), garantindo que petições com `requerimento` só sejam descartadas se não contiverem `denún`/`denun`.
4. **Eliminação de Fallbacks Hardcoded em ANPP:**
   - Todos os 6 parágrafos do ANPP são gerados dinamicamente a partir dos documentos reais do PJe (`termoDoc`, `cisaoDoc`, `despachoDoc`, `ipDoc`), sem valores mock ou IDs simulados.
5. **Validação Rigorosa em 100% dos Casos:**
   - Todos os 9 processos reais (`Proc. 0801889`, `Proc. 0802487`, `Proc. 0804041`, `Proc. 0806049`, `Proc. 0820550`, `Proc. 0821902`, `Proc. 0844118`, `Proc. 0860849`, `Proc. 0876503`) testados e aprovados com 100% de sucesso.

---

## 15. Atualizações da Versão 2.5 (Folha A4 Contínua e Desktop Eel no Python)

### 15.1. Resolução do Corte da Folha A4 no Preview (JavaScript e Python)
- **Causa Raiz Identificada:** Em contêineres flexbox com `display: flex; justify-content: center;`, a propriedade `align-items` assume por padrão o valor `stretch`. Sob a especificação CSS de rolagem vertical (`overflow-y: auto`), o elemento filho `.word-paper-sheet` tinha sua altura fixada ao viewport visível (~900px). Ao ultrapassar a primeira página com longas narrativas fáticas ou históricos extensos, o conteúdo interno do `#paper-body` transbordava para fora da folha, revelando o fundo azul/canvas da escrivaninha (`#0d121d`) atrás do texto.
- **Solução Arquitetural Aplicada:**
  - No container escrivaninha `.desk-scroller`: aplicação explícita de `align-items: flex-start;` e padding vertical ampliado (`padding: 2rem 1.5rem 4rem 1.5rem;`), libertando o item da restrição de altura do viewport.
  - No simulador da folha `.word-paper-sheet`: definição de `height: auto !important; min-height: 29.7cm; flex-shrink: 0; background: #ffffff !important; overflow: visible; margin: 0 auto 3rem auto;`.
  - No corpo `.paper-body`: definição de `width: 100%; height: auto; background: transparent;`.
- **Efeito Prático:** A folha branca expande-se dinamicamente por 2.000px, 5.000px ou quantas páginas forem necessárias, mantendo o fundo branco puro (`#ffffff`) e as margens estritas de 2,0 cm atrás de todos os parágrafos, sem qualquer exposição do fundo azul durante a rolagem.

### 15.2. Blindagem e Embutimento do CSS no Frontend Python
- **Causa Raiz:** O arquivo `versao_python/app/static/index.html` utilizava tag `<link rel="stylesheet" href="css/style.css">`. Quando aberto diretamente pelo usuário ou caso ocorresse qualquer falha na montagem de rotas estáticas do servidor web, o navegador renderizava o HTML cru com fontes Serif/Times New Roman e controles desformatados (conforme capturado na imagem enviada pelo magistrado).
- **Solução:** Embutimento integral de 1.142 linhas do sistema de design **Google Stitch & Nano Banana** diretamente dentro de `<style> ... </style>` no cabeçalho do `index.html`. Agora, seja via servidor FastAPI, janela Eel, ou abertura direta, a aplicação sempre carrega 100% formatada com os cards escuros, tipografia elegante e a folha A4 impecável.

### 15.3. Integração do Eel para Experiência Nativa de Desktop (Edge App Mode)
- **Novo Módulo `run_eel.py`:** Integração da biblioteca Python `eel` configurada para detectar automaticamente o executável do Microsoft Edge no Windows (`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` ou `C:\Program Files\Microsoft\Edge\Application\msedge.exe`) e inicializar a interface em modo de aplicativo (`--app`), sem barras de navegação ou abas de navegador.
- **Ponte Bidirecional Rápida (`@eel.expose`):**
  - `process_pdf_eel`: Recebe o arquivo PDF via base64, executa a extração direta no motor offline/Gemini e retorna o JSON estruturado instantaneamente.
  - `generate_docx_eel`: Recebe o JSON editado pelo usuário e gera o arquivo `.docx` via `docx_generator.py`, retornando os bytes codificados em base64 para download com um clique.
- **Frontend Híbrido e Resiliente (`app.js`):** O script detecta dinamicamente `if (typeof eel !== 'undefined')`. Em modo desktop Eel, utiliza a ponte Python direta; se iniciado via servidor FastAPI/Uvicorn, utiliza as rotas REST (`/api/upload` e `/api/generate-docx`).
- **Lançador Universal `run.py`:** Por padrão, `python run.py` ou os arquivos `.vbs` inicializam a janela nativa do Eel. Se for passado o parâmetro `--server` ou caso o Eel seja encerrado, o backend comuta com segurança para o servidor FastAPI/Uvicorn.


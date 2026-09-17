# JURISRESUMO — Sumarizador Inteligente de Autos do PJe para Audiências Criminais

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests Status](https://img.shields.io/badge/tests-173%20passed%20%7C%20100%25-brightgreen.svg)]()
[![Privacy](https://img.shields.io/badge/LGPD-100%25%20Offline%20Ready-success.svg)]()
[![PJe TJRN](https://img.shields.io/badge/PJe-TJRN%20Compatible-orange.svg)]()
[![Author](https://img.shields.io/badge/Desenvolvido%20por-FChNeto-blueviolet.svg)]()

> **Ferramenta de alta precisão para apoio ao Magistrado e assessoria jurídica na preparação e condução de audiências judiciais criminais.**

O **JURISRESUMO** realiza a ingestão dos autos processuais integrais em formato PDF (extraídos diretamente do sistema PJe) e gera minutas estruturadas no padrão oficial do Microsoft Word (`.docx`), guiando o juiz em tempo real durante o ato solene.

---

## ⚖️ Principais Finalidades e Recursos

* **Duplo Motor de Processamento:**
  * **Modo 100% Offline (Local e Seguro):** Opera com total privacidade (sem qualquer envio de dados pela rede), utilizando expressões regulares ancoradas na estrutura documental do PJe, OCR híbrido e heurísticas jurídicas avançadas.
  * **Modo IA (Google Gemini):** Integração com modelos generativos para síntese e correlação aprofundada em processos complexos.
* **Leitura Integral de 100% dos Autos do PDF:** Sem cortes de páginas; lê desde a capa do inquérito até as últimas intimações e despachos de pauta no final do processo.
* **Hierarquia Jurídica Estrita para Tipificação do Ato:**
  * **AIJ (Instrução e Julgamento):** Prioridade quando há recebimento de denúncia (Art. 396/399 CPP) e oitiva de testemunhas.
  * **ANPP (Acordo de Não Persecução Penal):** Reconhecimento preciso para audiências de homologação do Art. 28-A do CPP, diferenciando com exatidão despachos de homologação de meras cotas ministeriais que negaram o acordo.
  * **PAnP (Produção Antecipada de Provas):** Identificação automática em processos suspensos com citação por edital (Art. 366 CPP).
  * **Custódia:** Identificação pré-denúncia em autos de prisão em flagrante (APF).
* **Formatação Visual Idêntica aos Modelos Reais (`.docx`):**
  * **Marcatexto Amarelo e Verde Fiel:** Cabeçalhos de seção e notas destacadas em amarelo; promotor, réus e defesa destacados em verde claro.
  * **IDs do PJe com Hiperlinks Nativos:** Todos os IDs processuais de 7 a 10 dígitos convertidos em hiperlinks azuis sublinhados direcionando para a consulta do documento.
  * **Tipografia e Diagramação Canônica:** Fonte Verdana 12 pt, folha A4 com margens estritas de 2,0 cm, recuo de primeira linha de 1,27 cm e espaçamento entre linhas proporcional de 1,89x.
* **Versão Portátil Zero-Install:** Funciona diretamente pelo arquivo HTML nativo em qualquer computador, celular ou tablet, sem necessidade de instalar Python, Docker ou dependências.

---

## 🚀 Como Utilizar

Você pode utilizar o **JURISRESUMO** de duas formas simples:

### Opção 1: Uso Imediato Portátil (Nativo em JavaScript / Zero Instalação)
1. Dê um duplo clique no arquivo principal na raiz do repositório:
   ```text
   index.html
   ```
   *(ou no atalho `ABRIR_APLICATIVO_DIRETO.html`)*
2. O aplicativo abre instantaneamente no seu navegador web padrão (Chrome, Edge, Safari, Firefox).
3. **100% Offline e Autônomo:** Funciona imediatamente após o download do GitHub, mesmo sem conexão com a internet, pois as bibliotecas necessárias de extração de PDF e geração OpenXML `.docx` estão incorporadas localmente na pasta `vendor/`.
4. Arraste o arquivo PDF dos autos completos do PJe para a tela.
5. O resumo estruturado será extraído em segundos e exibido no simulador de folha A4.
6. Clique em **Exportar Documento Word (.docx)** para baixar a minuta formatada com marcatextos e links.

---

### Opção 2: Uso com Servidor Web Local (Python)

#### Pré-requisitos:
* Python 3.10 ou superior instalado no sistema.

#### Instalação das dependências:
```powershell
pip install -r requirements.txt
```

#### Inicialização Silenciosa (Windows - Sem tela preta):
Dê um duplo clique em:
```text
Iniciar_JURISRESUMO.vbs
```

#### Ou inicialização via terminal:
```powershell
python run.py
```
Acesse no seu navegador: `http://127.0.0.1:8000`

---

## 🏛️ Estrutura das Seções do Resumo

A minuta gerada obedece com rigor à seguinte ordem:

1. **Cabeçalho:**
   * Número do Processo, Tipo de Audiência (AIJ, ANPP, etc.), Data e Horário.
   * Link da sala virtual do Microsoft Teams/Google Meet (ou indicação de Audiência Presencial).
   * Linha de resumo: `Segue o resumo da audiência:`.
   * Promotor de Justiça titular ou substituto.
   * Relação de réus com status prisional e ID do mandado de intimação.
   * Defesa técnica (Defensoria Pública ou Advogado constituído com OAB).
2. **QUALIFICAÇÃO:**
   * Nome completo em caixa alta e negrito, nacionalidade, estado civil, profissão, RG, CPF, filiação e endereço residencial.
3. **IMPUTAÇÃO:**
   * Tipificação penal exata com artigos e parágrafos destacados em negrito.
4. **RESUMO DOS FATOS:**
   * Narrativa fática completa da denúncia ministerial (em 99% dos casos); síntese concisa em denúncias excessivamente longas, mantendo data, local, laudos periciais de materialidade e interrogatório/confissão policial.
5. **HISTÓRICO PROCESSUAL:**
   * Linha do tempo em ordem cronológica dos atos processuais relevantes:
     `DD/MM/AA: [Descrição do Ato/Decisão/Manifestação] (ID [número])`
6. **TESTEMUNHAS DE ACUSAÇÃO E DEFESA:**
   * Relação numerada com nome, papel (vítima, policial militar, testemunha presencial) e status de intimação com o respectivo ID.
   * Requerimento da defesa técnica (reiteração do rol ou testemunhas próprias).
7. **Fechamento:**
   * Fórmula oficial de encerramento respeitoso: `Cordial e respeitosamente,`.

---

## 📁 Estrutura do Repositório

```
├── .github/workflows/ci.yml       # Pipeline automatizado de testes (CI/CD)
├── app/
│   ├── api/routes.py              # Endpoints FastAPI (/upload, /extract, /generate-docx)
│   ├── core/models.py             # Esquemas de dados canônicos Pydantic
│   ├── core/pje_indexer.py        # Parser de TOC, carimbos 'Num. ID' e poda seletiva
│   ├── core/ocr_engine.py         # OCR híbrido (RapidOCR / Windows OCR / Tesseract)
│   ├── engines/offline_engine.py  # Motor 100% Offline com hierarquia penal
│   ├── engines/gemini_engine.py   # Motor com Google Gemini AI
│   ├── generators/docx_generator.py # Construtor OpenXML/DOCX fiel
│   └── static/                    # Interface Google Stitch & Nano Banana (CSS e JS)
├── vendor/                        # Bibliotecas JavaScript locais (100% offline)
│   ├── pdf.min.js                 # Parser PDF Mozilla
│   ├── pdf.worker.min.js          # Web Worker local
│   └── jszip.min.js               # Construtor de arquivos DOCX OpenXML
├── tests/                         # Suíte completa com 173 testes automatizados
├── index.html                     # Aplicativo nativo JavaScript/HTML5/CSS3 (Execução Imediata)
├── ABRIR_APLICATIVO_DIRETO.html   # Atalho portátil zero-install
├── Iniciar_JURISRESUMO.vbs        # Launcher invisível para Windows (modo servidor local)
├── run.py                         # Ponto de entrada do backend Python
├── recovery.py                    # Sistema de checkpoints e restauração
├── requirements.txt               # Dependências Python (opcional para modo servidor)
├── README.md                      # Esta documentação
└── LICENSE                        # Licença MIT (Autor: FChNeto)
```

---

## 🧪 Suíte de Testes Automatizados

Para executar todos os testes da aplicação:
```powershell
pytest tests/ -v
```
Todos os 173 testes cobrem a integridade dos parsers, a geração fiel de documentos OpenXML, a distinção penal entre AIJ e ANPP e a interface de ponta a ponta.

---

## 🔒 Conformidade com a LGPD e Segurança Forense

O **JURISRESUMO** foi projetado sob os princípios de *Privacy by Design* e estrita conformidade com a **Lei Geral de Proteção de Dados (Lei nº 13.709/2018)**:
* No **Modo Offline**, nenhum dado ou texto processual sai do computador do usuário.
* O repositório público não armazena arquivos de processos judiciais reais ou dados pessoais sensíveis de partes processuais.
* Chaves de API configuradas no Modo IA são salvas exclusivamente no armazenamento local (`localStorage`) do navegador do usuário.

---

## 👨‍⚖️ Autoria e Licença

* **Desenvolvido por:** **FChNeto**
* **Finalidade:** Apoio à condução de audiências do Poder Judiciário (Varas Criminais).
* **Licença:** Distribuído sob a licença [MIT](LICENSE).

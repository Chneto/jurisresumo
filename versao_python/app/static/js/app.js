/**
 * JURISRESUMO - Google Stitch & Nano Banana Client Engine
 * Desenvolvido por FChNeto
 *
 * Sistema reativo para ingestão de autos do PJe, edição interativa
 * e geração de minutas DOCX para audiências judiciais.
 */

const APP_AUTHOR = "FChNeto";
const PJE_DOC_URL_TEMPLATE = "https://pje1g.tjrn.jus.br/pje/Processo/ConsultaProcesso/Detalhe/documentoHTML.seam?idBin=";

document.addEventListener('DOMContentLoaded', () => {
  // State
  let currentEngineMode = localStorage.getItem('juris_engine_mode') || 'offline';
  let geminiApiKey = localStorage.getItem('juris_gemini_api_key') || '';
  let activeData = null;
  let originalData = null;

  // DOM Elements - Header & Navigation
  const btnExportDocx = document.getElementById('btn-export-docx');
  const btnHamburger = document.getElementById('btn-hamburger');
  const drawerBackdrop = document.getElementById('drawer-backdrop');
  const hamburgerDrawer = document.getElementById('hamburger-drawer');
  const btnCloseDrawer = document.getElementById('btn-close-drawer');
  const headerEngineDot = document.getElementById('header-engine-dot');
  const headerEngineLabel = document.getElementById('header-engine-label');

  // Drawer Elements
  const radioOffline = document.querySelector('input[name="drawer_engine_mode"][value="offline"]');
  const radioGemini = document.querySelector('input[name="drawer_engine_mode"][value="gemini"]');
  const cardOffline = document.getElementById('card-mode-offline');
  const cardGemini = document.getElementById('card-mode-gemini');
  const inputDrawerKey = document.getElementById('input-drawer-gemini-key');
  const btnSaveDrawerKey = document.getElementById('btn-save-drawer-key');
  const btnSaveDraft = document.getElementById('btn-save-draft');
  const inputLoadDraft = document.getElementById('input-load-draft');
  const btnClearForm = document.getElementById('btn-clear-form');
  const btnOpenAbout = document.getElementById('btn-open-about');

  // About Modal
  const modalAboutBackdrop = document.getElementById('modal-about-backdrop');
  const btnCloseAbout = document.getElementById('btn-close-about');
  const btnCloseAboutBtn = document.getElementById('btn-close-about-btn');

  // Ingestion & Upload
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const uploadLoading = document.getElementById('upload-loading');

  // Form & Preview
  const form = document.getElementById('hearing-form');
  const btnRevert = document.getElementById('btn-revert');
  const factsCharCount = document.getElementById('facts-char-count');
  const paperBody = document.getElementById('paper-body');
  const paperPlaceholder = document.getElementById('paper-placeholder');

  // Dynamic Item Containers
  const defsContainer = document.getElementById('defendants-container');
  const historyContainer = document.getElementById('history-container');
  const prosWitnessContainer = document.getElementById('pros-witnesses-container');

  const btnAddDef = document.getElementById('btn-add-defendant');
  const btnAddHist = document.getElementById('btn-add-history');
  const btnAddWit = document.getElementById('btn-add-witness');

  // Initialize UI State
  initEngineState();

  // Engine Setup
  function initEngineState() {
    inputDrawerKey.value = geminiApiKey;

    if (currentEngineMode === 'gemini') {
      radioGemini.checked = true;
      cardGemini.classList.add('active');
      cardOffline.classList.remove('active');
      headerEngineDot.className = 'engine-dot ai-dot';
      headerEngineLabel.innerText = 'Modo IA Gemini (Análise Jurídica)';
    } else {
      radioOffline.checked = true;
      cardOffline.classList.add('active');
      cardGemini.classList.remove('active');
      headerEngineDot.className = 'engine-dot offline-dot';
      headerEngineLabel.innerText = 'Modo 100% Offline (Local Seguro)';
    }
  }

  function setEngineMode(mode) {
    currentEngineMode = mode;
    localStorage.setItem('juris_engine_mode', mode);
    initEngineState();
    if (mode === 'gemini' && !geminiApiKey) {
      showToast('Modo IA ativado. Configure sua chave Gemini nas opções.', 'success');
    } else {
      showToast(`Motor alterado para: ${mode === 'gemini' ? 'IA Gemini' : 'Offline Local'}.`, 'success');
    }
  }

  radioOffline.addEventListener('change', () => setEngineMode('offline'));
  radioGemini.addEventListener('change', () => setEngineMode('gemini'));
  cardOffline.addEventListener('click', () => setEngineMode('offline'));
  cardGemini.addEventListener('click', () => setEngineMode('gemini'));

  btnSaveDrawerKey.addEventListener('click', () => {
    geminiApiKey = inputDrawerKey.value.trim();
    localStorage.setItem('juris_gemini_api_key', geminiApiKey);
    showToast('Chave da API Gemini salva localmente no navegador.', 'success');
  });

  // Hamburger Drawer Toggles
  btnHamburger.addEventListener('click', () => {
    hamburgerDrawer.classList.add('active');
    drawerBackdrop.classList.add('active');
  });

  function closeDrawer() {
    hamburgerDrawer.classList.remove('active');
    drawerBackdrop.classList.remove('active');
  }

  btnCloseDrawer.addEventListener('click', closeDrawer);
  drawerBackdrop.addEventListener('click', closeDrawer);

  // About Modal Toggles
  btnOpenAbout.addEventListener('click', () => {
    closeDrawer();
    modalAboutBackdrop.classList.add('active');
  });

  function closeAboutModal() {
    modalAboutBackdrop.classList.remove('active');
  }

  btnCloseAbout.addEventListener('click', closeAboutModal);
  btnCloseAboutBtn.addEventListener('click', closeAboutModal);
  modalAboutBackdrop.addEventListener('click', (e) => {
    if (e.target === modalAboutBackdrop) closeAboutModal();
  });

  // Draft Management (Save/Load/Clear)
  btnSaveDraft.addEventListener('click', () => {
    if (!activeData) {
      showToast('Nenhum dado ativo para exportar rascunho.', 'error');
      return;
    }
    syncDataFromForm();
    const jsonStr = JSON.stringify(activeData, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const safeNum = (activeData.case_number || 'processo').replace(/[\/\\]/g, '-');
    a.download = `Rascunho_Resumo_${safeNum}.json`;
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
    a.remove();
    showToast('Rascunho JSON salvo com sucesso.', 'success');
    closeDrawer();
  });

  inputLoadDraft.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const data = JSON.parse(event.target.result);
        loadDataIntoUI(data);
        showToast('Rascunho carregado com sucesso!', 'success');
        closeDrawer();
      } catch (err) {
        showToast('Arquivo de rascunho JSON inválido.', 'error');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  });

  btnClearForm.addEventListener('click', () => {
    if (confirm('Tem certeza de que deseja limpar todos os campos do formulário?')) {
      activeData = null;
      originalData = null;
      form.reset();
      defsContainer.innerHTML = '';
      historyContainer.innerHTML = '';
      prosWitnessContainer.innerHTML = '';
      btnExportDocx.disabled = true;
      updateLivePreview();
      showToast('Formulário limpo com sucesso.', 'success');
      closeDrawer();
    }
  });

  // Drag & Drop Upload
  dropzone.addEventListener('click', () => fileInput.click());

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileUpload(e.target.files[0]);
    }
  });

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result;
        const base64 = result.substring(result.indexOf(',') + 1);
        resolve(base64);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  function updateProgressPhase(phaseNumber, stepText, subText, percent) {
    const stepEl = document.getElementById('stitch-progress-step');
    const subEl = document.getElementById('stitch-progress-sub');
    const fillEl = document.getElementById('stitch-progress-fill');
    if (stepEl && stepText) stepEl.textContent = stepText;
    if (subEl && subText) subEl.textContent = subText;
    if (fillEl && percent !== undefined) fillEl.style.width = `${percent}%`;

    for (let i = 1; i <= 4; i++) {
      const chip = document.getElementById(`phase-chip-${i}`);
      if (chip) {
        if (i < phaseNumber) {
          chip.className = 'phase-chip completed';
        } else if (i === phaseNumber) {
          chip.className = 'phase-chip active';
        } else {
          chip.className = 'phase-chip';
        }
      }
    }
  }

  async function handleFileUpload(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      showToast('Por favor, selecione um arquivo em formato PDF do PJe.', 'error');
      return;
    }

    uploadLoading.classList.add('active');
    updateProgressPhase(1, 'Indexando catálogo de documentos (TOC) e carimbos Num. ID...', 'Mapeamento de capa, réus e catalogação de peças', 25);

    const timer1 = setTimeout(() => {
      updateProgressPhase(2, 'Otimizando contraste e calibrando OCR...', 'Otsu adaptativo, detecção de margens dinâmicas e RapidOCR', 50);
    }, 600);

    const timer2 = setTimeout(() => {
      updateProgressPhase(3, 'Executando decisão System One (JEV/Leya)...', 'Classificação de peças, descarte de carimbos e comprovantes bancários', 75);
    }, 1500);

    try {
      let data = null;
      if (typeof eel !== 'undefined' && eel.process_pdf_eel) {
        // Modo Desktop Nativo via Eel
        const base64 = await fileToBase64(file);
        const res = await eel.process_pdf_eel(base64, file.name, currentEngineMode, geminiApiKey || null)();
        if (res.error) {
          throw new Error(res.error);
        }
        data = res.data;
        updateProgressPhase(4, 'Sintetizando fatos e formatando folha A4 contínua...', 'Padronização OpenXML TJRN e hiperlinks nativos PJe', 100);
        loadDataIntoUI(data);
        showToast(`Processo ${data.case_number || 'sintetizado'} com sucesso via Motor Desktop!`, 'success');
      } else {
        // Modo Web padrão via FastAPI
        const formData = new FormData();
        formData.append('file', file);
        formData.append('engine_mode', currentEngineMode);
        if (geminiApiKey) formData.append('api_key', geminiApiKey);

        const response = await fetch('/api/upload', {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          const err = await response.json();
          throw new Error(err.detail || 'Falha ao processar os autos do PJe.');
        }

        data = await response.json();
        updateProgressPhase(4, 'Sintetizando fatos e formatando folha A4 contínua...', 'Padronização OpenXML TJRN e hiperlinks nativos PJe', 100);
        loadDataIntoUI(data);
        showToast(`Processo ${data.case_number} sintetizado com sucesso!`, 'success');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      clearTimeout(timer1);
      clearTimeout(timer2);
      uploadLoading.classList.remove('active');
      fileInput.value = '';
    }
  }

  // Load Data into UI
  function loadDataIntoUI(data) {
    originalData = JSON.parse(JSON.stringify(data));
    activeData = JSON.parse(JSON.stringify(data));

    document.getElementById('case_number').value = data.case_number || '';
    document.getElementById('act_type').value = data.act_type || 'AIJ';
    document.getElementById('hearing_datetime').value = data.hearing_datetime || '';
    document.getElementById('hearing_link').value = data.hearing_link || '';
    document.getElementById('is_in_person').checked = data.is_in_person || false;
    document.getElementById('prosecutor').value = data.prosecutor || '';
    document.getElementById('defense_counsel').value = data.defense_counsel || '';
    document.getElementById('qualification_text').value = data.qualification_text || '';
    document.getElementById('imputation_text').value = data.imputation_text || '';
    document.getElementById('facts_summary').value = data.facts_summary || '';
    document.getElementById('defense_witness_note').value = data.defense_witness_note || '';

    renderDefendants(data.defendants || []);
    renderHistory(data.chronological_history || []);
    renderWitnesses(data.prosecution_witnesses || []);

    btnExportDocx.disabled = false;
    updateLivePreview();
  }

  // Render Sub-Lists
  function renderDefendants(defendants) {
    defsContainer.innerHTML = '';
    defendants.forEach((d, idx) => {
      const row = document.createElement('div');
      row.className = 'item-row';
      row.innerHTML = `
        <input type="text" class="form-control def-name" placeholder="Nome do Réu" value="${d.name || ''}" data-idx="${idx}">
        <input type="text" class="form-control def-status" placeholder="Situação (ex: preso, solto)" value="${d.status || ''}" data-idx="${idx}">
        <input type="text" class="form-control def-subpoena mono" placeholder="ID Intimação" value="${d.subpoena_id || ''}" data-idx="${idx}">
        <button type="button" class="btn-remove-item" data-idx="${idx}" title="Remover Réu">&times;</button>
      `;
      row.querySelector('.btn-remove-item').addEventListener('click', () => {
        activeData.defendants.splice(idx, 1);
        renderDefendants(activeData.defendants);
        updateLivePreview();
      });
      row.querySelectorAll('input').forEach((input) => {
        input.addEventListener('input', syncDataFromForm);
      });
      defsContainer.appendChild(row);
    });
  }

  function renderHistory(items) {
    historyContainer.innerHTML = '';
    items.forEach((item, idx) => {
      const row = document.createElement('div');
      row.className = 'history-item-row';
      row.innerHTML = `
        <input type="text" class="form-control hist-date mono" placeholder="DD/MM/AA" value="${item.date_str || ''}" data-idx="${idx}">
        <input type="text" class="form-control hist-desc" placeholder="Descrição do Ato Processual" value="${item.description || ''}" data-idx="${idx}">
        <input type="text" class="form-control hist-id mono" placeholder="ID PJe" value="${item.doc_id || ''}" data-idx="${idx}">
        <button type="button" class="btn-remove-item" data-idx="${idx}" title="Remover Ato">&times;</button>
      `;
      row.querySelector('.btn-remove-item').addEventListener('click', () => {
        activeData.chronological_history.splice(idx, 1);
        renderHistory(activeData.chronological_history);
        updateLivePreview();
      });
      row.querySelectorAll('input').forEach((input) => {
        input.addEventListener('input', syncDataFromForm);
      });
      historyContainer.appendChild(row);
    });
  }

  function renderWitnesses(witnesses) {
    prosWitnessContainer.innerHTML = '';
    witnesses.forEach((w, idx) => {
      const row = document.createElement('div');
      row.className = 'item-row';
      row.innerHTML = `
        <input type="text" class="form-control wit-name" placeholder="Nome da Testemunha" value="${w.name || ''}" data-idx="${idx}">
        <input type="text" class="form-control wit-role" placeholder="Papel (Vítima, PM, etc.)" value="${w.role || ''}" data-idx="${idx}">
        <input type="text" class="form-control wit-status" placeholder="Status / ID" value="${w.status_id || ''}" data-idx="${idx}">
        <button type="button" class="btn-remove-item" data-idx="${idx}" title="Remover Testemunha">&times;</button>
      `;
      row.querySelector('.btn-remove-item').addEventListener('click', () => {
        activeData.prosecution_witnesses.splice(idx, 1);
        renderWitnesses(activeData.prosecution_witnesses);
        updateLivePreview();
      });
      row.querySelectorAll('input').forEach((input) => {
        input.addEventListener('input', syncDataFromForm);
      });
      prosWitnessContainer.appendChild(row);
    });
  }

  // Add Item Buttons
  btnAddDef.addEventListener('click', () => {
    if (!activeData) activeData = { defendants: [] };
    activeData.defendants.push({ name: '', status: 'respondendo ao processo em liberdade', subpoena_id: '' });
    renderDefendants(activeData.defendants);
    updateLivePreview();
  });

  btnAddHist.addEventListener('click', () => {
    if (!activeData) activeData = { chronological_history: [] };
    activeData.chronological_history.push({ date_str: '', description: '', doc_id: '' });
    renderHistory(activeData.chronological_history);
    updateLivePreview();
  });

  btnAddWit.addEventListener('click', () => {
    if (!activeData) activeData = { prosecution_witnesses: [] };
    const num = (activeData.prosecution_witnesses.length || 0) + 1;
    activeData.prosecution_witnesses.push({ number: num, name: '', role: 'Testemunha', status_id: 'Intimado(a)' });
    renderWitnesses(activeData.prosecution_witnesses);
    updateLivePreview();
  });

  // Sync Form Data
  form.addEventListener('input', syncDataFromForm);

  function syncDataFromForm() {
    if (!activeData) return;

    activeData.case_number = document.getElementById('case_number').value;
    activeData.act_type = document.getElementById('act_type').value;
    activeData.hearing_datetime = document.getElementById('hearing_datetime').value;
    activeData.hearing_link = document.getElementById('hearing_link').value;
    activeData.is_in_person = document.getElementById('is_in_person').checked;
    activeData.prosecutor = document.getElementById('prosecutor').value;
    activeData.defense_counsel = document.getElementById('defense_counsel').value;
    activeData.qualification_text = document.getElementById('qualification_text').value;
    activeData.imputation_text = document.getElementById('imputation_text').value;
    activeData.facts_summary = document.getElementById('facts_summary').value;
    activeData.defense_witness_note = document.getElementById('defense_witness_note').value;

    const defRows = defsContainer.querySelectorAll('.item-row');
    activeData.defendants = Array.from(defRows).map((r) => ({
      name: r.querySelector('.def-name').value,
      status: r.querySelector('.def-status').value,
      subpoena_id: r.querySelector('.def-subpoena').value,
    }));

    const histRows = historyContainer.querySelectorAll('.history-item-row');
    activeData.chronological_history = Array.from(histRows).map((r) => ({
      date_str: r.querySelector('.hist-date').value,
      description: r.querySelector('.hist-desc').value,
      doc_id: r.querySelector('.hist-id').value,
    }));

    const witRows = prosWitnessContainer.querySelectorAll('.item-row');
    activeData.prosecution_witnesses = Array.from(witRows).map((r, idx) => ({
      number: idx + 1,
      name: r.querySelector('.wit-name').value,
      role: r.querySelector('.wit-role').value,
      status_id: r.querySelector('.wit-status').value,
    }));

    updateLivePreview();
  }

  // Live Preview Renderer (Fixed White Sheet, Pure Styling)
  function updateLivePreview() {
    if (!activeData) {
      paperPlaceholder.style.display = 'flex';
      paperBody.classList.remove('active');
      return;
    }

    paperPlaceholder.style.display = 'none';
    paperBody.classList.add('active');

    const factsLen = (activeData.facts_summary || '').length;
    factsCharCount.innerText = `${factsLen} caracteres`;

    const pjeLink = (id) => `${PJE_DOC_URL_TEMPLATE}${id}`;

    let html = '';

    // Title line Underlined
    html += `<div class="doc-title">Proc. ${activeData.case_number || '0000000-00.0000.8.20.0000'} ${activeData.act_type || 'AIJ'} ${activeData.hearing_datetime || ''}</div>`;

    // Meeting Link
    if (activeData.hearing_link && !activeData.is_in_person) {
      html += `<div class="doc-link"><a href="${activeData.hearing_link}" target="_blank" rel="noopener noreferrer">${activeData.hearing_link}</a></div>`;
    } else {
      html += `<div class="doc-link" style="text-decoration: underline;">Audiência Presencial</div>`;
    }

    // Blank separator
    html += '<div style="margin-bottom: 1.2rem;"></div>';

    // Resumo Call
    html += `<div class="doc-resumo-call">Segue o resumo da audiência:</div>`;
    html += '<div style="margin-bottom: 1.2rem;"></div>';

    // Callout line if ANPP
    if ((activeData.act_type || '').includes('ANPP')) {
      const timePart = (activeData.hearing_datetime || '').includes('às')
        ? activeData.hearing_datetime.split('às').pop().trim()
        : activeData.hearing_datetime || '';
      html += `<div class="doc-callout"><span class="hl-yellow">${timePart} - ${activeData.case_number || ''} - ${activeData.act_type || ''}</span></div>`;
      html += '<div style="margin-bottom: 1.2rem;"></div>';
    }

    // PROMOTOR (Bright green highlight)
    const promPrefix = (activeData.prosecutor || '').includes(';') ? 'PROMOTORES:' : 'PROMOTOR:';
    html += `<div class="doc-promotor"><span class="hl-green">${promPrefix} ${activeData.prosecutor || ''}</span></div>`;
    html += '<div style="margin-bottom: 1.2rem;"></div>';

    // RÉUS (Bright green highlight)
    if (activeData.defendants && activeData.defendants.length === 1) {
      const d = activeData.defendants[0];
      const isFem = (d.name || '').trim().toLowerCase().endsWith('a');
      const genderPrefix = isFem ? 'Ré:' : 'Réu:';
      const idText = d.subpoena_id ? ` - Intimado ID <a href="${pjeLink(d.subpoena_id)}" target="_blank" rel="noopener noreferrer">${d.subpoena_id}</a>` : '';
      html += `<div class="doc-reus"><span class="hl-green">${genderPrefix} ${d.name} - ${d.status}${idText}</span></div>`;
    } else if (activeData.defendants && activeData.defendants.length > 1) {
      html += '<div class="doc-reus"><span class="hl-green">Réus:</span></div>';
      activeData.defendants.forEach((d) => {
        const idText = d.subpoena_id ? ` - Intimado ID <a href="${pjeLink(d.subpoena_id)}" target="_blank" rel="noopener noreferrer">${d.subpoena_id}</a>` : '';
        html += `<div class="doc-reus" style="padding-left: 1.27cm;">${d.name} - ${d.status}${idText}</div>`;
      });
    }

    // DEFESA (Bright green highlight)
    if (activeData.defense_counsel) {
      html += `<div class="doc-defesa"><span class="hl-green">${activeData.defense_counsel}</span></div>`;
    }

    html += '<div style="margin-bottom: 1.2rem;"></div>';

    const isAnpp = (activeData.act_type || '').includes('ANPP');

    // QUALIFICAÇÃO (Yellow highlight - omitted in ANPP)
    if (activeData.qualification_text && !isAnpp) {
      html += '<div class="doc-section-header"><span class="hl-yellow">QUALIFICAÇÃO</span></div>';
      const paras = activeData.qualification_text.split('\n\n').filter((p) => p.trim());
      paras.forEach((p) => {
        const commaIdx = p.indexOf(',');
        if (commaIdx !== -1) {
          const namePart = p.substring(0, commaIdx).trim();
          const restPart = p.substring(commaIdx);
          html += `<div class="doc-narrative-p"><strong class="doc-name-bold">${namePart.toUpperCase()}</strong>${restPart}</div>`;
        } else {
          html += `<div class="doc-narrative-p">${p}</div>`;
        }
      });
      html += '<div style="margin-bottom: 1.2rem;"></div>';
    }

    // IMPUTAÇÃO (Yellow highlight - omitted in ANPP)
    if (activeData.imputation_text && !isAnpp) {
      html += '<div class="doc-section-header"><span class="hl-yellow">IMPUTAÇÃO</span></div>';
      const paras = activeData.imputation_text.split('\n\n').filter((p) => p.trim());
      paras.forEach((p) => {
        const formattedP = p.replace(/(\(.*?\))/g, '<strong class="doc-art-bold">$1</strong>');
        html += `<div class="doc-narrative-p">${formattedP}</div>`;
      });
      html += '<div style="margin-bottom: 1.2rem;"></div>';
    }

    // RESUMO DOS FATOS (Yellow highlight)
    if (activeData.facts_summary) {
      html += '<div class="doc-section-header"><span class="hl-yellow">RESUMO DOS FATOS</span></div>';
      if (activeData.special_notes) {
        html += `<div class="doc-obs">${activeData.special_notes}</div>`;
      }
      const paras = activeData.facts_summary.split('\n\n').filter((p) => p.trim());
      paras.forEach((p) => {
        // Wrap IDs in links
        const linkedP = p.replace(/\b(\d{7,10})\b/g, (match) => `<a href="${pjeLink(match)}" target="_blank" rel="noopener noreferrer">${match}</a>`);
        html += `<div class="doc-narrative-p">${linkedP}</div>`;
      });
      html += '<div style="margin-bottom: 1.2rem;"></div>';
    }

    // HISTÓRICO PROCESSUAL (Yellow highlight - omitted in ANPP)
    if (activeData.chronological_history && activeData.chronological_history.length > 0 && !isAnpp) {
      html += '<div class="doc-section-header"><span class="hl-yellow">HISTÓRICO PROCESSUAL</span></div>';
      activeData.chronological_history.forEach((h) => {
        html += `<div class="doc-history-p">${h.date_str}: ${h.description} (ID <a href="${pjeLink(h.doc_id)}" target="_blank" rel="noopener noreferrer">${h.doc_id}</a>)</div>`;
      });
      html += '<div style="margin-bottom: 1.2rem;"></div>';
    }

    // TESTEMUNHAS (Yellow highlight - omitted in ANPP)
    if (!isAnpp) {
      if (activeData.prosecution_witnesses && activeData.prosecution_witnesses.length > 0) {
        html += '<div class="doc-section-header"><span class="hl-yellow">TESTEMUNHAS DE ACUSAÇÃO:</span></div>';
        activeData.prosecution_witnesses.forEach((w) => {
          const num = String(w.number).padStart(2, '0');
          let status = w.status_id ? ` - ${w.status_id}` : '';
          status = status.replace(/\b(\d{7,10})\b/g, (match) => `<a href="${pjeLink(match)}" target="_blank" rel="noopener noreferrer">${match}</a>`);
          html += `<div class="doc-witness-p">${num}) ${w.name} - ${w.role}${status}</div>`;
        });
      }

      if (activeData.defense_witnesses && activeData.defense_witnesses.length > 0) {
        html += '<div class="doc-section-header"><span class="hl-yellow">TESTEMUNHAS DE DEFESA:</span></div>';
        activeData.defense_witnesses.forEach((w) => {
          const num = String(w.number).padStart(2, '0');
          let status = w.status_id ? ` - ${w.status_id}` : '';
          status = status.replace(/\b(\d{7,10})\b/g, (match) => `<a href="${pjeLink(match)}" target="_blank" rel="noopener noreferrer">${match}</a>`);
          html += `<div class="doc-witness-p">${num}) ${w.name}${status}</div>`;
        });
      } else if (activeData.defense_witness_note) {
        html += `<div class="doc-witness-p" style="margin-top: 0.6rem;"><span class="hl-yellow">${activeData.defense_witness_note}</span></div>`;
      }
    }

    html += '<div style="margin-bottom: 1.2rem;"></div>';

    // Fechamento Formal
    html += `<div class="doc-closure">${activeData.closure_text || 'Cordial e respeitosamente,'}</div>`;

    paperBody.innerHTML = html;
  }

  // Export DOCX
  btnExportDocx.addEventListener('click', async () => {
    if (!activeData) return;

    btnExportDocx.disabled = true;
    btnExportDocx.innerHTML = `
      <div class="spinner" style="width:16px;height:16px;border-width:2px;"></div>
      <span>Gerando DOCX...</span>
    `;

    try {
      syncDataFromForm();
      const safeCase = (activeData.case_number || 'Processo').replace(/[\/\\]/g, '-');
      const filename = `Resumo - ${safeCase} ${activeData.act_type || 'AIJ'}.docx`;

      if (typeof eel !== 'undefined' && eel.generate_docx_eel) {
        // Modo Desktop Nativo via Eel
        const base64Docx = await eel.generate_docx_eel(JSON.stringify(activeData))();
        if (!base64Docx || base64Docx.startsWith('ERROR:')) {
          throw new Error(base64Docx || 'Falha na geração do arquivo DOCX.');
        }

        const byteCharacters = atob(base64Docx);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
        showToast('Documento DOCX gerado e baixado com sucesso!', 'success');
      } else {
        // Modo Web padrão via FastAPI
        const response = await fetch('/api/generate-docx', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(activeData),
        });

        if (!response.ok) {
          throw new Error('Falha na geração do arquivo DOCX.');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
        showToast('Documento DOCX baixado com sucesso!', 'success');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      btnExportDocx.disabled = false;
      btnExportDocx.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        <span>Baixar Resumo (.docx)</span>
      `;
    }
  });

  // Revert Changes
  btnRevert.addEventListener('click', () => {
    if (originalData) {
      loadDataIntoUI(originalData);
      showToast('Valores originais restaurados com sucesso.', 'success');
    }
  });

  // Toast Notification
  function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerText = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, 4000);
  }
});

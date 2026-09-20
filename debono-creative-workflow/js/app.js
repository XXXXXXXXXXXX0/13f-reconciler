/*
 * Engine for the Focus & Alternatives pipeline.
 * Renders whatever STAGES (js/stages.js) defines — adding, removing, or reordering
 * stages there is enough to change the flow; nothing here should need to change
 * unless a genuinely new *input type* is introduced.
 */

(function () {
  const STORAGE_KEY = 'debono-focus-pipeline-session';

  const state = {
    answers: {},
    currentIndex: 0
  };

  const stageContainer = document.getElementById('stage-container');
  const progressEl = document.getElementById('progress');
  const backBtn = document.getElementById('back-btn');
  const nextBtn = document.getElementById('next-btn');
  const footer = document.getElementById('footer');

  function loadSession() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw);
      if (saved && typeof saved === 'object') {
        state.answers = saved.answers || {};
        state.currentIndex = typeof saved.currentIndex === 'number' ? saved.currentIndex : 0;
      }
    } catch (e) {
      // Storage unavailable or corrupted — start fresh, no need to surface this.
    }
  }

  function saveSession() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      // Best-effort persistence only.
    }
  }

  function resetSession() {
    state.answers = {};
    state.currentIndex = 0;
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {
      // ignore
    }
    render();
  }

  function getVisibleStages() {
    return STAGES.filter((stage) => {
      if (!stage.showIf) return true;
      return state.answers[stage.showIf.stage] === stage.showIf.equals;
    });
  }

  function clearContainer(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function renderProgress(visibleStages) {
    clearContainer(progressEl);
    if (state.currentIndex >= visibleStages.length) {
      progressEl.textContent = 'Complete';
      return;
    }
    const label = document.createElement('span');
    label.textContent = `Step ${state.currentIndex + 1} of ${visibleStages.length}`;
    progressEl.appendChild(label);

    const track = document.createElement('div');
    track.className = 'progress-track';
    const fill = document.createElement('div');
    fill.className = 'progress-fill';
    fill.style.width = `${((state.currentIndex) / visibleStages.length) * 100}%`;
    track.appendChild(fill);
    progressEl.appendChild(track);
  }

  function renderSingleChoice(stage, container) {
    const list = document.createElement('div');
    list.className = 'option-list';
    const existing = state.answers[stage.id];

    stage.options.forEach((opt) => {
      const label = document.createElement('label');
      label.className = 'option';

      const input = document.createElement('input');
      input.type = 'radio';
      input.name = stage.id;
      input.value = opt.value;
      input.checked = existing === opt.value;

      const text = document.createElement('div');
      text.className = 'option-text';
      const title = document.createElement('div');
      title.className = 'option-title';
      title.textContent = opt.label;
      text.appendChild(title);
      if (opt.description) {
        const desc = document.createElement('div');
        desc.className = 'option-description';
        desc.textContent = opt.description;
        text.appendChild(desc);
      }

      label.appendChild(input);
      label.appendChild(text);
      list.appendChild(label);
    });

    container.appendChild(list);
  }

  function renderText(stage, container) {
    const textarea = document.createElement('textarea');
    textarea.id = `input-${stage.id}`;
    textarea.rows = 4;
    textarea.value = state.answers[stage.id] || '';
    container.appendChild(textarea);
  }

  function renderTextList(stage, container) {
    const existing = Array.isArray(state.answers[stage.id]) ? state.answers[stage.id].slice() : [];
    const minItems = stage.minItems || (stage.optional ? 0 : 1);
    while (existing.length < minItems) existing.push('');
    if (existing.length === 0) existing.push('');

    const list = document.createElement('div');
    list.className = 'text-list';
    list.id = `input-${stage.id}`;

    function addRow(value) {
      const row = document.createElement('div');
      row.className = 'text-list-row';

      const input = document.createElement('input');
      input.type = 'text';
      input.value = value || '';
      row.appendChild(input);

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'remove-row-btn';
      removeBtn.textContent = 'Remove';
      removeBtn.addEventListener('click', () => {
        if (list.children.length > (minItems || 1)) {
          row.remove();
        } else {
          input.value = '';
        }
      });
      row.appendChild(removeBtn);

      list.appendChild(row);
    }

    existing.forEach(addRow);
    container.appendChild(list);

    if (!stage.maxItems || existing.length < stage.maxItems) {
      const addBtn = document.createElement('button');
      addBtn.type = 'button';
      addBtn.className = 'add-row-btn';
      addBtn.textContent = '+ Add another';
      addBtn.addEventListener('click', () => {
        if (stage.maxItems && list.children.length >= stage.maxItems) return;
        addRow('');
        if (stage.maxItems && list.children.length >= stage.maxItems) {
          addBtn.disabled = true;
        }
      });
      container.appendChild(addBtn);
    }
  }

  function renderStage(stage) {
    clearContainer(stageContainer);

    const card = document.createElement('div');
    card.className = 'stage-card';

    const eyebrow = document.createElement('div');
    eyebrow.className = 'stage-number';
    eyebrow.textContent = `Stage ${stage.number}`;
    card.appendChild(eyebrow);

    const title = document.createElement('h2');
    title.textContent = stage.title;
    card.appendChild(title);

    const instructions = document.createElement('p');
    instructions.className = 'stage-instructions';
    instructions.textContent = stage.instructions;
    card.appendChild(instructions);

    if (stage.optional) {
      const badge = document.createElement('span');
      badge.className = 'optional-badge';
      badge.textContent = 'Optional';
      card.appendChild(badge);
    }

    const inputArea = document.createElement('div');
    inputArea.className = 'stage-input';

    if (stage.type === 'single-choice') renderSingleChoice(stage, inputArea);
    else if (stage.type === 'text') renderText(stage, inputArea);
    else if (stage.type === 'text-list') renderTextList(stage, inputArea);

    card.appendChild(inputArea);

    const errorEl = document.createElement('div');
    errorEl.className = 'stage-error';
    errorEl.id = 'stage-error';
    card.appendChild(errorEl);

    stageContainer.appendChild(card);
  }

  function collectAnswer(stage) {
    if (stage.type === 'single-choice') {
      const checked = stageContainer.querySelector(`input[name="${stage.id}"]:checked`);
      return checked ? checked.value : undefined;
    }
    if (stage.type === 'text') {
      const el = document.getElementById(`input-${stage.id}`);
      return el ? el.value.trim() : '';
    }
    if (stage.type === 'text-list') {
      const list = document.getElementById(`input-${stage.id}`);
      if (!list) return [];
      const values = Array.from(list.querySelectorAll('input[type="text"]'))
        .map((i) => i.value.trim())
        .filter((v) => v.length > 0);
      return values;
    }
    return undefined;
  }

  function validateAnswer(stage, value) {
    if (stage.optional) return true;
    if (stage.type === 'text-list') {
      const min = stage.minItems || 1;
      return Array.isArray(value) && value.length >= min;
    }
    if (Array.isArray(value)) return value.length > 0;
    return value !== undefined && value !== '';
  }

  function showError(message) {
    const errorEl = document.getElementById('stage-error');
    if (errorEl) errorEl.textContent = message;
  }

  function renderSummary(visibleStages) {
    clearContainer(stageContainer);

    const card = document.createElement('div');
    card.className = 'stage-card summary-card';

    const title = document.createElement('h2');
    title.textContent = 'Focus & Alternatives — Summary';
    card.appendChild(title);

    const intro = document.createElement('p');
    intro.className = 'stage-instructions';
    intro.textContent =
      'This is what you defined before applying any tool. It carries forward into whichever ' +
      'tool module you choose next.';
    card.appendChild(intro);

    visibleStages.forEach((stage) => {
      const row = document.createElement('div');
      row.className = 'summary-row';

      const label = document.createElement('div');
      label.className = 'summary-label';
      label.textContent = stage.title;
      row.appendChild(label);

      const value = document.createElement('div');
      value.className = 'summary-value';
      const answer = state.answers[stage.id];
      if (Array.isArray(answer)) {
        if (answer.length === 0) {
          value.textContent = '—';
        } else {
          const ul = document.createElement('ul');
          answer.forEach((item) => {
            const li = document.createElement('li');
            li.textContent = item;
            ul.appendChild(li);
          });
          value.appendChild(ul);
        }
      } else {
        value.textContent = answer || '—';
      }
      row.appendChild(value);
      card.appendChild(row);
    });

    const nextStepNote = document.createElement('p');
    nextStepNote.className = 'stage-instructions next-step-note';
    nextStepNote.textContent = 'Tool modules (Six Hats, PO, Concept Fan, and others) build on this output and are coming next.';
    card.appendChild(nextStepNote);

    stageContainer.appendChild(card);
  }

  function updateFooter(visibleStages) {
    const atStart = state.currentIndex === 0;
    const atEnd = state.currentIndex >= visibleStages.length;

    backBtn.disabled = atStart;
    backBtn.style.display = atEnd ? 'none' : '';

    if (atEnd) {
      nextBtn.textContent = 'Start Over';
    } else if (state.currentIndex === visibleStages.length - 1) {
      nextBtn.textContent = 'Finish';
    } else {
      nextBtn.textContent = 'Next';
    }
  }

  function render() {
    const visibleStages = getVisibleStages();
    if (state.currentIndex > visibleStages.length) {
      state.currentIndex = visibleStages.length;
    }

    renderProgress(visibleStages);

    if (state.currentIndex >= visibleStages.length) {
      renderSummary(visibleStages);
    } else {
      renderStage(visibleStages[state.currentIndex]);
    }

    updateFooter(visibleStages);
  }

  nextBtn.addEventListener('click', () => {
    const visibleStages = getVisibleStages();

    if (state.currentIndex >= visibleStages.length) {
      resetSession();
      return;
    }

    const stage = visibleStages[state.currentIndex];
    const value = collectAnswer(stage);

    if (!validateAnswer(stage, value)) {
      showError('This step needs an answer before moving on.');
      return;
    }

    state.answers[stage.id] = value;
    state.currentIndex += 1;
    saveSession();
    render();
  });

  backBtn.addEventListener('click', () => {
    if (state.currentIndex === 0) return;
    state.currentIndex -= 1;
    saveSession();
    render();
  });

  loadSession();
  render();
})();

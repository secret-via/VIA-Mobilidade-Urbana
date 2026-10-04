/* Chat da VIA com histórico de conversas (como o Claude): várias conversas salvas,
   lista ao lado, nova conversa, renomear e excluir. Com contas, as conversas ficam no
   servidor e são privadas de cada usuário; no modo local (sem contas) ficam neste
   navegador. O mesmo painel serve a aba VIA e o popup do desktop. */
(() => {
  const panel = document.getElementById('assistantChatPanel');
  if (!panel) return;

  const q = (s) => panel.querySelector(s);
  const msgs = q('#chatMessages'), input = q('#chatInput'), sendBtn = q('#chatSend');
  const suggest = q('#chatSuggest'), down = q('#chatDown');
  const histList = q('#chatHistList'), histBtn = q('#chatHistBtn'), backdrop = q('#chatHistBackdrop');
  const layout = q('.chat-layout'), titleEl = q('#chatTitle'), main = q('.chat-main');

  msgs.setAttribute('role', 'log');
  msgs.setAttribute('aria-live', 'polite');

  const LS = 'via-chats';
  const STARTERS = ['Qual foi o horário de pico hoje?', 'Resuma o fluxo da última semana', 'Houve alguma ocorrência incomum?'];
  const state = { mode: 'local', convs: [], currentId: null, busy: false, lastIntent: null };

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* ---------------- armazenamento: servidor (contas) ou local ---------------- */
  async function api(url, opts) {
    const res = await fetch(url, opts);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || ('Erro ' + res.status));
    return body;
  }
  const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });

  function readLocal() { try { return JSON.parse(localStorage.getItem(LS) || '[]'); } catch (_) { return []; } }
  function writeLocal(list) { try { localStorage.setItem(LS, JSON.stringify(list.slice(0, 50))); } catch (_) { /* sem armazenamento */ } }

  const backend = {
    async list() {
      if (state.mode === 'server') return api('/api/chat/conversations');
      return readLocal().map(({ id, title, updated_at }) => ({ id, title, updated_at }));
    },
    async open(id) {
      if (state.mode === 'server') return api('/api/chat/conversations/' + id);
      return readLocal().find((c) => c.id === id) || { id, title: 'Conversa', messages: [] };
    },
    async create() {
      if (state.mode === 'server') return api('/api/chat/conversations', json('POST'));
      const conv = { id: 'l' + Date.now(), title: 'Nova conversa', updated_at: new Date().toISOString(), messages: [] };
      writeLocal([conv, ...readLocal()]);
      return conv;
    },
    async rename(id, title) {
      if (state.mode === 'server') return api('/api/chat/conversations/' + id, json('PATCH', { title }));
      writeLocal(readLocal().map((c) => (c.id === id ? { ...c, title } : c)));
    },
    async remove(id) {
      if (state.mode === 'server') return api('/api/chat/conversations/' + id, { method: 'DELETE' });
      writeLocal(readLocal().filter((c) => c.id !== id));
    },
    async send(id, text) {
      if (state.mode === 'server') return api('/api/chat/conversations/' + id + '/messages', json('POST', { content: text }));
      const r = await api('/api/assistant/query', json('POST', { question: text, previous_intent: state.lastIntent }));
      const all = readLocal();
      const conv = all.find((c) => c.id === id);
      if (conv) {
        conv.messages.push({ role: 'user', content: text }, { role: 'assistant', content: r.answer, intent: r.data && r.data.has_data ? r.intent : null });
        if (conv.title === 'Nova conversa') conv.title = text.replace(/\s+/g, ' ').slice(0, 60);
        conv.updated_at = new Date().toISOString();
        writeLocal([conv, ...all.filter((c) => c.id !== id)]);
      }
      return { answer: r.answer, intent: r.data && r.data.has_data ? r.intent : null, limit_reached: r.limit_reached, title: conv ? conv.title : 'Conversa' };
    },
  };

  /* ---------------- mensagens ---------------- */
  function scrollEnd() { msgs.scrollTop = msgs.scrollHeight; }
  function updateDown() { if (down) down.hidden = msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight < 80; }

  function bubble(role, text, intent) {
    const div = document.createElement('div');
    div.className = 'chat-message ' + role;
    div.textContent = text;
    if (role === 'assistant' && intent) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'button small chat-report';
      btn.textContent = 'Baixar relatório PDF deste período';
      btn.addEventListener('click', () => downloadReportPdf(buildReportUrl(intent)));
      div.appendChild(btn);
    }
    msgs.appendChild(div);
    scrollEnd();
    return div;
  }

  /* Conversa vazia: título, campo e sugestões (as sugestões ficam à vista só enquanto vazia). */
  function setEmpty(on) {
    main.classList.toggle('is-empty', on);
    if (suggest) suggest.hidden = !on;
  }
  function emptyState() {
    msgs.innerHTML = '<div class="chat-empty"><h3>Como posso ajudar?</h3><p>Pergunte sobre o fluxo, os horários de pico ou as ocorrências das suas câmeras.</p></div>';
    setEmpty(true);
  }

  /* ---------------- lista de conversas ---------------- */
  function groupOf(iso) {
    const d = new Date(iso), now = new Date();
    const days = Math.floor((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000);
    if (days <= 0) return 'Hoje';
    if (days === 1) return 'Ontem';
    if (days <= 7) return 'Últimos 7 dias';
    return 'Anteriores';
  }

  function renderList() {
    if (!state.convs.length) { histList.innerHTML = '<p class="chat-hist-empty">Suas conversas aparecem aqui.</p>'; return; }
    let html = '', last = '';
    state.convs.forEach((c) => {
      const g = groupOf(c.updated_at);
      if (g !== last) { html += '<div class="chat-hist-group">' + g + '</div>'; last = g; }
      html += '<div class="chat-hist-item' + (String(c.id) === String(state.currentId) ? ' active' : '') + '" data-id="' + esc(c.id) + '">' +
        '<button type="button" class="chat-hist-open" title="' + esc(c.title) + '">' + esc(c.title) + '</button>' +
        '<button type="button" class="chat-hist-act" data-act="rename" aria-label="Renomear conversa" title="Renomear"><svg viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16z"/></svg></button>' +
        '<button type="button" class="chat-hist-act" data-act="delete" aria-label="Excluir conversa" title="Excluir"><svg viewBox="0 0 24 24"><path d="M5 7h14M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg></button></div>';
    });
    histList.innerHTML = html;
  }

  async function refreshList() {
    try { state.convs = await backend.list(); } catch (_) { state.convs = []; }
    renderList();
  }

  function setTitle(t) { titleEl.textContent = t || 'Nova conversa'; }
  function closeHist() { layout.classList.remove('hist-open'); histBtn?.setAttribute('aria-expanded', 'false'); if (backdrop) backdrop.hidden = true; }
  function openHist() { layout.classList.add('hist-open'); histBtn?.setAttribute('aria-expanded', 'true'); if (backdrop) backdrop.hidden = false; }

  /* ---------------- ações ---------------- */
  function newConversation() {
    state.currentId = null;
    state.lastIntent = null;
    setTitle('Nova conversa');
    emptyState();
    renderList();
    closeHist();
    input.focus();
    updateDown();
  }

  async function selectConversation(id) {
    if (state.busy) return;
    try {
      const conv = await backend.open(id);
      state.currentId = conv.id;
      state.lastIntent = null;
      msgs.innerHTML = '';
      (conv.messages || []).forEach((m) => { bubble(m.role, m.content, m.intent); if (m.role === 'assistant' && m.intent) state.lastIntent = m.intent; });
      if (!(conv.messages || []).length) emptyState(); else setEmpty(false);
      setTitle(conv.title);
      renderList();
      closeHist();
      scrollEnd();
      updateDown();
    } catch (err) { bubble('assistant', 'Não consegui abrir a conversa: ' + err.message); }
  }

  function renameConversation(id) {
    const item = histList.querySelector('.chat-hist-item[data-id="' + String(id).replace(/"/g, '') + '"]');
    const cur = state.convs.find((c) => String(c.id) === String(id));
    if (!item || !cur) return;
    const field = document.createElement('input');
    field.type = 'text'; field.className = 'chat-hist-edit'; field.maxLength = 80; field.value = cur.title;
    field.setAttribute('aria-label', 'Novo título da conversa');
    item.innerHTML = '';
    item.appendChild(field);
    field.focus(); field.select();
    let done = false;
    const finish = async (save) => {
      if (done) return;
      done = true;
      const title = field.value.trim().slice(0, 80);
      if (save && title && title !== cur.title) {
        try {
          await backend.rename(id, title);
          if (String(id) === String(state.currentId)) setTitle(title);
        } catch (err) { bubble('assistant', 'Não consegui renomear: ' + err.message); }
      }
      await refreshList();
    };
    field.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); finish(true); }
      else if (e.key === 'Escape') { e.preventDefault(); finish(false); }
    });
    field.addEventListener('blur', () => finish(true));
  }

  function deleteConversation(id, btn) {
    if (btn && !btn.classList.contains('armed')) {
      btn.classList.add('armed');
      btn.title = 'Clique de novo para excluir';
      btn.setAttribute('aria-label', 'Confirmar exclusão');
      setTimeout(() => { btn.classList.remove('armed'); btn.title = 'Excluir'; }, 3000);
      return;
    }
    (async () => {
      try {
        await backend.remove(id);
        if (String(id) === String(state.currentId)) newConversation();
        await refreshList();
      } catch (err) { bubble('assistant', 'Não consegui excluir: ' + err.message); }
    })();
  }
  async function send(text) {
    text = (text ?? input.value).trim();
    if (!text || state.busy) return;
    state.busy = true;
    input.disabled = true; sendBtn.disabled = true;
    msgs.querySelector('.chat-empty')?.remove();
    setEmpty(false);
    input.value = ''; input.style.height = 'auto';
    bubble('user', text);
    const thinking = bubble('assistant', '');
    thinking.classList.add('thinking');
    thinking.innerHTML = '<span class="chat-bot" aria-hidden="true"><span class="chat-bot-fig"><img src="/static/via-assistente-claro.png" alt=""><i class="chat-bot-eye"></i></span></span><span class="chat-typing-label">Consultando os dados</span>';
    try {
      if (!state.currentId) {
        const conv = await backend.create();
        state.currentId = conv.id;
      }
      const r = await backend.send(state.currentId, text);
      thinking.classList.remove('thinking');
      thinking.textContent = r.answer;
      if (r.intent) {
        state.lastIntent = r.intent;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'button small chat-report';
        btn.textContent = 'Baixar relatório PDF deste período';
        btn.addEventListener('click', () => downloadReportPdf(buildReportUrl(r.intent)));
        thinking.appendChild(btn);
      }
      if (r.title) setTitle(r.title);
      await refreshList();
    } catch (err) {
      thinking.classList.remove('thinking');
      thinking.textContent = 'Não consegui responder: ' + err.message;
    }
    state.busy = false;
    input.disabled = false; sendBtn.disabled = false;
    input.focus();
    scrollEnd();
  }

  /* ---------------- eventos ---------------- */
  sendBtn.addEventListener('click', () => send());
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } });
  input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 160) + 'px'; });
  msgs.addEventListener('scroll', updateDown);
  down?.addEventListener('click', () => msgs.scrollTo({ top: msgs.scrollHeight, behavior: 'smooth' }));
  panel.addEventListener('click', (e) => {
    const sug = e.target.closest('.chat-sug');
    if (sug) { if (suggest) suggest.hidden = true; send(sug.textContent); return; }
    if (e.target.closest('#chatNew') || e.target.closest('#chatNewSm')) { newConversation(); return; }
    const act = e.target.closest('.chat-hist-act');
    const item = e.target.closest('.chat-hist-item');
    if (act && item) { if (act.dataset.act === 'rename') renameConversation(item.dataset.id); else deleteConversation(item.dataset.id, act); return; }
    if (e.target.closest('.chat-hist-open') && item) selectConversation(item.dataset.id);
  });
  histBtn?.addEventListener('click', () => (layout.classList.contains('hist-open') ? closeHist() : openHist()));
  backdrop?.addEventListener('click', closeHist);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && layout.classList.contains('hist-open')) closeHist(); });

  /* Altura do menu superior: a aba VIA ocupa o resto da página (desktop). */
  function setNavHeight() {
    const bar = document.querySelector('.sidebar');
    if (bar && innerWidth > 640) document.documentElement.style.setProperty('--navh', bar.offsetHeight + 'px');
  }
  setNavHeight();
  addEventListener('resize', setNavHeight);

  /* ---------------- início ---------------- */
  (async () => {
    try { const me = await api('/api/me'); state.mode = me.multi_tenant ? 'server' : 'local'; } catch (_) { state.mode = 'local'; }
    emptyState();
    await refreshList();
  })();
})();

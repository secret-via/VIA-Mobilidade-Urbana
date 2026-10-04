/* Mapa operacional: mapa real (Leaflet + OpenStreetMap) centrado no município
   escolhido (estado -> município), com o contorno oficial do IBGE.

   O mapa SÓ MOSTRA câmeras já cadastradas em "Câmeras". A posição vem do
   ENDEREÇO digitado no cadastro: o sistema localiza o endereço e a câmera já
   aparece no ponto. Não existe cadastro nem posicionamento clicando no mapa, e a
   posição não depende do computador de quem monitora (ele pode estar em outro lugar).
   Posições de câmeras do servidor ficam salvas no banco; as demais ficam neste
   navegador junto com o restante do cadastro. */
(() => {
  const el = document.getElementById('map');
  if (!el) return;

  const $ = (s) => document.querySelector(s);
  const LS_MUNI = 'via-municipio';
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const notice = $('#mapNotice');
  const unplacedBox = $('#mapUnplaced');

  const state = { map: null, markers: new Map(), outline: null, muni: null, serverIds: new Set(), multiTenant: false, serverPos: new Map() };

  function say(text, kind) {
    if (!notice) return;
    clearTimeout(say.timer);
    if (!text) { notice.classList.add('hidden'); return; }
    notice.textContent = text;
    notice.className = 'vmap-notice' + (kind ? ' ' + kind : '');
    // Confirmações somem sozinhas; avisos de erro ficam até serem resolvidos.
    if (kind === 'info') say.timer = setTimeout(() => notice.classList.add('hidden'), 6000);
  }

  async function getJSON(url, opts) {
    const res = await fetch(url, opts);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || ('Erro ' + res.status));
    return body;
  }

  /* ---------- Leaflet ---------- */
  if (!window.L) {
    say('Não foi possível carregar o mapa. Verifique sua conexão com a internet.', 'err');
    return;
  }
  state.map = L.map(el, { zoomControl: true, attributionControl: true, minZoom: 3 }).setView([-14.2, -51.9], 4);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>',
  }).addTo(state.map);
  new ResizeObserver(() => state.map.invalidateSize()).observe(el);

  /* Alfinete: volta ao município escolhido, centralizado, depois de explorar o mapa. */
  const PIN = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/></svg>';
  const Recenter = L.Control.extend({
    onAdd() {
      const button = L.DomUtil.create('button', 'vmap-recenter');
      button.type = 'button';
      button.title = 'Voltar ao meu município';
      button.setAttribute('aria-label', 'Voltar ao meu município');
      button.innerHTML = PIN;
      L.DomEvent.disableClickPropagation(button);
      button.addEventListener('click', () => {
        if (state.muni) {
          const [s, w, n, e] = state.muni.bbox;
          state.map.flyToBounds([[s, w], [n, e]], { padding: [14, 14], duration: 0.6 });
        } else {
          document.getElementById('mapChange')?.click();
        }
      });
      return button;
    },
  });
  new Recenter({ position: 'topleft' }).addTo(state.map);

  /* ---------- município ---------- */
  function savedMunicipio() {
    try { return JSON.parse(localStorage.getItem(LS_MUNI) || 'null'); } catch (_) { return null; }
  }
  function rememberMunicipio(m) {
    try { localStorage.setItem(LS_MUNI, JSON.stringify({ id: m.id, nome: m.nome, uf: m.uf })); } catch (_) { /* sem armazenamento */ }
  }

  async function showMunicipio(id) {
    say('Carregando o mapa do município…');
    try {
      const data = await getJSON('/api/geo/municipio/' + encodeURIComponent(id));
      state.muni = data;
      rememberMunicipio(data);
      if (state.outline) state.map.removeLayer(state.outline);
      state.outline = L.geoJSON(data.geometry, { style: { color: '#4eaff7', weight: 2, fillColor: '#4eaff7', fillOpacity: 0.06, dashArray: '6 5' }, interactive: false }).addTo(state.map);
      const [s, w, n, e] = data.bbox;
      state.map.fitBounds([[s, w], [n, e]], { padding: [14, 14] });
      const place = $('#mapPlace');
      if (place) place.textContent = data.nome + ' · ' + data.uf;
      say('');
      render();
    } catch (err) {
      say(err.message || 'Não foi possível carregar o município.', 'err');
    }
  }

  /* ---------- seletor estado -> município ---------- */
  const picker = $('#mapPicker');
  const ufSel = $('#mapUf');
  const munSel = $('#mapMun');
  const saveBtn = $('#mapPickSave');
  let ufLoaded = false;

  async function loadUfs() {
    if (ufLoaded) return;
    const list = await getJSON('/api/geo/estados');
    ufSel.innerHTML = '<option value="">Estado</option>' + list.map((u) => '<option value="' + esc(u.sigla) + '">' + esc(u.nome) + '</option>').join('');
    ufLoaded = true;
  }
  async function loadMuns(uf, selected) {
    munSel.disabled = true;
    munSel.innerHTML = '<option value="">Carregando…</option>';
    if (!uf) { munSel.innerHTML = '<option value="">Município</option>'; return; }
    const list = await getJSON('/api/geo/municipios?uf=' + encodeURIComponent(uf));
    munSel.innerHTML = '<option value="">Município</option>' + list.map((m) => '<option value="' + m.id + '"' + (String(m.id) === String(selected) ? ' selected' : '') + '>' + esc(m.nome) + '</option>').join('');
    munSel.disabled = false;
    saveBtn.disabled = !munSel.value;
  }
  async function openPicker(first) {
    try {
      await loadUfs();
      const cur = state.muni || savedMunicipio();
      if (cur && cur.uf) { ufSel.value = cur.uf; await loadMuns(cur.uf, cur.id); }
      $('#mapPickTitle').textContent = first ? 'Escolha o município do mapa' : 'Trocar município';
      picker.classList.remove('hidden');
    } catch (err) { say(err.message, 'err'); }
  }
  ufSel?.addEventListener('change', () => loadMuns(ufSel.value).catch((e) => say(e.message, 'err')));
  munSel?.addEventListener('change', () => { saveBtn.disabled = !munSel.value; });
  $('#mapChange')?.addEventListener('click', () => openPicker(false));
  $('#mapPickCancel')?.addEventListener('click', () => picker.classList.add('hidden'));
  saveBtn?.addEventListener('click', async () => {
    const id = munSel.value;
    if (!id) return;
    saveBtn.disabled = true;
    try {
      if (state.multiTenant) await getJSON('/api/me/municipio', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
      picker.classList.add('hidden');
      await showMunicipio(id);
    } catch (err) { say(err.message, 'err'); }
    saveBtn.disabled = false;
  });

  /* ---------- câmeras no mapa (somente as cadastradas) ---------- */
  const valid = (c) => Number.isFinite(c.lat) && Number.isFinite(c.lng);
  const statusOf = (c) => (c.status === 'connected' ? 'ok' : (c.status === 'error' ? 'bad' : 'off'));
  const STATUS_TXT = { ok: 'Online', off: 'Sem sinal', bad: 'Com falha' };
  const CAM_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3z"/></svg>';
  const shownAddress = (c) => (c.location && !/^conectada ao servidor/i.test(c.location) ? c.location : '');

  function iconFor(c) {
    return L.divIcon({ className: 'vmap-pin ' + statusOf(c), html: CAM_SVG, iconSize: [34, 34], iconAnchor: [17, 17], popupAnchor: [0, -18] });
  }
  function addrForm(c) {
    return '<form class="vmap-addr" data-id="' + esc(c.id) + '"><input type="text" name="address" value="' + esc(shownAddress(c)) + '" placeholder="Rua, número, bairro" maxlength="200" aria-label="Endereço da câmera ' + esc(c.name) + '" required><button type="submit">Localizar</button></form>';
  }
  function popupFor(c) {
    return '<b>' + esc(c.name) + '</b><br>' + (shownAddress(c) ? esc(shownAddress(c)) + '<br>' : '') +
      '<span class="vmap-st ' + statusOf(c) + '">' + STATUS_TXT[statusOf(c)] + '</span>' +
      '<details class="vmap-edit"><summary>Alterar endereço</summary>' + addrForm(c) + '</details>' +
      '<div class="vmap-actions"><button type="button" class="danger" data-vm-act="delete" data-id="' + esc(c.id) + '">Excluir câmera</button></div>';
  }

  function allCameras() {
    return CameraStore.all().map((c) => {
      // Posição do servidor vale quando o cadastro local ainda não tem coordenadas.
      const srv = state.serverPos.get(c.id);
      return valid(c) || !srv ? c : { ...c, lat: srv.lat, lng: srv.lng };
    });
  }

  function render() {
    if (!state.map) return;
    const cams = allCameras();
    const seen = new Set();
    cams.filter(valid).forEach((c) => {
      seen.add(c.id);
      let m = state.markers.get(c.id);
      if (!m) {
        m = L.marker([c.lat, c.lng], { icon: iconFor(c), draggable: false, title: c.name, keyboard: true }).addTo(state.map);
        state.markers.set(c.id, m);
      } else {
        m.setLatLng([c.lat, c.lng]);
        m.setIcon(iconFor(c));
      }
      m.bindPopup(popupFor(c), { minWidth: 230 });
    });
    state.markers.forEach((m, id) => { if (!seen.has(id)) { state.map.removeLayer(m); state.markers.delete(id); } });

    // Câmeras cadastradas cujo endereço ainda não foi localizado: o endereço se informa aqui.
    const missing = cams.filter((c) => !valid(c));
    if (!unplacedBox) return;
    unplacedBox.classList.toggle('hidden', !missing.length);
    unplacedBox.innerHTML = missing.length
      ? '<div class="vmap-missing-title">Câmeras sem endereço no mapa</div>' + missing.map((c) =>
        '<div class="vmap-missing"><span class="vmap-missing-name">' + esc(c.name) + '</span>' + addrForm(c) +
        '<button type="button" class="vmap-del" data-vm-act="delete" data-id="' + esc(c.id) + '" aria-label="Excluir câmera ' + esc(c.name) + '">Excluir</button></div>').join('')
      : '';
  }

  /* ---------- salvar posição ---------- */
  async function setLocation(id, lat, lng, label) {
    lat = Math.round(lat * 1e6) / 1e6; lng = Math.round(lng * 1e6) / 1e6;
    CameraStore.update(id, { lat, lng });
    const cam = CameraStore.get(id);
    if (cam && (cam.serverManaged || state.serverIds.has(id) || id === 'cam_local')) {
      try {
        await getJSON('/api/cameras/' + encodeURIComponent(id) + '/location', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lat, lng, label: label || cam.location || null }) });
        state.serverPos.set(id, { lat, lng });
      } catch (err) {
        // Sem banco ativo a posição fica só neste navegador; avisa sem travar o cadastro.
        say('Posição salva só neste navegador: ' + err.message, 'warn');
      }
    }
  }

  const COORDS = /^\s*(-?\d{1,2}[.,]\d+)\s*[;,\s]\s*(-?\d{1,3}[.,]\d+)\s*$/;

  /** Localiza o endereço da câmera e a coloca no mapa. Devolve true se achou. */
  async function locate(id, text) {
    const typed = String(text || '').trim();
    const cam = CameraStore.get(id);
    if (!typed) { say('A câmera "' + (cam ? cam.name : id) + '" está sem endereço. Informe o endereço abaixo do mapa para ela aparecer aqui.', 'warn'); return false; }
    const m = COORDS.exec(typed);
    if (m) { await setLocation(id, parseFloat(m[1].replace(',', '.')), parseFloat(m[2].replace(',', '.')), typed); focus(id); return true; }
    try {
      const qs = new URLSearchParams({ q: typed });
      if (state.muni) qs.set('municipio', state.muni.id);
      const found = await getJSON('/api/geo/buscar?' + qs.toString());
      if (found.length) {
        CameraStore.update(id, { location: typed });
        await setLocation(id, found[0].lat, found[0].lng, typed);
        say('Endereço localizado: ' + found[0].label, 'info');
        focus(id);
        return true;
      }
    } catch (err) { say(err.message, 'warn'); return false; }
    say('Não encontrei "' + typed + '". Confira o endereço (rua, número e bairro) e tente de novo abaixo do mapa.', 'warn');
    return false;
  }
  function focus(id) {
    setTimeout(() => {
      const mk = state.markers.get(id);
      if (mk) { state.map.setView(mk.getLatLng(), Math.max(state.map.getZoom(), 16)); mk.openPopup(); }
    }, 150);
  }

  /* ---------- alterar endereço / excluir ---------- */
  document.addEventListener('submit', async (e) => {
    const form = e.target.closest('.vmap-addr');
    if (!form || !(el.contains(form) || unplacedBox?.contains(form))) return;
    e.preventDefault();
    const button = form.querySelector('button');
    button.disabled = true;
    await locate(form.dataset.id, form.elements.address.value);
    button.disabled = false;
  });

  async function removeCamera(id) {
    const cam = CameraStore.get(id);
    if (!cam || !confirm('Excluir a câmera "' + cam.name + '"? Ela deixa de ser monitorada e some do mapa.')) return;
    if (!cam.serverManaged && (state.serverIds.has(id) || id === 'cam_local')) {
      try { await getJSON('/api/cameras/' + encodeURIComponent(id), { method: 'DELETE' }); } catch (err) { say(err.message, 'err'); return; }
    }
    state.serverPos.delete(id);
    state.serverIds.delete(id);
    state.map.closePopup();
    CameraStore.remove(id);  // já avisa o servidor quando a câmera é dele
    say('Câmera excluída.', 'info');
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-vm-act="delete"]');
    if (b && (el.contains(b) || unplacedBox?.contains(b))) removeCamera(b.dataset.id);
  });

  /* ---------- início ---------- */
  CameraStore.subscribe(render);
  window.ViaMap = { locate, render, get map() { return state.map; }, get municipio() { return state.muni; } };

  (async () => {
    let meData = null;
    try { meData = await getJSON('/api/me'); } catch (_) { /* modo local */ }
    state.multiTenant = !!(meData && meData.multi_tenant);
    try { (await getJSON('/api/cameras')).forEach((c) => state.serverIds.add(c.id)); } catch (_) { /* sem lista */ }
    try { (await getJSON('/api/cameras/positions')).forEach((c) => { if (c.lat != null && c.lng != null) state.serverPos.set(c.camera_key, { lat: c.lat, lng: c.lng }); }); } catch (_) { /* sem banco */ }

    const chosen = (meData && meData.municipio) || savedMunicipio();
    if (chosen && chosen.id) await showMunicipio(chosen.id);
    else { render(); openPicker(true); }
  })();
})();

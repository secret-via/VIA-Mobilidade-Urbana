/* Aba Estatísticas: a análise detalhada do período NÃO é exibida na tela. O painel
   mostra apenas o esqueleto desfocado de cada gráfico; ao clicar, avisa que o
   detalhe vem no relatório (PDF). As formas são fixas e genéricas: nenhum número
   real passa por aqui, então desfocar não é um truque de CSS que dê para desfazer
   no inspetor. Os dados completos só existem no PDF exportado. */
(function () {
  const E = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const LOCK = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';

  /* ---- esqueletos genéricos (formas fixas) ---- */
  const BARS = [38, 52, 30, 64, 80, 58, 92, 70, 44, 60, 36, 74, 50, 66, 28, 84, 56, 40, 72, 48, 62, 34, 78, 54];
  const skelLine = () => '<svg viewBox="0 0 600 160" preserveAspectRatio="none" class="dv-sk"><path d="M0 120 C60 90 90 130 150 80 S250 30 300 70 S400 140 450 60 S560 40 600 90 L600 160 L0 160Z" fill="rgba(78,175,247,.25)"/><path d="M0 120 C60 90 90 130 150 80 S250 30 300 70 S400 140 450 60 S560 40 600 90" fill="none" stroke="#4eaff7" stroke-width="3"/></svg>';
  const skelBars = () => '<svg viewBox="0 0 480 160" preserveAspectRatio="none" class="dv-sk">' + BARS.map((h, i) => '<rect x="' + (i * 20 + 3) + '" y="' + (160 - h * 1.5) + '" width="14" height="' + (h * 1.5) + '" rx="3" fill="' + (i === 6 ? '#f0b74a' : '#4eaff7') + '"/>').join('') + '</svg>';
  const skelHeat = () => {
    let s = '<svg viewBox="0 0 480 140" preserveAspectRatio="none" class="dv-sk">';
    for (let r = 0; r < 7; r++) for (let c = 0; c < 24; c++) { const v = ((r * 7 + c * 3) % 11) / 10; s += '<rect x="' + (c * 20 + 1) + '" y="' + (r * 20 + 1) + '" width="18" height="18" rx="3" fill="rgba(78,175,247,' + (0.12 + v * 0.7).toFixed(2) + ')"/>'; }
    return s + '</svg>';
  };
  const skelRank = () => '<div class="dv-sk-rank">' + [92, 78, 66, 51, 40].map(w => '<i style="width:' + w + '%"></i>').join('') + '</div>';
  const skelCams = () => '<div class="dv-sk-rank">' + [88, 61, 47].map(w => '<i style="width:' + w + '%"></i>').join('') + '</div>';

  const KPIS = ['Variação vs período anterior'];  // os 3 primeiros indicadores são reais (ver realKpis)
  const CARDS = [
    ['Evolução do fluxo', 'Veículos ao longo do período', skelLine, 12],
    ['Perfil por horário', 'Total em cada hora do dia', skelBars, 6],
    ['Mapa de calor semanal', 'Dia da semana × hora', skelHeat, 6],
    ['Fluxo por câmera', 'Participação de cada ponto', skelCams, 6],
    ['Janelas de maior movimento', 'Os momentos de pico', skelRank, 6],
  ];

  /* Fluxo total, pico e hora mais movimentada aparecem de verdade (o "gostinho").
     São os únicos números que o servidor envia para esta tela. */
  const N = (n) => Number(n || 0).toLocaleString('pt-BR');
  function realKpi(label, value, note) {
    return '<div class="dv-kpi"><span class="dv-kpi-label">' + E(label) + '</span><div class="dv-kpi-row"><b>' + E(value) + '</b></div><span class="dv-kpi-note">' + E(note) + '</span></div>';
  }
  function realKpis(s) {
    if (!s) return '';
    const at = s.peak ? new Date(s.peak.at).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
    return realKpi('Fluxo total', N(s.total_vehicles), 'veículos no período') +
      (s.peak ? realKpi('Pico de movimento', N(s.peak.total), 'veículos em 15 min · ' + at) : '') +
      (s.busiest_hour ? realKpi('Hora mais movimentada', String(s.busiest_hour.hour).padStart(2, '0') + 'h', N(s.busiest_hour.total) + ' veículos nessa hora') : '');
  }

  function render(summary) {
    const kpis = realKpis(summary) + KPIS.map(k => '<button type="button" class="dv-kpi dv-lk" data-locked aria-label="' + E(k) + ' (bloqueado: baixe o relatório para ter acesso)"><span class="dv-kpi-label">' + E(k) + '</span><div class="dv-kpi-row"><b class="dv-blur-val">0.000</b></div></button>').join('');
    const cards = CARDS.map(([t, sub, sk, span]) => '<button type="button" class="panel dv-card dv-lk dv-s' + span + '" data-locked aria-label="' + E(t) + ' (bloqueado: baixe o relatório para ter acesso)"><div class="panel-head"><div><h2 class="panel-title">' + E(t) + '</h2><p class="panel-subtitle">' + E(sub) + '</p></div><span class="dv-lock-ic">' + LOCK + '</span></div><div class="dv-body dv-blurred">' + sk() + '</div></button>').join('');
    return '<div class="dv"><div class="dv-banner"><span class="dv-lock-ic">' + LOCK + '</span><div><b>Análise detalhada no relatório</b><span>Horários, picos, dias da semana, câmeras e comparações ficam no PDF exportado.</span></div><button type="button" class="button primary small" data-go-reports>Gerar relatório</button></div><div class="dv-kpis">' + kpis + '</div><div class="dv-grid">' + cards + '</div></div>';
  }

  /* ---- aviso ao clicar ---- */
  let toast = null, toastTimer = null;
  function showLocked() {
    if (!toast) {
      toast = document.createElement('div');
      toast.className = 'dv-toast';
      toast.setAttribute('role', 'status');
      toast.innerHTML = '<span class="dv-lock-ic">' + LOCK + '</span><span>Baixe o relatório para ter acesso</span><button type="button" class="button primary small" data-go-reports>Ir para Relatórios</button>';
      document.body.appendChild(toast);
    }
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 4500);
  }
  document.addEventListener('click', e => {
    if (e.target.closest('[data-go-reports]')) {
      if (toast) toast.classList.remove('show');
      if (typeof navigate === 'function') navigate('reports');
      return;
    }
    if (e.target.closest('[data-locked]')) showLocked();
  });

  /* `filters.has_data`: só mostra o esqueleto se houve leitura no período; sem leitura
     o painel diz isso com todas as letras, em vez de sugerir que há algo atrás do desfoque. */
  function load(filters, target) {
    const el = typeof target === 'string' ? document.querySelector(target) : target;
    if (!el) return;
    el.innerHTML = filters && filters.has_data
      ? render(filters.summary)
      : '<section class="panel"><div class="empty"><strong>Nenhuma leitura neste período</strong>Nenhuma câmera enviou dados neste intervalo. Este painel mostra só o que foi realmente registrado.</div></section>';
  }

  window.VIADeep = { load };
})();

/* Menu de conta: carrega /api/me ao abrir e mostra plano, consumo e atalhos. */
(() => {
  // Links vindos das Configurações (…/#contato) abrem direto o chamado de suporte.
  if (location.hash === '#contato') {
    history.replaceState(null, '', location.pathname + location.search);
    document.getElementById('openContact')?.click();
  }

  const root = document.getElementById('acct');
  if (!root) return;
  const button = document.getElementById('acctBtn');
  const menu = document.getElementById('acctMenu');

  const ROLES = { via_admin: 'Equipe VIA', owner: 'Responsável', member: 'Usuário' };
  const STATUS = { active: 'Ativa', inactive: 'Suspensa', expired: 'Plano expirado' };

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const ICONS = {
    gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M4.9 4.9 7 7m10 10 2.1 2.1M2 12h3m14 0h3M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01"/>',
    doc: '<path d="M6 3h9l3 3v15H6zM9 12h6m-6 4h6"/>',
    out: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
    up: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  };
  const icon = (name) => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.innerHTML = ICONS[name];
    return svg;
  };

  function item(label, iconName, { href, onClick, className } = {}) {
    const node = href ? el('a', 'acct-item') : el('button', 'acct-item');
    if (href) node.href = href;
    else node.type = 'button';
    if (className) node.classList.add(className);
    node.setAttribute('role', 'menuitem');
    node.append(icon(iconName), document.createTextNode(label));
    if (onClick) node.addEventListener('click', onClick);
    return node;
  }

  function usageRow(label, used, limit) {
    const row = el('div', 'acct-row');
    const top = el('div', 'top');
    top.append(el('span', null, label));
    if (limit === 0) {
      top.append(el('span', null, 'não incluído'));
      row.append(top);
      return row;
    }
    const unlimited = limit === null || limit === undefined;
    top.append(el('span', null, unlimited ? `${used} · ilimitado` : `${used} / ${limit}`));
    row.append(top);
    if (!unlimited) {
      const ratio = limit ? used / limit : 1;
      const bar = el('div', `acct-bar${ratio >= 1 ? ' full' : ratio >= 0.8 ? ' warn' : ''}`);
      const fill = el('i');
      fill.style.width = `${Math.min(100, ratio * 100)}%`;
      bar.append(fill);
      row.append(bar);
    }
    return row;
  }

  function needsUpgrade(me) {
    const { org, usage } = me;
    const near = (used, limit) => limit !== null && limit !== undefined && limit > 0 && used / limit >= 0.8;
    return (
      near(usage.pdf, org.pdf_per_month) || near(usage.chat, org.chat_per_month) ||
      near(usage.cameras, org.max_cameras) || near(usage.users, org.max_users) ||
      org.chat_per_month === 0 || org.status !== 'active'
    );
  }

  function render(me) {
    menu.replaceChildren();
    if (!me.multi_tenant) return;
    const { org, usage } = me;

    const head = el('div', 'acct-head');
    head.append(el('div', 'acct-email', me.email));
    const orgRow = el('div', 'acct-org');
    orgRow.append(el('span', 'acct-avatar', (org.name || '?').slice(0, 1).toUpperCase()));
    const orgText = el('div');
    orgText.append(el('b', null, org.name), el('span', 'role', ROLES[me.role] || me.role));
    orgRow.append(orgText);
    head.append(orgRow);
    menu.append(head);

    const plan = el('div', 'acct-plan');
    plan.append(el('b', null, org.plan_label), el('span', `acct-tag ${org.status}`, STATUS[org.status] || org.status));
    menu.append(plan);

    const box = el('div', 'acct-usage');
    box.append(el('div', 'acct-usage-title', 'Uso do plano'));
    box.append(usageRow('Câmeras', usage.cameras, org.max_cameras));
    box.append(usageRow('Relatórios PDF no mês', usage.pdf, org.pdf_per_month));
    box.append(usageRow('Consultas ao assistente', usage.chat, org.chat_per_month));
    box.append(usageRow('Usuários', usage.users, org.max_users));
    menu.append(box);

    menu.append(el('div', 'acct-sep'));
    const contact = () => { close(); document.getElementById('openContact')?.click(); };
    if (needsUpgrade(me) && me.role !== 'via_admin') {
      menu.append(item('Ampliar plano com a VIA', 'up', { onClick: contact, className: 'upgrade' }));
    }
    menu.append(item('Configurações', 'gear', { href: '/configuracoes/perfil' }));
    if (me.role === 'via_admin') menu.append(item('Administração VIA', 'shield', { href: '/configuracoes/administracao' }));
    menu.append(item('Contato / Suporte', 'help', { onClick: contact }));
    menu.append(item('Termos e Privacidade', 'doc', {
      onClick: () => { close(); document.getElementById('openTerms')?.click(); },
    }));
    menu.append(el('div', 'acct-sep'));

    const form = el('form');
    form.method = 'post';
    form.action = '/logout';
    const out = item('Sair', 'out');
    out.type = 'submit';
    form.append(out);
    menu.append(form);
  }

  let loading = false;
  async function refresh() {
    if (loading) return;
    loading = true;
    try {
      const response = await fetch('/api/me', { cache: 'no-store' });
      if (response.ok) render(await response.json());
    } catch (_) { /* mantém o conteúdo anterior */ }
    loading = false;
  }

  function open() {
    menu.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    refresh();
  }
  function close() {
    menu.hidden = true;
    button.setAttribute('aria-expanded', 'false');
  }

  button.addEventListener('click', () => (menu.hidden ? open() : close()));
  document.addEventListener('click', (event) => { if (!root.contains(event.target)) close(); });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !menu.hidden) { close(); button.focus(); }
  });
  refresh();
})();

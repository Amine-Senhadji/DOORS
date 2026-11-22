// Le tiroir : les hypothèses avec leur nature et leur source, les vérifications en direct, le registre d'un mois
// du trajet affiché, et les limites du modèle. Fermé par défaut.
// Chaque chiffre vient de l'API ; les phrases sont dans texts.fr.js.
import { T } from './texts.fr.js';
import { ageAtMonth, chf, plain } from './format.js';

const escapeHtml = (text) => String(text).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const isShare = (unit) => unit.startsWith('%');

/** Une valeur telle qu'on la saisit : une part s'écrit en pour cent (0,02 devient 2). Mise en forme, pas un calcul financier. */
const shown = (a, value) => (isShare(a.unit) ? Number((value * 100).toFixed(6)) : value);
const stored = (a, typed) => (isShare(a.unit) ? typed / 100 : typed);

function assumptionsHtml(assumptions, overrides) {
  const changed = Object.keys(overrides).length;
  let html = `<p class="soft">${escapeHtml(T.drawer.assumptionsHelp)}</p>`;
  if (changed) html += `<p class="num"><strong>${escapeHtml(T.drawer.changed(changed))}</strong> <button type="button" class="link" data-reset="*">${escapeHtml(T.drawer.resetAll)}</button></p>`;
  html += '<div class="assumptions">';
  for (const a of assumptions) {
    const modified = a.key in overrides;
    const value = modified ? overrides[a.key] : a.value;
    html += `<div class="assumption${modified ? ' modified' : ''}" data-key="${escapeHtml(a.key)}">`
      + `<label><span>${escapeHtml(a.label)}</span>`
      + `<span class="field"><input type="number" step="any" class="num" data-key="${escapeHtml(a.key)}" value="${shown(a, value)}">`
      + `<em>${escapeHtml(a.unit)}</em></span></label>`
      + `<p class="origin"><span class="kind ${escapeHtml(a.kind)}">${escapeHtml(T.kinds[a.kind] ?? a.kind)}</span> ${escapeHtml(a.source)}</p>`;
    if (modified) {
      html += `<p class="num mark">${escapeHtml(T.drawer.modified(plain(shown(a, a.value)), a.unit))} `
        + `<button type="button" class="link" data-reset="${escapeHtml(a.key)}">${escapeHtml(T.drawer.reset)}</button></p>`;
    }
    html += '</div>';
  }
  return `${html}</div>`;
}

function checksHtml(checks, kit) {
  let html = `<p class="soft">${escapeHtml(T.drawer.checksHelp)}</p><ul class="checks">`;
  for (const check of checks ?? []) {
    html += `<li class="${check.ok ? 'ok' : 'ko'}"><i></i><span><strong>${escapeHtml(check.title)}</strong> ${escapeHtml(check.detail)}</span></li>`;
  }
  html += '</ul>';
  html += `<button type="button" class="pill" id="run-kit">${escapeHtml(T.drawer.runKit)}</button>`;
  if (kit) {
    html += `<ul class="checks"><li class="${kit.ok ? 'ok' : 'ko'}"><i></i><span><strong>${escapeHtml(kit.title)}</strong> ${escapeHtml(kit.detail)} `
      + `<span class="num">${escapeHtml(T.drawer.kitResult(kit.total - kit.failed, kit.total, kit.duration_s, kit.ran_at.slice(11)))}</span></span></li></ul>`;
    for (const failure of kit.failures) html += `<p class="small">${escapeHtml(failure.test)} : ${escapeHtml(failure.message)}</p>`;
  }
  return html;
}

function ledgerHtml(trip, month, world, startAge) {
  const record = trip.months[month];
  let html = `<p class="soft">${escapeHtml(T.drawer.ledgerHelp(world.name))}</p>`
    + `<label class="month"><span>${escapeHtml(T.drawer.month(month, ageAtMonth(month, startAge)))}</span>`
    + `<input type="range" id="ledger-month" min="0" max="${trip.months.length - 1}" step="1" value="${month}"></label>`
    + `<table class="ledger num"><tbody><tr class="total"><th colspan="2">${escapeHtml(T.drawer.opening)}</th><td>${escapeHtml(chf(record.opening_cash_chf))}</td></tr>`;
  for (const flow of record.flows) {
    // Une ligne de montant 0 est une note : une explication du moteur, pas un mouvement.
    if (flow.amount_chf === 0) html += `<tr class="note"><td colspan="3">${escapeHtml(T.drawer.note(flow.label))}</td></tr>`;
    else {
      html += `<tr><th>${escapeHtml(flow.label)}</th><td class="account">${escapeHtml(T.drawer.accounts[flow.account] ?? flow.account)}</td>`
        + `<td>${flow.amount_chf > 0 ? '+' : ''}${escapeHtml(chf(flow.amount_chf))}</td></tr>`;
    }
  }
  html += `<tr class="total"><th colspan="2">${escapeHtml(T.drawer.closing)}</th><td>${escapeHtml(chf(record.closing_cash_chf))}</td></tr>`
    + `<tr><th colspan="2">${escapeHtml(T.drawer.debt)}</th><td>${escapeHtml(chf(record.debt_chf))}</td></tr>`
    + `<tr><th colspan="2">${escapeHtml(T.drawer.netWorth)}</th><td>${escapeHtml(chf(record.net_worth_chf))}</td></tr></tbody></table>`;
  return html;
}

/**
 * Dessine le tiroir.
 * @param data      { assumptions, overrides, checks, kit, limits, trip, month, world, startAge, section }
 * @param handlers  { onClose, onChange(key, value), onReset(key | '*'), onRunKit, onMonth(month), onSection(name) }
 */
export function renderDrawer(host, data, handlers) {
  const section = (name, body) => `<details class="section" data-section="${name}"${data.section === name ? ' open' : ''}>`
    + `<summary>${escapeHtml(T.drawer.sections[name])}</summary>${body}</details>`;
  host.innerHTML = `<div class="drawer-top"><h2>${escapeHtml(T.drawer.title)}</h2>`
    + `<button type="button" class="pill" id="drawer-close">${escapeHtml(T.drawer.close)}</button></div>`
    + section('hypotheses', assumptionsHtml(data.assumptions, data.overrides))
    + section('verifications', checksHtml(data.checks, data.kit))
    + section('registre', ledgerHtml(data.trip, data.month, data.world, data.startAge))
    + section('limites', `<p class="soft">${escapeHtml(T.drawer.limitsHelp(data.limits.source))}</p><ul class="limits">`
      + data.limits.limits.map((limit) => `<li>${escapeHtml(limit)}</li>`).join('') + '</ul>');

  host.querySelector('#drawer-close').addEventListener('click', handlers.onClose);
  host.querySelectorAll('details.section').forEach((node) => {
    node.addEventListener('toggle', () => { if (node.open) handlers.onSection(node.dataset.section); });
  });
  host.querySelectorAll('.assumption input').forEach((input) => {
    input.addEventListener('change', () => {
      const a = data.assumptions.find((item) => item.key === input.dataset.key);
      if (input.value !== '' && Number.isFinite(Number(input.value))) handlers.onChange(a.key, stored(a, Number(input.value)));
    });
  });
  host.querySelectorAll('[data-reset]').forEach((button) => button.addEventListener('click', () => handlers.onReset(button.dataset.reset)));
  host.querySelector('#run-kit').addEventListener('click', handlers.onRunKit);
  host.querySelector('#ledger-month').addEventListener('change', (event) => handlers.onMonth(Number(event.target.value)));
}

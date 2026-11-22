// Les fiches : le trajet en cours, une station, une gare de correspondance.
// Chaque fiche tient en quelques lignes ; le reste est rangé sous « Détails ».
// Chaque chiffre vient de l'API ; les phrases sont dans texts.fr.js.
import { T } from './i18n.js';
import { ageAtMonth, chf, plain, ranges } from './format.js';
import { lightOf, stateOf, symbol } from './map.js';

const escapeHtml = (text) => String(text).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const COLOR = { open: 'var(--open)', ajar: 'var(--ajar)', closed: 'var(--closed)', unknown: 'var(--unknown)' };
const p = (text, className = '') => `<p${className ? ` class="${className}"` : ''}>${escapeHtml(text)}</p>`;
const details = (html) => `<details class="fold"><summary>${escapeHtml(T.card.details)}</summary>${html}</details>`;
const back = (onBack) => (onBack ? `<button type="button" class="link" id="card-back">${escapeHtml(T.card.back)}</button>` : '');

/** Le nom du monde d'où vient un chiffre du « pire monde testé » ; aucun si tous les mondes testés donnent le même. */
const from = (worlds, id) => (id === null ? T.bands.everywhere : (worlds.find((w) => w.id === id)?.name ?? id).toLowerCase());

/** Les trois bandes d'un trajet : pire monde testé, central, prudent. Chaque chiffre vient du moteur (/path, bands). */
function bandsTable(bands, worlds) {
  const B = T.bands;
  let html = `<h3 class="bands-title">${escapeHtml(B.title)}</h3><table class="worlds bands num"><thead><tr>`
    + B.columns.map((name) => `<th>${escapeHtml(name)}</th>`).join('') + '</tr></thead><tbody>';
  for (const name of ['pire', 'central', 'prudent']) {
    const band = bands[name];
    const where = (cell) => (name === 'pire' ? `<small>${escapeHtml(from(worlds, cell.world_id))}</small>` : '');
    html += `<tr data-band="${name}"><th>${escapeHtml(B[name])}</th>`
      + `<td>${escapeHtml(B.count(band.doors_open.value, bands.doors_total))}${where(band.doors_open)}</td>`
      + `<td>${escapeHtml(chf(band.peak_financing_chf.value))}${where(band.peak_financing_chf)}</td>`
      + `<td>${escapeHtml(chf(band.net_worth_end_chf.value))}${where(band.net_worth_end_chf)}</td></tr>`;
  }
  return `${html}</tbody></table>`;
}

/** Le besoin de financement d'un trajet dans un monde, en une phrase. */
function financing(summary, startAge) {
  const spans = ranges(summary.financing_months);
  if (!spans.length) return T.card.noFinancing;
  return T.card.financing(summary.financing_months.length, ageAtMonth(spans[0][0], startAge),
    ageAtMonth(spans.at(-1)[1] + 1, startAge), chf(summary.peak_financing_chf));
}

/**
 * La fiche du trajet en cours : ce qu'il donne dans le monde affiché ; sous « Détails », dans chaque monde testé.
 * @param trip  la réponse de /path
 */
export function renderTripCard(card, { title, trip, worlds, world, profile, endAge, onObserve }) {
  const shown = trip.by_world[world.id];
  const tested = worlds.filter((w) => trip.by_world[w.id]);
  card.style.removeProperty('--c');
  let table = `<h3>${escapeHtml(T.card.worlds(tested.length))}</h3><table class="worlds num"><thead><tr>`
    + T.card.columns.map((name) => `<th>${escapeHtml(name)}</th>`).join('') + '</tr></thead><tbody>';
  for (const w of tested) {
    const s = trip.by_world[w.id];
    table += `<tr${w.id === world.id ? ' class="shown"' : ''}><th>${escapeHtml(w.name)}</th>`
      + `<td>${s.doors_open} / ${s.doors_total}</td><td>${escapeHtml(chf(s.peak_financing_chf))}</td>`
      + `<td>${escapeHtml(chf(s.net_worth_end_chf))}</td></tr>`;
  }
  table += `</tbody></table>${p(T.bands.note(T.bands.points(trip.bands.prudent_points, plain(trip.bands.prudent_points))))}${p(T.card.origin, 'origin')}`;
  card.innerHTML = `<div class="state">${escapeHtml(T.card.trip)}</div><h2>${escapeHtml(title)}</h2>`
    + p(T.card.shown(world.name), 'soft')
    + p(`${T.card.open(shown.doors_open, shown.doors_total)}.`, 'num') + p(financing(shown, profile.age), 'num')
    + p(T.card.netWorth(endAge, chf(shown.net_worth_end_chf)), 'num')
    + bandsTable(trip.bands, worlds)
    + (trip.observation ? `<p class="seen num">${escapeHtml(T.card.observe.trip(trip.observation.age, chf(trip.observation.value_chf)))} `
      + `<button type="button" class="link" id="observe-forget">${escapeHtml(T.card.observe.forget)}</button></p>` : '')
    + details(table) + p(T.card.pick, 'wait');
  card.querySelector('#observe-forget')?.addEventListener('click', () => onObserve(null, null));
}

/**
 * La fiche d'une station : son état dans le monde affiché et pourquoi, et la correspondance qui la sauve.
 * Sous « Détails » : sa règle, chaque monde testé, le point de bascule et le point de non-retour, son origine.
 * @param door      la description de la porte, dans /path
 * @param pathways  la réponse de /pathways pour le trajet en cours
 */
export function renderStationCard(card, { door, trip, pathways, worlds, world, profile, onGare, onBack }) {
  const light = lightOf(door.key, trip.by_world, world.id);
  const tested = worlds.filter((w) => trip.by_world[w.id]);
  const isOpen = (w) => stateOf(trip.by_world[w.id].doors[door.key]) === 'ouverte';
  const margin = (w) => {
    const result = trip.by_world[w.id].doors[door.key];
    return result?.value_chf == null || door.whole_trip ? '' : T.card.margin(chf(result.value_chf), chf(result.required_chf));
  };
  const row = pathways?.by_world[world.id]?.doors.find((r) => r.key === door.key);
  card.style.setProperty('--c', COLOR[light]);

  let html = `<div class="state"><span class="lamp"></span>`
    + `${escapeHtml(T.card.stateAt(T.states[light], door.whole_trip ? T.wholeTrip : T.age(door.age)))}</div>`
    + `<h2>${escapeHtml(door.name)}</h2>`;
  if (margin(world)) html += p(T.card.here(margin(world)), 'num');
  html += p(T.worldsOpen(tested.filter(isOpen).length, tested.length), 'share num');
  // Les trois bandes de cette station : ce qu'elle atteint dans le pire monde testé, le monde de référence, le monde prudent.
  const band = trip.bands.doors[door.key];
  const said = (d) => T.doorState[d.state] ?? d.state;
  html += p(band.central.value_chf == null || door.whole_trip
    ? T.bands.stationState(said(band.pire), from(worlds, band.pire.world_id), said(band.central), said(band.prudent))
    : T.bands.station(chf(band.pire.value_chf), from(worlds, band.pire.world_id), chf(band.central.value_chf), chf(band.prudent.value_chf),
      chf(band.central.required_chf)), 'bands-line num');
  if (row && !row.holds && row.last_transfer) {
    const where = row.last_transfer.gare_month === 0 ? T.card.atDeparture(row.last_transfer.age) : T.card.atGare(row.last_transfer.age);
    html += `<p class="num last-transfer"><span class="diamond last">${symbol('gare')}</span>`
      + `<span>${escapeHtml(T.card.lastTransfer(where, row.last_transfer.label))}</span></p>`
      + `<button type="button" class="pill" id="see-gare">${escapeHtml(T.card.seeGare)}</button>`;
  } else if (row && !row.holds) html += p(T.card.noReturnAtStart);
  if (row?.signpost) html += `<p class="signpost"><strong>${escapeHtml(T.card.signpost)}</strong> ${escapeHtml(row.signpost.text)}</p>`;

  let more = p(door.rule, 'rule num') + '<ul class="world-lamps">';
  for (const w of tested) {
    const state = stateOf(trip.by_world[w.id].doors[door.key]);
    more += `<li class="${isOpen(w) ? 'open' : 'closed'}${w.id === world.id ? ' shown' : ''}"><i></i>`
      + `<span>${escapeHtml(w.name)} : ${escapeHtml(T.doorState[state] ?? state)}${margin(w) ? escapeHtml(` · ${margin(w)}`) : ''}</span></li>`;
  }
  more += '</ul>';
  if (row && !row.holds) {
    if (row.tipping) more += p(T.card.tipping(ageAtMonth(row.tipping.month, profile.age)), 'num');
    if (row.last_transfer && row.no_return) more += p(T.card.noReturn(row.no_return.age), 'num');
  } else if (row) more += p(T.card.holds);
  if (door.source) more += p(T.card.source(T.kinds[door.kind] ?? door.kind, door.source), 'origin');
  html += details(more) + back(onBack);
  card.innerHTML = html;
  card.querySelector('#see-gare')?.addEventListener('click', () => onGare(row.last_transfer.gare_month));
  card.querySelector('#card-back')?.addEventListener('click', onBack);
}

/**
 * La fiche d'une gare : ce qui reste atteignable d'ici, où en sont les crises testées, et les branches à prendre.
 * @param node      la réponse de /node pour cette gare
 * @param trip      la réponse de /path pour le trajet en cours (les noms des portes)
 * @param pathways  la réponse de /pathways pour ce trajet (les signaux à surveiller)
 */
export function renderGareCard(card, { node, trip, pathways, worlds, world, profile, onTake, onBack, onObserve }) {
  const names = Object.fromEntries(trip.doors.map((door) => [door.key, door.name]));
  const flex = node.flexibility;
  const lost = Object.keys(flex.by_door).filter((key) => !flex.by_door[key].possible);
  const named = (keys) => keys.map((key) => T.quoted(names[key] ?? key));
  const here = node.state_by_world[world.id];
  card.style.removeProperty('--c');

  let html = `<div class="state"><span class="diamond">${symbol('gare')}</span>`
    + `${escapeHtml(node.gare_month === 0 ? T.card.departure(node.age) : T.card.gare(node.age))}</div>`
    + p(T.card.flexibility(flex.robust.length, flex.possible.length, flex.doors_total), 'flex num')
    + '<div class="gauge" aria-hidden="true">'
    + flex.robust.map(() => '<i class="robust"></i>').join('') + flex.possible.map(() => '<i class="possible"></i>').join('')
    + lost.map(() => '<i class="lost"></i>').join('') + '</div>';
  // Où en sont les crises testées à cet âge, telles que le moteur le dit : déjà eu lieu, en cours, à venir.
  // Après le début d'une crise, l'état de la gare en porte déjà la trace.
  const standing = (w) => node.state_by_world[w.id]?.crises ?? [];
  const alone = worlds.filter((w) => standing(w).length === 1);
  const inState = (status) => alone.filter((w) => standing(w)[0].status === status).map((w) => w.name);
  if (alone.length) html += p(T.card.shocks(node.age, inState('passee'), inState('en_cours'), inState('a_venir')), 'small');
  // Un monde à deux crises : chacune avec son état.
  for (const w of worlds) {
    if (standing(w).length > 1) html += p(T.card.combined(node.age, standing(w)), 'small');
  }
  // Les signaux à surveiller à cette gare, pour le trajet en cours et dans le monde affiché.
  for (const row of pathways?.by_world[world.id]?.doors ?? []) {
    if (row.signpost && row.signpost.gare_month === node.gare_month) {
      html += `<p class="signpost"><strong>${escapeHtml(T.card.signpost)}</strong> ${escapeHtml(row.signpost.text)}</p>`;
    }
  }

  // Le jumeau qui apprend : ce qu'Alexia a vraiment de côté à cette gare remplace l'épargne simulée.
  if (node.gare_month > 0 && here) {
    const seen = node.observation?.gare_month === node.gare_month ? node.observation : null;
    html += `<form class="observe" id="observe"><label for="observe-value">${escapeHtml(T.card.observe.ask)}</label>`
      + `<span class="hint">${escapeHtml(T.card.observe.hint)}</span><div class="row">`
      + `<input id="observe-value" type="number" step="100" inputmode="decimal" required value="${seen ? escapeHtml(seen.value_chf) : ''}">`
      + `<span>${escapeHtml(T.card.observe.unit)}</span>`
      + `<button type="submit" class="pill">${escapeHtml(T.card.observe.apply)}</button></div>`;
    if (seen) {
      for (const signal of seen.signals) html += `<p class="signpost side" data-side="${escapeHtml(signal.side)}">${escapeHtml(signal.text)}</p>`;
      if (!seen.signals.length) html += p(T.card.observe.noSignal, 'small');
      html += p(T.card.observe.instead(world.name, chf(seen.simulated_chf[world.id])), 'small num')
        + `<button type="button" class="link" id="observe-forget">${escapeHtml(T.card.observe.forget)}</button>`;
    } else {
      html += p(T.card.observe.simulated(world.name, chf(here.liquidite_chf)), 'small num');
      if (node.observation) html += p(T.card.observe.elsewhere(node.observation.age, chf(node.observation.value_chf)), 'small num');
    }
    html += '</form>';
  }

  html += `<h3 class="branches">${escapeHtml(T.card.branches)}</h3>`;
  const best = node.best_by_world.find((b) => b.world_id === world.id);
  node.branches.forEach((branch, index) => {
    const s = branch.by_world?.[world.id];
    const closed = branch.available === false;
    html += `<div class="branch${branch.on_path ? ' current' : ''}${closed ? ' barred' : ''}" data-branch="${escapeHtml(branch.id)}">`
      + `<strong>${escapeHtml(branch.label)}</strong>`;
    if (branch.on_path) html += `<span class="tag">${escapeHtml(T.card.current)}</span>`;
    if (closed) html += p(`${T.card.barred}. ${branch.reason ?? ''}`.trim(), 'small');
    else if (s) {
      html += p(T.card.summary(T.card.open(s.doors_open, s.doors_total), chf(s.peak_financing_chf), chf(s.net_worth_end_chf)), 'small num');
      if (best?.branch_id === branch.id && best.doors_more_than_staying > 0) html += p(T.card.more(branch.label, best.doors_more_than_staying), 'small num');
      if (!branch.on_path) html += `<button type="button" class="pill take" data-take="${index}">${escapeHtml(T.card.take)}</button>`;
    }
    html += '</div>';
  });

  let more = p(T.card.horizon(flex.horizon));
  if (flex.robust.length) more += p(T.card.robust(named(flex.robust)));
  if (flex.possible.length) more += p(T.card.possible(named(flex.possible)));
  if (lost.length) more += p(T.card.lost(named(lost)));
  more += p(node.branches.length < 2 ? T.card.alone : node.matters ? T.card.matters : T.card.quiet);
  if (here) more += p(T.card.state(world.name, chf(here.cash_chf), chf(here.debt_chf), chf(here.net_worth_chf)), 'num');
  more += p(T.card.origin, 'origin');
  html += details(more) + back(onBack);
  card.innerHTML = html;
  card.querySelectorAll('[data-take]').forEach((button) => {
    button.addEventListener('click', () => onTake(node.branches[Number(button.dataset.take)]));
  });
  card.querySelector('#card-back')?.addEventListener('click', onBack);
  card.querySelector('#observe')?.addEventListener('submit', (event) => {
    event.preventDefault();
    const typed = card.querySelector('#observe-value').value;
    if (typed !== '' && Number.isFinite(Number(typed))) onObserve(node.gare_month, Number(typed));
  });
  card.querySelector('#observe-forget')?.addEventListener('click', () => onObserve(null, null));
}

/**
 * Le panneau « Plan figé ou politique » : dans le monde affiché, le trajet sans changement contre le même
 * trajet qui applique la règle ; puis le résumé sur tous les mondes testés.
 * @param plan  la réponse de /adaptive pour le trajet en cours
 */
export function renderPlanCard(card, { plan, trip, worlds, world, onBack }) {
  const names = Object.fromEntries(trip.doors.map((door) => [door.key, door.name]));
  const named = (keys) => keys.map((key) => T.quoted(names[key] ?? key));
  const here = plan.by_world[world.id];
  const tested = worlds.filter((w) => plan.by_world[w.id]);
  card.style.removeProperty('--c');

  let html = `<div class="state">${escapeHtml(T.plan.title)}</div>`
    + `<p class="rule-text num"><strong>${escapeHtml(T.plan.rule)}</strong> ${escapeHtml(plan.rule.text)}</p>`
    + p(plan.observation?.gare_month === plan.rule.gare_month
      ? T.plan.seen(plan.rule.age, chf(plan.observation.value_chf), here.adaptive.applies)
      : T.plan.observed(world.name, plan.rule.age, chf(here.adaptive.observed_chf), here.adaptive.applies), 'small num');
  // Une épargne constatée avant la gare de la règle : les deux plans la suivent. Après : elle arrive trop tard pour la règle.
  if (plan.observation && plan.observation.gare_month !== plan.rule.gare_month) html += p(T.plan.since(plan.observation.age, chf(plan.observation.value_chf)), 'small num');
  if (trip.observation && !plan.observation) html += p(T.plan.tooLate(trip.observation.age), 'small num');
  const row = (label, fixed, adaptive) => `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(fixed)}</td><td>${escapeHtml(adaptive)}</td></tr>`;
  html += `<table class="plans num"><thead><tr><th></th><th>${escapeHtml(T.plan.fixed)}</th><th>${escapeHtml(T.plan.adaptive)}</th></tr></thead><tbody>`
    + row(T.plan.kept, T.plan.count(here.fixed.doors_open, here.fixed.doors_total), T.plan.count(here.adaptive.doors_open, here.adaptive.doors_total))
    + row(T.plan.borrowing, chf(here.fixed.peak_financing_chf), chf(here.adaptive.peak_financing_chf))
    + row(T.plan.worth, chf(here.fixed.net_worth_end_chf), chf(here.adaptive.net_worth_end_chf)) + '</tbody></table>';
  if (here.adaptive.applies) {
    const saved = here.saved;
    if (saved.doors_reopened.length) html += p(T.plan.reopened(named(saved.doors_reopened)), 'num');
    if (saved.doors_lost.length) html += p(T.plan.lost(named(saved.doors_lost)), 'num');
    if (saved.financing_avoided_chf > 0) html += p(T.plan.avoided(chf(saved.financing_avoided_chf)), 'num');
  }
  // Le résumé sur tous les mondes testés, pour l'objectif que la règle cherche à garder.
  const target = plan.target_door && plan.summary.doors_kept[plan.target_door];
  if (target) html += p(T.plan.summary(names[plan.target_door], target.adaptive, target.fixed, plan.summary.worlds), 'flex num');

  let more = `<table class="worlds num"><thead><tr>` + T.plan.columns.map((name) => `<th>${escapeHtml(name)}</th>`).join('') + '</tr></thead><tbody>';
  for (const w of tested) {
    const r = plan.by_world[w.id];
    more += `<tr${w.id === world.id ? ' class="shown"' : ''}><th>${escapeHtml(w.name)}</th>`
      + `<td>${r.fixed.doors_open} / ${r.fixed.doors_total}</td><td>${r.adaptive.doors_open} / ${r.adaptive.doors_total}</td>`
      + `<td>${escapeHtml(r.adaptive.applies ? chf(r.saved.financing_avoided_chf) : T.plan.same)}</td></tr>`;
  }
  more += `</tbody></table>${p(T.plan.onlyState)}${p(T.card.origin, 'origin')}`;
  html += details(more) + back(onBack);
  card.innerHTML = html;
  card.querySelector('#card-back')?.addEventListener('click', onBack);
}

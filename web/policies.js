// La feuille « Des politiques, pas des plans » : le tableau de valeur.
// Le plan figé et les trois politiques en lignes, les mondes en colonnes. Dans chaque case, au même niveau : les
// objectifs gardés et ce que devient le master. Puis l'emprunt maximal et le regret.
// Chaque chiffre vient de la route /policies, donc du moteur ; rien n'est calculé ici.
import { T } from './i18n.js';
import { chf, plain } from './format.js';

const escapeHtml = (text) => String(text).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const p = (text, className = '') => `<p${className ? ` class="${className}"` : ''}>${escapeHtml(text)}</p>`;
const P = T.policies;

/** Le nom d'un monde du tableau : son nom, l'âge de sa crise, sa durée ou sa gravité quand elles comptent. */
function worldName(world) {
  if (!world.adjustable) return P.noShock;
  const lasting = world.parameters.find((parameter) => typeof parameter.value === 'boolean' && parameter.months > 1);
  return P.world(world.name, world.age, world.highlight && lasting ? lasting.months : null, world.gravity);
}

const fate = (master) => P.fate[master.state](master.age);

function cell(shown, rowId, world) {
  const c = shown.cells[rowId][world.id];
  const tag = rowId === 'fige' ? '' : `<span class="tag">${escapeHtml(c.applies ? P.applies : P.follows)}</span>`;
  return `<td class="cell${world.highlight ? ' long' : ''}" data-row="${escapeHtml(rowId)}" data-world="${escapeHtml(world.id)}">`
    + `<strong class="kept num">${escapeHtml(P.kept(c.doors_open, c.doors_total))}</strong>`
    + `<strong class="fate">${escapeHtml(fate(c.master))}</strong>`
    + `<dl class="num"><dt>${escapeHtml(P.borrowing)}</dt><dd>${escapeHtml(chf(c.peak_financing_chf))}</dd>`
    + `<dt>${escapeHtml(P.regret)}</dt><dd>${escapeHtml(chf(c.regret_chf))}</dd></dl>${tag}</td>`;
}

function table(data, shown) {
  let html = '<table class="value"><thead><tr><th></th>'
    + data.worlds.map((world) => `<th class="${world.highlight ? 'long' : ''}" data-world="${escapeHtml(world.id)}">`
      + `${escapeHtml(worldName(world))}${world.highlight ? `<span class="tag">${escapeHtml(P.long)}</span>` : ''}</th>`).join('')
    + '</tr></thead><tbody>';
  for (const row of data.policies) {
    html += `<tr data-policy="${escapeHtml(row.id)}"><th><span class="name">${escapeHtml(row.name)}</span>`
      + `<span class="rule num">${escapeHtml(row.rule ? row.rule.text : P.fixedRule)}</span>`
      + `<span class="how">${escapeHtml(P.how[row.id] ?? '')}</span></th>`
      + data.worlds.map((world) => cell(shown, row.id, world)).join('') + '</tr>';
  }
  // La référence clairvoyante : ce qu'on aurait choisi en connaissant le monde à l'avance. Jamais une action possible.
  html += `<tr class="seer"><th><span class="name">${escapeHtml(P.seer)}</span><span class="how">${escapeHtml(P.seerHow)}</span></th>`
    + data.worlds.map((world) => {
      const c = shown.clairvoyant[world.id];
      return `<td class="cell${world.highlight ? ' long' : ''}"><strong class="kept num">${escapeHtml(P.kept(c.doors_open, c.doors_total))}</strong>`
        + `<strong class="fate">${escapeHtml(fate(c.master))}</strong><span class="tag">${escapeHtml(c.label)}</span></td>`;
    }).join('') + '</tr></tbody></table>';
  return html;
}

/** Les trois bandes de chaque ligne : pire monde testé parmi les colonnes, central, prudent. */
function bands(data, shown) {
  const B = T.bands, worlds = Object.fromEntries(data.worlds.map((world) => [world.id, worldName({ ...world, highlight: false })]));
  const where = (cell) => (cell.world_id === null ? B.everywhere : worlds[cell.world_id].toLowerCase());
  let html = `<h3 class="bands-title">${escapeHtml(B.title)}</h3><table class="value bands"><thead><tr><th></th>`
    + ['pire', 'central', 'prudent'].map((name) => `<th>${escapeHtml(B[name])}</th>`).join('') + '</tr></thead><tbody>';
  for (const row of data.policies) {
    const band = shown.bands[row.id];
    html += `<tr data-policy="${escapeHtml(row.id)}"><th><span class="name">${escapeHtml(row.name)}</span></th>`
      + ['pire', 'central', 'prudent'].map((name) => {
        const b = band[name], from = (cell) => (name === 'pire' ? ` <small>(${escapeHtml(where(cell))})</small>` : '');
        return `<td class="cell" data-band="${name}"><strong class="kept num">${escapeHtml(P.kept(b.doors_open.value, band.doors_total))}${from(b.doors_open)}</strong>`
          + `<dl class="num"><dt>${escapeHtml(P.borrowing)}${from(b.peak_financing_chf)}</dt><dd>${escapeHtml(chf(b.peak_financing_chf.value))}</dd>`
          + `<dt>${escapeHtml(B.worth)}${from(b.net_worth_end_chf)}</dt><dd>${escapeHtml(chf(b.net_worth_end_chf.value))}</dd></dl></td>`;
      }).join('') + '</tr>';
  }
  const points = shown.bands.fige.prudent_points;
  return `${html}</tbody></table>${p(B.note(B.points(points, plain(points))), 'small')}${p(B.sheetNote, 'small')}`;
}

/** L'écart entre chaque politique et le plan figé, pour Alexia et pour Alexia fragile : mêmes règles, mêmes seuils, deux états. */
function gaps(data) {
  const cases = [[P.caseShort(chf(data.start_cash_chf)), data], [P.fragileShort(chf(data.fragile.start_cash_chf)), data.fragile]];
  let html = `<h3 class="bands-title">${escapeHtml(P.gapTitle)}</h3>${p(P.gapIntro, 'small')}<table class="value gap"><thead><tr><th></th>`
    + data.worlds.map((world) => `<th class="${world.highlight ? 'long' : ''}">${escapeHtml(worldName({ ...world, highlight: false }))}</th>`).join('')
    + '</tr></thead><tbody>';
  for (const row of data.policies.filter((r) => r.rule)) {
    cases.forEach(([label, shown], index) => {
      html += `<tr data-policy="${escapeHtml(row.id)}" data-case="${index ? 'fragile' : 'alexia'}"><th>`
        + `${index ? '' : `<span class="name">${escapeHtml(row.name)}</span>`}<span class="how">${escapeHtml(label)}</span></th>`
        + data.worlds.map((world) => {
          const g = shown.gap[row.id][world.id];
          return `<td class="cell${world.highlight ? ' long' : ''}"><strong class="num">${escapeHtml(P.doorsMore(g.doors_more))}</strong>`
            + `<span class="num">${escapeHtml(P.borrowingMore(g.financing_difference_chf, chf(g.financing_difference_chf)))}</span>`
            + `${g.target_saved ? `<span class="tag">${escapeHtml(P.saved(data.target.name))}</span>` : ''}</td>`;
        }).join('') + '</tr>';
    });
  }
  return `${html}</tbody></table>`;
}

/** Sous « Détails » : comment chaque seuil est choisi, et ce que donnent les tests contre le surapprentissage. */
function proof(data) {
  const named = Object.fromEntries(data.policies.map((row) => [row.id, row.name]));
  const worlds = Object.fromEntries(data.worlds.map((world) => [world.id, worldName(world)]));
  let html = `<h3>${escapeHtml(P.choiceTitle)}</h3>${p(P.choice)}`;
  for (const row of data.policies.filter((r) => r.calibration)) {
    const zone = row.calibration.zone;
    html += p(zone ? (zone.high_chf === null ? P.zoneOpen(row.name, chf(row.rule.threshold_chf), chf(zone.low_chf))
      : P.zone(row.name, chf(row.rule.threshold_chf), chf(zone.low_chf), chf(zone.high_chf))) : P.noZone(row.name), 'num');
  }
  html += `<h3>${escapeHtml(P.leftOutTitle)}</h3>${p(P.leftOut)}<table class="worlds num"><thead><tr><th></th>`
    + data.worlds.map((world) => `<th>${escapeHtml(worlds[world.id])}</th>`).join('') + '</tr></thead><tbody>';
  for (const row of data.policies.filter((r) => r.leave_one_out)) {
    html += `<tr><th>${escapeHtml(row.name)}</th>` + row.leave_one_out.map((test) =>
      `<td>${escapeHtml(P.leftOutCell(test.threshold_chf === null ? P.none : chf(test.threshold_chf), test.target_holds))}</td>`).join('') + '</tr>';
  }
  html += `</tbody></table><h3>${escapeHtml(P.variantsTitle)}</h3>${p(P.variants)}${p(P.blind)}`
    + '<table class="worlds num"><thead><tr><th></th>' + data.policies.map((row) => `<th>${escapeHtml(row.name)}</th>`).join('') + '</tr></thead><tbody>';
  for (const variant of data.validation.variants) {
    html += `<tr><th>${escapeHtml(worldName({ ...variant.world, highlight: false }))}</th>` + data.policies.map((row) => {
      const c = variant.cells[row.id];
      return `<td>${escapeHtml(P.variantCell(c.doors_open, c.doors_total, c.target_holds))}</td>`;
    }).join('') + '</tr>';
  }
  const drawn = data.validation.random;
  html += `</tbody></table><h3>${escapeHtml(P.drawnTitle)}</h3>${p(P.drawn(drawn.draws, drawn.seed, drawn.ages[0], drawn.ages[1], drawn.gravity[0], drawn.gravity[1]))}`;
  for (const row of data.policies.filter((r) => r.rule)) {
    html += p(P.drawnKept(named[row.id], data.target.name, drawn.kept[row.id], drawn.draws, drawn.applied[row.id]), 'num');
  }
  return html + p(P.drawnSeer(drawn.clairvoyant_kept, drawn.draws), 'num');
}

/**
 * @param host  le <dialog> de la feuille
 * @param data  la réponse de /policies
 */
export function renderPolicies(host, data, { onClose, onCase, onFolk, which = 'alexia' }) {
  const shown = which === 'fragile' ? data.fragile : data;
  const pick = (id, label) => `<button type="button" class="pill" data-case="${id}" aria-pressed="${id === which}">${escapeHtml(label)}</button>`;
  host.innerHTML = `<div class="sheet-top"><h2>${escapeHtml(P.title)}</h2>`
    + `<button type="button" class="pill close" id="policies-close">${escapeHtml(P.close)}</button></div>`
    + p(P.intro) + p(P.target(data.target.name, chf(data.target.required_chf), data.target.age), 'num')
    + `<p class="limit">${escapeHtml(P.limit)}</p>`
    + `<div class="cases" role="group" aria-label="${escapeHtml(P.cases)}">${pick('alexia', P.caseOf(chf(data.start_cash_chf)))}`
    + `${pick('fragile', P.fragileCase(chf(data.fragile.start_cash_chf)))}<span class="how">${escapeHtml(P.sameRules)}</span></div>`
    + table(data, shown)
    + p(P.regretIs, 'small') + p(P.seerIs, 'small')
    + gaps(data)
    + bands(data, shown)
    + `<button type="button" class="pill" id="folk-open">${escapeHtml(T.folk.button)}</button>`
    + `<details class="fold"><summary>${escapeHtml(T.card.details)}</summary>${proof(data)}${p(T.card.origin, 'origin')}</details>`;
  host.querySelector('#folk-open').addEventListener('click', onFolk);
  host.querySelector('#policies-close').addEventListener('click', onClose);
  host.querySelectorAll('.cases [data-case]').forEach((button) => button.addEventListener('click', () => onCase(button.dataset.case)));
}

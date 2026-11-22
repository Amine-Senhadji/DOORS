// La feuille « Une règle répandue, à l'épreuve » : le moteur teste « trois mois d'épargne de précaution suffisent »
// dans deux états d'Alexia, au même âge. Chaque chiffre, et la phrase, viennent de la route /folk-rule.
import { T } from './i18n.js';
import { ageAtMonth, chf, plain } from './format.js';

const escapeHtml = (text) => String(text).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const p = (text, className = '') => `<p${className ? ` class="${className}"` : ''}>${escapeHtml(text)}</p>`;
const F = T.folk;

/**
 * @param host  le <dialog> de la feuille
 * @param data  la réponse de /folk-rule
 */
export function renderFolk(host, data, { onClose, startAge }) {
  const name = (world) => (world.adjustable ? F.world(world.name, world.age) : F.noShock);
  let table = '<table class="value folk"><thead><tr><th></th>'
    + data.worlds.map((world) => `<th>${escapeHtml(name(world))}</th>`).join('') + '</tr></thead><tbody>';
  for (const state of data.states) {
    table += `<tr data-state="${escapeHtml(state.id)}"><th><span class="name">${escapeHtml(state.label)}</span>`
      + `<span class="rule num">${escapeHtml(F.cushion(chf(state.expenses_chf), data.rule.months, chf(state.cushion_chf)))}</span>`
      + `<span class="rule num"><strong>${escapeHtml(F.kept(state.kept, state.total))}</strong></span>`
      + `<span class="how num">${escapeHtml(state.needed_chf === null ? F.never
        : F.needed(chf(state.needed_chf), plain(state.needed_months), state.needed_chf <= state.cushion_chf))}</span></th>`
      + data.worlds.map((world) => {
        const row = state.by_world[world.id];
        return `<td class="cell ${row.holds ? 'holds' : 'breaks'}"><strong>${escapeHtml(row.holds ? F.holds : F.breaks)}</strong>`
          + (row.holds ? '' : `<span class="num">${escapeHtml(F.red(ageAtMonth(row.first_red_month, startAge), chf(row.peak_financing_chf)))}</span>`)
          + '</td>';
      }).join('') + '</tr>';
  }
  host.innerHTML = `<div class="sheet-top"><h2>${escapeHtml(F.title)}</h2>`
    + `<button type="button" class="pill close" id="folk-close">${escapeHtml(T.policies.close)}</button></div>`
    + `<p class="slide num">${escapeHtml(data.sentence)}</p>`
    + p(F.how(data.rule.age, data.rule.months, data.rule.window_months))
    + `${table}</tbody></table>` + p(F.why) + p(F.limit, 'small') + p(T.card.origin, 'origin');
  host.querySelector('#folk-close').addEventListener('click', onClose);
}

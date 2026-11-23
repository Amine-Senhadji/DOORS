// The sheet of "Ask in your own words": what was understood of one sentence, as settings that Alexia keeps, changes
// or unticks before anything is computed. Nothing goes to the engine until she presses "Compute".
// Every text here comes from the server (the engine's descriptions, the conversions and the reasons written by code)
// or from the text files. Nothing is computed in the browser.
import { T } from './i18n.js';
import { ageAtMonth, plain, worldDetails } from './format.js';

const escapeHtml = (text) => String(text).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const p = (text, className = '') => (text ? `<p${className ? ` class="${className}"` : ''}>${escapeHtml(text)}</p>` : '');
const A = T.ask;
const isShare = (unit) => unit.startsWith('%');

/** What was not in her sentence, and so was inferred by the model: said next to the setting, so that she checks it.
 *  `name`: which crisis it is about, when a world holds two. */
function inferred(fields, name = null) {
  if (!fields?.length) return '';
  const named = fields.map((field) => A.fields[field] ?? field);
  return p(name ? A.inferredFor(name, named) : A.inferred(named), 'check');
}

function routePart(route, view) {
  const when = (month) => ageAtMonth(month, view.startAge);
  const legs = route.legs.map((leg) => `${leg.name} (${T.trip.when(when(leg.from_month), when(leg.to_month))})`).join(' → ');
  return `<fieldset class="part" data-part="route"><label class="tick"><input type="checkbox" name="route"${route.unchanged ? '' : ' checked'}>`
    + `<strong>${escapeHtml(A.route)}</strong></label>${p(legs, 'what num')}`
    + (route.notes.length ? `<ul class="notes">${route.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join('')}</ul>` : '')
    + inferred(route.inferred) + (route.unchanged ? p(A.sameRoute, 'small') : '') + '</fieldset>';
}

function worldPart(world, view) {
  let html = `<fieldset class="part" data-part="world"><label class="tick"><input type="checkbox" name="world" checked>`
    + `<strong>${escapeHtml(A.crisis(world.crises.length))}</strong></label>${p(world.name, 'what')}`;
  for (const crisis of world.crises) {
    html += p(crisis.conversion, 'conversion num')
      + (crisis.defaults.length ? p(A.usual(crisis.name, crisis.defaults.map((field) => A.fields[field] ?? field)), 'small') : '')
      + inferred(crisis.inferred, world.crises.length > 1 ? crisis.name : null);
  }
  // What the engine builds for this world: its own description, parameter by parameter.
  return `${html}${p([world.description, ...worldDetails(world.parameters, view.horizon, view.startAge)].join(' '), 'small num')}</fieldset>`;
}

function assumptionPart(item) {
  const bounds = isShare(item.unit) ? ' min="0" max="100"' : ' min="0"';
  let html = `<fieldset class="part" data-part="assumption" data-key="${escapeHtml(item.key)}"><label class="tick">`
    + `<input type="checkbox" name="assumption" value="${escapeHtml(item.key)}"${item.unchanged ? '' : ' checked'}><strong>${escapeHtml(item.label)}</strong></label>`
    + `<label class="field"><input type="number" step="any"${bounds} class="num" data-key="${escapeHtml(item.key)}" value="${item.shown}" required>`
    + `<em>${escapeHtml(item.unit)}</em></label>`
    + p(item.unchanged ? A.sameValue : A.before(plain(item.before_shown), item.unit), 'small num') + p(item.conversion, 'conversion num');
  if (item.readings) {
    // A rate said with no unit: two readings. The first one is ticked; she picks.
    html += p(`${A.toCheck} ${item.reading}`, 'check num') + '<div class="readings">' + item.readings.map((reading, index) => `<label>`
      + `<input type="radio" name="reading-${escapeHtml(item.key)}" value="${reading.shown}"${index ? '' : ' checked'}>${escapeHtml(reading.written)}</label>`).join('') + '</div>';
  }
  return `${html}${inferred(item.inferred)}</fieldset>`;
}

function savingsPart(savings) {
  return `<fieldset class="part" data-part="savings"><label class="tick"><input type="checkbox" name="savings" checked>`
    + `<strong>${escapeHtml(A.savings(savings.age))}</strong></label>`
    + `<label class="field"><input type="number" step="any" class="num" id="ask-savings" value="${savings.value_chf}" required><em>CHF</em></label>`
    + `${inferred(savings.inferred)}</fieldset>`;
}

const reasons = (title, entries) => (entries.length ? `<h3>${escapeHtml(title)}</h3><ul class="reasons">`
  + entries.map((entry) => `<li>${entry.quote ? `<q>${escapeHtml(entry.quote)}</q> ` : ''}${escapeHtml(entry.reason)}</li>`).join('') + '</ul>' : '');

/** The sentences that have a recorded answer for what is on screen, as buttons. */
const picks = (sentences) => (sentences.length ? `${p(A.pick)}<div class="picks">`
  + sentences.map((sentence) => `<button type="button" class="pill pick" data-sentence="${escapeHtml(sentence)}">${escapeHtml(sentence)}</button>`).join('') + '</div>' : '');

/** The state with no answer to show: said plainly, with the reason, the mode, and how to get answers. */
function noAnswer(view) {
  return `<div class="none"><h3>${escapeHtml(T.ai.noAnswer)}</h3>${p(view.answer?.reason, 'reason')}${p(T.ai.played)}${p(view.why, 'small')}${p(T.ai.howTo, 'small')}</div>`
    + picks(view.sentences) + (view.sentences.length || !view.elsewhere ? '' : p(A.otherRoute, 'small'));
}

function answered(view) {
  const result = view.answer.result;
  const lists = reasons(A.notUnderstood, result.not_understood) + reasons(A.refused, result.refused);
  if (!result.understood) return `<h3>${escapeHtml(A.nothing)}</h3>${lists}`;
  return `<h3>${escapeHtml(A.understood)}</h3>${p(A.intro, 'small')}<form id="ask-apply">`
    + (result.route ? routePart(result.route, view) : '') + (result.world ? worldPart(result.world, view) : '')
    + result.assumptions.map(assumptionPart).join('') + (result.savings ? savingsPart(result.savings) : '')
    + `${lists}<p class="small" id="ask-none-ticked" hidden>${escapeHtml(A.noneTicked)}</p>`
    + `<div class="buttons"><button type="submit" class="pill" id="ask-compute">${escapeHtml(A.compute)}</button>`
    + `<button type="button" class="pill" id="ask-cancel">${escapeHtml(A.cancel)}</button></div></form>`;
}

/** What she ticked, with the values as she left them: the settings to hand to the engine. */
function settingsOf(host, result) {
  const ticked = (name) => Boolean(host.querySelector(`input[name="${name}"]`)?.checked);
  const settings = { path: null, world: null, assumptions: null, observation: null };
  if (result.route && ticked('route')) settings.path = result.route.path;
  if (result.world && ticked('world')) settings.world = result.world.id;
  const changed = {};
  host.querySelectorAll('.part[data-part="assumption"]').forEach((part) => {
    const item = result.assumptions.find((each) => each.key === part.dataset.key);
    const typed = Number(part.querySelector('input[type="number"]').value);
    if (!part.querySelector('input[type="checkbox"]').checked || !Number.isFinite(typed)) return;
    // A value she did not touch is the one the server stored. One she typed, or the reading she picked, is written as
    // the drawer writes it: a share is given in percent. Formatting, not a financial calculation.
    changed[item.key] = typed === item.shown ? item.value : (isShare(item.unit) ? typed / 100 : typed);
  });
  if (Object.keys(changed).length) settings.assumptions = changed;
  if (result.savings && ticked('savings')) {
    settings.observation = { gare_month: result.savings.gare_month, value_chf: Number(host.querySelector('#ask-savings').value) };
  }
  return settings;
}

/**
 * Draws the sheet.
 * @param host  the <dialog>
 * @param view  { state: 'wait' | 'list' | 'none' | 'answer', sentence, sentences, elsewhere, answer, why, startAge, horizon }
 *              `sentences`: the recorded sentences for the route on screen; `elsewhere`: some are recorded for another route
 * @param on    { onClose, onPick(sentence), onCompute(settings) }
 */
export function renderAsk(host, view, on) {
  const answer = view.answer;
  const body = { wait: p(A.waiting, 'wait'), list: view.sentences.length ? picks(view.sentences) : noAnswer(view), none: noAnswer(view) }[view.state]
    ?? answered(view);
  host.innerHTML = `<div class="sheet-top"><h2>${escapeHtml(A.title)}</h2>`
    + `<button type="button" class="pill close" id="ask-close">${escapeHtml(T.ai.close)}</button></div>`
    + (view.sentence ? p(T.quoted(view.sentence), 'said') : '')
    + (answer?.label ? `<p class="source">${escapeHtml(answer.label)}</p>` : '') + p(answer?.notice, 'notice')
    + (view.state === 'answer' ? p(T.ai.engine, 'small') : '') + body;
  host.querySelector('#ask-close').addEventListener('click', on.onClose);
  host.querySelectorAll('.pick').forEach((button) => button.addEventListener('click', () => on.onPick(button.dataset.sentence)));
  const form = host.querySelector('#ask-apply');
  if (!form) return;
  host.querySelector('#ask-cancel').addEventListener('click', on.onClose);
  const refresh = () => {
    const none = !form.querySelector('input[type="checkbox"]:checked');
    host.querySelector('#ask-compute').disabled = none;
    host.querySelector('#ask-none-ticked').hidden = !none;
  };
  form.querySelectorAll('input[type="checkbox"]').forEach((box) => box.addEventListener('change', refresh));
  // A value she types is a setting she wants: its box is ticked. A reading she picks goes into the field.
  form.querySelectorAll('.part input[type="number"]').forEach((field) => field.addEventListener('input', () => {
    field.closest('.part').querySelector('input[type="checkbox"]').checked = true;
    refresh();
  }));
  form.querySelectorAll('.readings input').forEach((radio) => radio.addEventListener('change', () => {
    radio.closest('.part').querySelector('input[type="number"]').value = radio.value;
  }));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    on.onCompute(settingsOf(host, answer.result));
  });
  refresh();
}

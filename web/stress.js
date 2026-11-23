// The sheet of "Find what breaks my plan": the worlds the model proposed, simulated and ranked by the engine; for each
// world kept, the model's explanation with its verified figures, or the engine's figures alone when the checker refused
// it; the engine's own signposts; and the engine's check of the search itself.
// With no answer of the model to show, the sheet says so and shows what the engine finds on its own.
// Every figure and every sentence about a world comes from the server. Nothing is computed in the browser.
import { T } from './i18n.js';
import { plain } from './format.js';

const escapeHtml = (text) => String(text).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const p = (text, className = '') => (text ? `<p${className ? ` class="${className}"` : ''}>${escapeHtml(text)}</p>` : '');
const S = T.stress;

const show = (world) => `<button type="button" class="link show" data-show="${escapeHtml(world.world)}">${escapeHtml(S.show)}</button>`;

/** Worlds found by the engine, one per line: the name, what the route loses, and a way to see it on the map. */
const worldsList = (worlds) => `<ul class="worlds-list">` + worlds.map((world) => `<li data-world="${escapeHtml(world.world)}">`
  + `<span><strong>${escapeHtml(world.name)}</strong><span class="what num">${escapeHtml(S.lost(world.goals_lost_names))}</span></span>${show(world)}</li>`).join('') + '</ul>';

/** The explanation of one world: the model's text and its verified figures, or the rejection and nothing of the text. */
function explanation(given) {
  if (!given.accepted) return `<div class="explanation rejected"><p class="badge">${escapeHtml(given.label)}</p>${p(S.rejected, 'small')}</div>`;
  const figures = given.figures.length ? `<details class="figures"><summary class="badge num">${escapeHtml(given.label)}</summary>`
    + `${p(S.figures, 'small')}<ul class="num">${given.figures.map((figure) => `<li><strong>${escapeHtml(figure.text)}</strong> `
      + `${escapeHtml(figure.origins.join(' · '))}</li>`).join('')}</ul>${p(S.attempts(given.attempts), 'small num')}</details>`
    : `<p class="badge">${escapeHtml(given.label)}</p>`;
  return `<div class="explanation"><p class="by">${escapeHtml(S.explanation)}</p><p class="text num">${escapeHtml(given.text)}</p>${figures}</div>`;
}

function ranked(world) {
  const headline = world.facts.filter((fact) => fact.headline);
  return `<article class="world" data-world="${escapeHtml(world.world)}"><div class="world-top"><h3>${escapeHtml(world.name)}</h3>${show(world)}</div>`
    + p(S.lost(world.goals_lost_names), 'lost num')
    + `<dl class="num">${headline.map((fact) => `<dt>${escapeHtml(fact.origin)}</dt><dd>${escapeHtml(fact.written)}</dd>`).join('')}</dl>`
    + explanation(world.explanation)
    + `<p class="by">${escapeHtml(S.signpost)}</p>`
    + (world.signposts.length ? world.signposts.map((signpost) => p(signpost.text, 'signpost num')).join('') : p(S.noSignpost, 'small'))
    + '</article>';
}

/** For a route of the benchmark: what the full scan made offline found, with the mildest of its hardest worlds. */
const scanned = (scan) => (scan ? p(S.scan(plain(scan.worlds), scan.max_goals_lost, scan.hardest_count), 'num') + worldsList(scan.hardest) : '');

/** The engine's check of the search: every single crisis simulated, and the full scan when there is one. The engine
 *  lists its hardest single crises mildest first: when the search found as hard, the first one is the milder world. */
function checked(result, scan) {
  const single = result.verification.single_crises, found = result.verification.benchmark?.found;
  const kind = single.harder_than_found ? 'harder' : single.as_hard_and_milder ? 'milder' : 'none';
  const listed = { harder: single.hardest, milder: single.hardest.slice(0, 1), none: [] }[kind];
  return `<section class="checked"><h3>${escapeHtml(S.checked)}</h3>`
    + p(S.single[kind](single.scanned, single.max_goals_lost), 'num') + (listed.length ? worldsList(listed) : '')
    + scanned(scan) + (scan ? p(found ? S.scanFound : S.scanMissed, 'limit') : '') + '</section>';
}

/** The path of the search, call by call: what the model asked for, and what the engine did with it. */
function path(result) {
  const calls = result.calls.map((call) => `<li><strong>${escapeHtml(S.call(call.call))}</strong> `
    + `<span class="num">${escapeHtml(S.tested(call.tested.length))}</span>`
    + (call.asked.length ? ` <code>${escapeHtml(call.asked.join('  '))}</code>` : '')
    + (call.already_tested.length ? p(`${S.again}: ${call.already_tested.join(', ')}`, 'small') : '')
    + call.refused.map((refusal) => p(`${S.refusedWorld}: ${refusal.asked}. ${refusal.reason}`, 'small')).join('')
    + (call.not_tested.length ? p(S.notTested(result.budget.worlds_per_call, call.not_tested.join(', ')), 'small') : '') + '</li>').join('');
  return `<details class="fold"><summary>${escapeHtml(S.details)}</summary><ol class="calls">${calls}</ol>`
    + p(S.stopped[result.stopped] ?? '', 'small')
    + p(S.tokens(plain(result.usage.input_tokens ?? 0), plain(result.usage.output_tokens ?? 0)), 'small num') + '</details>';
}

function answered(answer) {
  const result = answer.result, budget = result.budget;
  return p(S.budget(budget.calls_used, budget.worlds_tested, plain(result.space.worlds)), 'num')
    + p(S.calm(result.calm.goals_kept, result.calm.goals_total), 'num')
    + (result.ranking.length ? result.ranking.map(ranked).join('') : p(S.nothing, 'limit'))
    + checked(result, answer.scan) + path(result);
}

/** No answer of the model: said plainly, then what the engine finds on its own, which is never labelled as an answer. */
function alone(view) {
  const answer = view.answer, engine = answer.engine;
  let html = `<div class="none"><h3>${escapeHtml(T.ai.noAnswer)}</h3>${p(answer.reason, 'reason')}${p(T.ai.played)}${p(view.why, 'small')}${p(T.ai.howTo, 'small')}</div>`;
  if (!engine) return html;
  const single = engine.single_crises;
  html += `<section class="checked" id="engine-alone"><h3>${escapeHtml(S.alone)}</h3>${p(S.aloneHow, 'small')}`
    + p(S.calm(engine.calm.goals_kept, engine.calm.goals_total), 'num')
    + p(S.single.alone(single.scanned, single.max_goals_lost), 'num') + (single.max_goals_lost ? worldsList(single.hardest) : '')
    + scanned(answer.scan) + '</section>';
  return html;
}

/**
 * Draws the sheet.
 * @param host  the <dialog>
 * @param view  { state: 'wait' | 'answer', answer, why }   `answer`: what /ai/stress returned
 * @param on    { onClose, onShow(worldId) }
 */
export function renderStress(host, view, on) {
  const answer = view.answer;
  const body = view.state === 'wait' ? p(S.waiting, 'wait') : answer.available ? answered(answer) : alone(view);
  host.innerHTML = `<div class="sheet-top"><h2>${escapeHtml(S.title)}</h2>`
    + `<button type="button" class="pill close" id="stress-close">${escapeHtml(T.ai.close)}</button></div>`
    + (answer?.label ? `<p class="source">${escapeHtml(answer.label)}</p>` : '') + p(answer?.notice, 'notice')
    + (view.state === 'answer' && answer.available ? p(T.ai.engine, 'small') : '') + body;
  host.querySelector('#stress-close').addEventListener('click', on.onClose);
  host.querySelectorAll('[data-show]').forEach((button) => button.addEventListener('click', () => on.onShow(button.dataset.show)));
}

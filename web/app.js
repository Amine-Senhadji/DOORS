// Démarrage et enchaînement : le profil, les mondes, le trajet en cours, la carte, les fiches.
// Aucun chiffre n'est calculé ici : tout vient de web/api.js.
import { T } from './texts.fr.js';
import { ageAtMonth, chf, worldValue } from './format.js';
import { fetchAdaptive, fetchAssumptions, fetchChecks, fetchFolkRule, fetchLimits, fetchNode, fetchPath, fetchPathways, fetchPolicies, fetchScenario, fetchWorlds,
         runStarterKit, setAssumptions, setObservation, setWorlds } from './api.js';
import { VIEW, SYMBOL, renderMap, tripName } from './map.js';
import { renderGareCard, renderPlanCard, renderStationCard, renderTripCard } from './card.js';
import { runTrain, stopTrain } from './train.js';
import { renderDrawer } from './drawer.js';
import { renderPolicies } from './policies.js';
import { renderFolk } from './folk.js';

const $ = (id) => document.getElementById(id);
const escapeHtml = (text) => String(text).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const params = new URLSearchParams(location.search);

const state = {
  scenario: null,        // le profil et la durée
  worlds: [],            // les mondes nommés
  world: 'reference',    // le monde affiché par « Info trafic »
  trip: null,            // le trajet en cours : la réponse de /path
  pathways: null,        // la réponse de /pathways pour ce trajet
  nodes: new Map(),      // gare (mois) -> la réponse de /node, pour le trajet en cours
  open: null,            // la gare ouverte, ou null
  selected: null,        // { kind: 'station', key } | { kind: 'gare', month } | { kind: 'plan' } | null
  branch: null,          // la branche choisie à la gare ouverte : ses petits feux restent affichés
  plan: null,            // la réponse de /adaptive pour ce trajet, demandée à l'ouverture du panneau
  policies: null,        // la réponse de /policies pour ce trajet, demandée à l'ouverture de la feuille
  overrides: {},         // les hypothèses modifiées dans le tiroir
  observed: null,        // l'épargne constatée à une gare : { gare_month, value_chf }, ou null
  drawer: null,          // le tiroir, une fois ouvert : { assumptions, checks, kit, limits, month, section }
  geometry: null,        // le tracé du trajet en cours, pour le métro
};

const world = () => state.worlds.find((w) => w.id === state.world) ?? state.worlds[0];
const profile = () => state.scenario.profile;
const months = () => state.scenario.horizon_months;
const when = (month) => ageAtMonth(month, profile().age);
const tripTitle = () => tripName(state.trip.legs);

function fail(error) {
  $('status').textContent = error.refused ? T.refused(error.message) : T.serverDown;
}

function renderHeader() {
  $('brand').textContent = T.brand;
  $('who').textContent = T.who(profile(), chf(profile().cash_chf));
  $('banner').textContent = T.banner;
  $('trip-title').textContent = T.trip.title;
  $('traffic-title').textContent = T.traffic.title;
  document.title = T.brand;
  const mark = (kind) => `<span class="mark" style="--c:var(--${kind})"><svg viewBox="0 0 22 22" aria-hidden="true">${SYMBOL[kind]}</svg></span>`;
  $('legend').innerHTML = ['open', 'ajar', 'closed'].map((kind) => `<span>${mark(kind)}${escapeHtml(T.legend[kind])}</span>`).join('')
    + `<span><span class="dash"></span>${escapeHtml(T.legend.tunnel)}</span>`
    + `<span><span class="diamond"><svg viewBox="0 0 22 22" aria-hidden="true">${SYMBOL.gare}</svg></span>${escapeHtml(T.legend.gare)}</span>`
    + `<span><span class="diamond last"><svg viewBox="0 0 22 22" aria-hidden="true">${SYMBOL.gare}</svg></span>${escapeHtml(T.legend.last)}</span>`;
  $('train').title = T.train.how;
  $('train').addEventListener('click', toggleTrain);
  $('plan').textContent = T.plan.button;
  $('plan').addEventListener('click', openPlan);
  $('policies').textContent = T.policies.button;
  $('policies').addEventListener('click', () => openPolicies());
  $('drawer-open').textContent = T.drawer.open;
  $('drawer-open').addEventListener('click', () => openDrawer(state.drawer?.section));
}

const ARROW = '<svg width="22" height="14" viewBox="0 0 22 14" aria-hidden="true"><path d="M1 7 H19 M14 2 L19 7 L14 12" '
  + 'fill="none" stroke="#6F81B3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

function renderChips() {
  $('chips').innerHTML = state.trip.legs.map((leg, i, all) => `<li><div class="chip">`
    + `<span class="what">${escapeHtml(leg.name)}</span>`
    + `<span class="more num">${escapeHtml([T.trip.when(when(leg.from_month), when(leg.to_month)), leg.catalog_ids?.length ? T.trip.catalog(leg.catalog_ids) : '']
      .filter(Boolean).join(' · '))}</span>`
    + `</div>${i < all.length - 1 ? ARROW : ''}</li>`).join('');
}

/** « Info trafic » : un bouton par monde nommé, et ce qui distingue le monde affiché du monde de référence. */
function renderTraffic() {
  const host = $('worlds');
  host.setAttribute('aria-label', T.traffic.group);
  host.replaceChildren(...state.worlds.map((w) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'pill';
    button.textContent = w.name;
    button.dataset.world = w.id;
    button.setAttribute('aria-pressed', String(w.id === state.world));
    button.addEventListener('click', () => setWorld(w.id));
    return button;
  }));
  const shown = world();
  const details = shown.parameters.map((p) => {
    const span = p.to_month >= months() && p.months > 1 ? T.traffic.since(when(p.from_month))
      : T.traffic.span(when(p.from_month), when(p.months > 1 ? p.to_month : p.from_month));
    if (typeof p.value === 'boolean') return T.traffic.flag(p.label, span);
    return T.traffic.parameter(p.label, `${worldValue(p.field, p.value)} ${T.traffic.reference(worldValue(p.field, p.reference))}`, span);
  });
  $('traffic-note').textContent = [shown.description, ...details].join(' ');
  // L'âge de la crise affichée : un an plus tôt, un an plus tard, entre la première et la dernière gare.
  const age = $('traffic-age');
  age.hidden = !shown.adjustable;
  if (!shown.adjustable) return;
  const step = (by, label, sign) => `<button type="button" class="step" data-age="${shown.age + by}" aria-label="${escapeHtml(label)}"`
    + `${shown.age + by < shown.min_age || shown.age + by > shown.max_age ? ' disabled' : ''}>${sign}</button>`;
  age.innerHTML = `<span>${escapeHtml(T.traffic.age)}</span>${step(-1, T.traffic.earlier, '−')}`
    + `<output id="crisis-age" title="${escapeHtml(T.traffic.range(shown.min_age, shown.max_age))}">${escapeHtml(T.traffic.years(shown.age))}</output>`
    + step(1, T.traffic.later, '+')
    + (shown.age === shown.default_age ? '' : `<button type="button" class="link" data-age="${shown.default_age}">${escapeHtml(T.traffic.origin(shown.default_age))}</button>`);
  age.querySelectorAll('[data-age]').forEach((button) => {
    button.addEventListener('click', () => setCrisisAge(shown.type, Number(button.dataset.age)));
  });
}

/** Déplace une crise à un autre âge : le moteur décrit le nouveau monde, puis recalcule tout le trajet dans les mondes testés. */
async function setCrisisAge(type, age) {
  $('status').textContent = '';
  const before = { worlds: state.worlds, world: state.world }, shown = world().type;
  const use = (worlds, id) => {
    state.worlds = worlds;
    state.world = id;
    setWorlds(worlds.map((w) => w.id));
  };
  try {
    const worlds = await fetchWorlds(state.worlds.map((w) => (w.type === type ? `${type}@${age}` : w.id)));
    use(worlds, worlds.find((w) => w.type === shown).id);
  } catch (error) {
    fail(error);
    return;
  }
  if (!(await reload())) use(before.worlds, before.world);      // le moteur a refusé : on revient aux mondes d'avant
}

/** Recalcule le trajet en cours (mondes ou hypothèses changés) et rouvre ce qui était ouvert. */
async function reload() {
  const { selected } = state;
  if (!(await showTrip(state.trip.path))) return false;
  if (selected?.kind === 'gare') await openGare(selected.month);
  else if (selected?.kind === 'plan') await openPlan();
  else if (selected?.kind === 'station') selectStation(selected.key);
  renderTiroir();
  return true;
}

/** Les branches à dessiner : celles de la gare ouverte, et aucune autre. */
function branchesToDraw() {
  if (state.open === null) return [];
  return (state.nodes.get(state.open)?.branches ?? []).filter((branch) => !branch.on_path && branch.available !== false)
    .map((branch) => ({ ...branch, from_month: state.open }));
}

function renderBoard() {
  stopTrain($('tracks'));          // la carte est redessinée : le métro repart du départ à la prochaine demande
  $('train').textContent = T.train.go;
  state.geometry = renderMap({ svg: $('tracks'), labels: $('labels'), profile: profile(), months: months(), trip: state.trip,
              pathways: state.pathways, branches: branchesToDraw(), world: world(), selected: state.selected,
              picked: state.branch, onBranch: pickBranch,
              node: state.open === null ? null : state.nodes.get(state.open),
              onStation: selectStation, onGare: openGare });
}

/** Le bouton du métro : le lancer, ou l'arrêter s'il roule. */
function toggleTrain() {
  const button = $('train');
  if (document.body.dataset.train === 'en route') {
    stopTrain($('tracks'));
    button.textContent = T.train.go;
    return;
  }
  button.textContent = T.train.stop;
  runTrain({ svg: $('tracks'), labels: $('labels'), geometry: state.geometry, onEnd: () => { button.textContent = T.train.again; } });
}

function renderSide() {
  const card = $('card'), common = { trip: state.trip, worlds: state.worlds, world: world(), profile: profile() };
  const door = state.selected?.kind === 'station' ? state.trip.doors.find((d) => d.key === state.selected.key) : null;
  const node = state.selected?.kind === 'gare' ? state.nodes.get(state.selected.month) : null;
  if (state.selected?.kind === 'plan' && state.plan) renderPlanCard(card, { ...common, plan: state.plan, onBack: clearSelection });
  else if (door) renderStationCard(card, { ...common, door, pathways: state.pathways, onGare: openGare, onBack: clearSelection });
  else if (node) renderGareCard(card, { ...common, node, pathways: state.pathways, onTake: (branch) => takeBranch(branch, node.gare_month),
                                        onBack: clearSelection, onObserve: observeAt });
  else renderTripCard(card, { ...common, title: tripTitle(), endAge: profile().age + Math.round(months() / 12), onObserve: observeAt });
  card.scrollTop = 0;
  document.body.dataset.selected = state.selected ? `${state.selected.kind}:${state.selected.key ?? state.selected.month ?? ''}` : 'trajet';
  // Dans la fiche d'une gare : survoler une branche montre ses petits feux sur la carte, la cliquer la choisit.
  card.querySelectorAll('.branch[data-branch]').forEach((box) => {
    const group = () => $('tracks').querySelector(`g.branch[data-branch="${box.dataset.branch}"]`);
    box.classList.toggle('picked', box.dataset.branch === state.branch);
    box.addEventListener('mouseenter', () => group()?.classList.add('hover'));
    box.addEventListener('mouseleave', () => group()?.classList.remove('hover'));
    box.addEventListener('click', (event) => { if (!event.target.closest('button')) pickBranch(box.dataset.branch); });
  });
}

/** Prend une branche à une gare. L'épargne constatée reste valable si la branche part de sa gare ou d'une gare suivante :
 *  le passé est le même. Avant, le nouveau trajet n'y passe plus : elle est oubliée. */
function takeBranch(branch, month) {
  if (state.observed && month < state.observed.gare_month) remember(null);
  return showTrip(branch.path);
}

function remember(observed) {
  state.observed = observed;
  setObservation(observed);
  document.body.dataset.observed = observed ? `${observed.gare_month}:${observed.value_chf}` : '';
}

/** Le jumeau qui apprend : l'épargne constatée à une gare (ou son oubli, avec null). Tout le trajet est recalculé par le moteur. */
async function observeAt(month, value) {
  const before = state.observed, gare = month ?? (state.selected?.kind === 'gare' ? state.selected.month : null);
  remember(month === null ? null : { gare_month: month, value_chf: value });
  if (!(await showTrip(state.trip.path))) {
    remember(before);                    // le moteur a refusé la valeur : on revient à l'état d'avant
    return;
  }
  if (gare !== null) await openGare(gare);
  renderTiroir();
}

/** Choisit une branche de la gare ouverte (ou l'abandonne si elle l'était déjà). */
function pickBranch(id) {
  state.branch = state.branch === id ? null : id;
  renderBoard();
  renderSide();
}

/** Ouvre le panneau « Plan figé ou politique » : la gare de la règle s'ouvre, sa branche est choisie si la règle s'applique. */
async function openPlan() {
  $('status').textContent = '';
  try {
    if (!state.plan) state.plan = await fetchAdaptive(state.trip.path);
    const gare = state.plan.rule.gare_month;
    if (!state.nodes.has(gare)) state.nodes.set(gare, await fetchNode(state.trip.path, gare));
    state.open = gare;
    state.selected = { kind: 'plan' };
    render();
  } catch (error) {
    $('status').textContent = error.refused ? T.plan.none(error.message) : T.serverDown;
  }
}

/** Ouvre la feuille « Des politiques, pas des plans » : le tableau de valeur du trajet en cours. */
async function openPolicies(which = 'alexia') {
  $('status').textContent = '';
  const sheet = $('policies-sheet');
  try {
    if (!state.policies) state.policies = await fetchPolicies(state.trip.path);
    const close = () => { sheet.close(); delete document.body.dataset.policies; };
    const keep = sheet.open ? sheet.scrollTop : 0;
    // Alexia ou Alexia fragile : le même tableau, les mêmes règles, deux épargnes de départ.
    renderPolicies(sheet, state.policies, { onClose: close, onCase: openPolicies, onFolk: () => { close(); openFolk(); }, which });
    if (!sheet.open) sheet.showModal();
    sheet.addEventListener('close', () => delete document.body.dataset.policies, { once: true });
    sheet.scrollTop = keep;
    document.body.dataset.policies = which === 'fragile' ? 'fragile' : 'ouvert';
  } catch (error) {
    $('status').textContent = error.refused ? T.policies.refused(error.message) : T.serverDown;
  }
}

/** Ouvre la feuille « Une règle répandue, à l'épreuve » : trois mois d'épargne, dans deux états d'Alexia. */
async function openFolk() {
  $('status').textContent = '';
  const sheet = $('folk-sheet');
  try {
    const data = await fetchFolkRule(state.trip.path);
    renderFolk(sheet, data, { onClose: () => sheet.close(), startAge: profile().age });
    if (!sheet.open) sheet.showModal();
    sheet.addEventListener('close', () => delete document.body.dataset.folk, { once: true });
    document.body.dataset.folk = 'ouvert';
  } catch (error) {
    $('status').textContent = error.refused ? T.folk.refused(error.message) : T.serverDown;
  }
}

function render() {
  // Avec le panneau des plans ouvert, la branche de la règle est choisie dans les mondes où la règle s'applique.
  if (state.selected?.kind === 'plan' && state.plan) {
    state.branch = state.plan.by_world[state.world]?.adaptive.applies ? state.plan.rule.branch_id : null;
  }
  renderChips();
  renderTraffic();
  renderBoard();
  renderSide();
  fitStage();
  document.body.dataset.world = state.world;
  document.body.dataset.trip = tripTitle();
}

function selectStation(key) {
  state.selected = { kind: 'station', key };
  render();
}

function clearSelection() {
  state.selected = null;
  state.open = null;
  state.branch = null;
  render();
}

/** Ouvre une gare : ses branches sont calculées à la demande, puis gardées. */
async function openGare(month) {
  $('status').textContent = '';
  try {
    if (!state.nodes.has(month)) state.nodes.set(month, await fetchNode(state.trip.path, month));
    if (state.open !== month) state.branch = null;
    state.open = month;
    state.selected = { kind: 'gare', month };
    render();
  } catch (error) {
    fail(error);
  }
}

async function setWorld(id) {
  state.world = id;          // les stations de tous les mondes sont déjà là : la carte change tout de suite
  render();
  try {
    // Le registre mois par mois, lui, est celui d'un seul monde : on le redemande pour le monde affiché.
    const trip = await fetchPath(state.trip.path, id);
    if (state.world === id) {
      state.trip = trip;
      renderTiroir();
    }
  } catch (error) {
    fail(error);
  }
}

// ------------------------------------------------------------------ le tiroir
function renderTiroir() {
  const host = $('drawer');
  if (host.hidden || !state.drawer) return;
  const keep = host.scrollTop;
  renderDrawer(host, { ...state.drawer, overrides: state.overrides, trip: state.trip, world: world(), startAge: profile().age }, {
    onClose: () => { host.hidden = true; delete document.body.dataset.drawer; },
    onSection: (name) => { state.drawer.section = name; document.body.dataset.drawer = name; },
    onChange: (key, value) => changeAssumption(key, value),
    onReset: (key) => changeAssumption(key, null),
    onRunKit: async () => {
      try {
        state.drawer.kit = await runStarterKit();
        renderTiroir();
      } catch (error) {
        fail(error);
      }
    },
    onMonth: (month) => { state.drawer.month = month; renderTiroir(); },
  });
  host.scrollTop = keep;
}

/** Ouvre le tiroir. Ses données sont demandées à la première ouverture. */
async function openDrawer(section = 'hypotheses') {
  $('status').textContent = '';
  try {
    if (!state.drawer) {
      const [assumptions, checks, limits] = await Promise.all([fetchAssumptions(), fetchChecks(), fetchLimits()]);
      // Le mois montré d'abord : celui de l'adresse (?mois=27), sinon le premier mois de financement, sinon le premier mois.
      const asked = Number(params.get('mois')), last = state.trip.months.length - 1;
      const first = state.trip.by_world[state.world].first_negative_month;
      const month = params.has('mois') && Number.isInteger(asked) ? Math.min(Math.max(asked, 0), last) : first ?? 0;
      state.drawer = { assumptions, checks, limits, kit: null, month, section };
    }
    state.drawer.section = section;
    $('drawer').hidden = false;
    document.body.dataset.drawer = section;
    renderTiroir();
  } catch (error) {
    fail(error);
  }
}

/** Une hypothèse modifiée (ou remise à l'origine, avec null ; '*' pour toutes) : tout le trajet est recalculé par le moteur. */
async function changeAssumption(key, value) {
  const before = { ...state.overrides };
  if (key === '*') state.overrides = {};
  else if (value === null) delete state.overrides[key];
  else state.overrides[key] = value;
  const original = state.drawer.assumptions.find((a) => a.key === key);
  if (original && state.overrides[key] === original.value) delete state.overrides[key];
  setAssumptions(state.overrides);
  if (!(await showTrip(state.trip.path))) {
    state.overrides = before;            // le moteur a refusé la valeur : on revient à l'état d'avant
    setAssumptions(before);
  }
  state.drawer.month = Math.min(state.drawer.month, state.trip.months.length - 1);
  document.body.dataset.overrides = String(Object.keys(state.overrides).length);
  renderTiroir();
}

/** Change de trajet : ses tronçons et ses stations, ses chemins d'adaptation, et la gare de départ. */
async function showTrip(path) {
  $('status').textContent = '';
  try {
    const [trip, pathways, departure] = await Promise.all([fetchPath(path, state.world), fetchPathways(path), fetchNode(path, 0)]);
    Object.assign(state, { trip, pathways, nodes: new Map([[0, departure]]), open: null, selected: null, branch: null, plan: null, policies: null });
    render();
    return true;
  } catch (error) {
    fail(error);
    return false;
  }
}

/** La carte est dessinée sur une planche de taille fixe, mise à l'échelle de la place disponible. */
function fitStage() {
  const map = $('map');
  $('stage').style.setProperty('--k', String(map.clientWidth / VIEW.width));
  // La fiche est au moins aussi haute que la carte, et descend jusqu'au bas de l'écran s'il y a la place.
  const room = window.innerHeight - map.getBoundingClientRect().top - window.scrollY - $('legend').offsetHeight - 22;
  $('card').style.maxHeight = `${Math.max(map.clientHeight, room)}px`;
}

async function boot() {
  $('status').textContent = T.loading;
  new ResizeObserver(fitStage).observe($('map'));
  fitStage();
  let lines;
  try {
    [state.scenario, state.worlds, lines] = await Promise.all([fetchScenario(), fetchWorlds(), fetchNode([], 0)]);
  } catch (error) {
    fail(error);
    document.body.dataset.ready = 'error';
    return;
  }
  renderHeader();
  // Pour ouvrir directement un trajet, un monde, une gare ou une station :
  // ?trajet=master&monde=chomage_6_mois&gare=12   ou   ?trajet=berlin&station=logement
  // ?monde=krach@25 : le krach déplacé à 25 ans. Le moteur décrit le monde déplacé ; s'il refuse l'âge, la crise garde le sien.
  const [askedWorld, askedAge] = (params.get('monde') ?? '').split('@');
  if (askedAge && state.worlds.some((w) => w.type === askedWorld && w.adjustable)) {
    try {
      state.worlds = await fetchWorlds(state.worlds.map((w) => (w.type === askedWorld ? `${askedWorld}@${askedAge}` : w.id)));
      setWorlds(state.worlds.map((w) => w.id));
    } catch (error) {
      fail(error);
    }
  }
  const shownFirst = state.worlds.find((w) => w.type === askedWorld);
  if (shownFirst) state.world = shownFirst.id;
  // ?hyp=taxe_semestre:580,loyer:1000 : des hypothèses modifiées dès l'ouverture, comme si on les avait saisies dans le tiroir.
  for (const pair of (params.get('hyp') ?? '').split(',').filter(Boolean)) {
    const [key, value] = pair.split(':');
    if (key && Number.isFinite(Number(value))) state.overrides[key] = Number(value);
  }
  setAssumptions(state.overrides);
  document.body.dataset.overrides = String(Object.keys(state.overrides).length);
  // ?gare=72&epargne=40000 : l'épargne constatée à cette gare, comme si on l'avait saisie dans sa fiche.
  const saved = Number(params.get('epargne'));
  if (params.has('epargne') && params.has('gare') && !params.has('branche') && Number.isFinite(saved)) {
    remember({ gare_month: Number(params.get('gare')), value_chf: saved });
  }
  // Sans demande particulière, la page s'ouvre sur le trajet par défaut du scénario : l'histoire de la démo.
  const asked = lines.branches.find((b) => b.id === params.get('trajet'));
  const first = asked?.path ?? (state.scenario.default_path?.length ? state.scenario.default_path : lines.branches[0].path);
  let shown = await showTrip(first);
  if (!shown && state.observed) {        // l'épargne de l'adresse a été refusée : le trajet s'ouvre sans elle
    remember(null);
    shown = await showTrip(first);
  }
  if (!shown) {
    document.body.dataset.ready = 'error';
    return;
  }
  // ?trajet=emploi&gare=60&branche=master : le trajet qui quitte la ligne de départ par cette branche, à cette gare.
  let taken = false;
  if (params.has('gare') && params.has('branche')) {
    try {
      const node = await fetchNode(state.trip.path, Number(params.get('gare')));
      const branch = node.branches.find((b) => b.id === params.get('branche') && b.available);
      taken = Boolean(branch) && await showTrip(branch.path);
    } catch (error) {
      fail(error);
    }
  }
  if (params.has('gare') && !taken) await openGare(Number(params.get('gare')));
  if (params.has('plan')) await openPlan();                 // ?plan=1 : le panneau « Plan figé ou politique »
  if (params.has('politiques')) await openPolicies(params.get('politiques') === 'fragile' ? 'fragile' : 'alexia');   // ?politiques=1, ou ?politiques=fragile
  if (params.has('regle')) await openFolk();                // ?regle=1 : la règle répandue, à l'épreuve
  if (params.has('tiroir')) await openDrawer(params.get('tiroir') || 'hypotheses');      // ?tiroir=registre
  if (state.trip.doors.some((d) => d.key === params.get('station'))) selectStation(params.get('station'));
  await document.fonts?.ready;
  document.body.dataset.ready = '1';
  if (params.has('metro')) toggleTrain();
}

boot();

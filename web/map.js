// La carte du réseau : l'arbre des trajets. Une voie par type de vie, le trajet en cours, les branches
// qui le quittent aux gares de correspondance, et les stations.
// Géométrie d'affichage seulement : aucun montant n'est calculé ici.
import { T } from './texts.fr.js';
import { ageAtMonth, chf, durationOf, ranges } from './format.js';

export const VIEW = { width: 980, height: 520 };
const X0 = 132, YEAR = 68;                         // 20 ans à x = 132 ; un an = 68
const HEADS = 104;                                 // la rangée des noms de stations, sous l'en-tête de la carte
const LANE_Y = { study: 178, work: 252, abroad: 326, project: 400 };
// La voie de chaque bloc du contrat : un choix d'affichage.
const LANE_OF = { master: 'study', master_part_time: 'study', phd: 'study', internship: 'study',
                  job: 'work', job_abroad: 'abroad', independent: 'project', startup: 'project', pause: 'project' };
const SIDE = [0, 32, -32, 16, -16];                // deux lignes sur la même voie : la seconde passe à côté, hors des feux
const SLOPE = 0.5;                                 // un aiguillage avance de la moitié de ce qu'il descend
export const SYMBOL = {
  open: '<path d="M5 11.5 L9.5 16 L17 7"/>',
  ajar: '<path d="M5 11 H17"/>',
  closed: '<path d="M6 6 L16 16 M16 6 L6 16"/>',
  unknown: '<path d="M5 11 h.01 M11 11 h.01 M17 11 h.01"/>',
  gare: '<path d="M11 3 L19 11 L11 19 L3 11 Z"/>',
};
export const symbol = (light) => `<svg viewBox="0 0 22 22" aria-hidden="true">${SYMBOL[light]}</svg>`;

const xOf = (month) => X0 + (month * YEAR) / 12;
const fmt = (p) => `${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
const escapeHtml = (text) => String(text).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/** L'état d'une porte dans une réponse de l'API : une chaîne, ou un objet { state }. */
export const stateOf = (door) => (typeof door === 'string' ? door : door?.state);

/**
 * La couleur d'une station dans le monde affiché : ouverte (open), fermée (closed),
 * ou ouverte ici mais fermée dans un autre monde testé (ajar).
 */
export function lightOf(key, byWorld, world) {
  const here = stateOf(byWorld[world]?.doors[key]);
  if (here === 'fermee') return 'closed';
  if (here !== 'ouverte') return 'unknown';
  return Object.values(byWorld).some((other) => stateOf(other.doors[key]) === 'fermee') ? 'ajar' : 'open';
}

/**
 * Le nom d'un trajet : ses parties, dans l'ordre. Chaque partie sauf la dernière porte sa durée,
 * pour distinguer « Master, 1 an » de « Master, 2 ans ». Une recherche d'emploi n'est pas nommée.
 */
export function tripName(legs) {
  const parts = legs.filter((leg) => LANE_OF[leg.block]);
  return T.trip.name(parts.map((leg, i) => (i < parts.length - 1 ? T.trip.lasting(leg.name, durationOf(leg.to_month - leg.from_month)) : leg.name)));
}

/** Les tronçons regroupés par voie. Une recherche d'emploi se dessine sur la voie de l'emploi qui la suit. */
function runsOf(legs) {
  const laneOf = (leg) => LANE_OF[leg?.block];
  const lanes = legs.map((leg, i) => laneOf(leg) ?? laneOf(legs.slice(i + 1).find(laneOf))
    ?? laneOf(legs.slice(0, i).reverse().find(laneOf)) ?? 'work');
  const runs = [];
  legs.forEach((leg, i) => {
    const last = runs.at(-1);
    if (last && last.lane === lanes[i]) {
      last.to = leg.to_month;
      last.legs.push(leg);
    } else runs.push({ lane: lanes[i], from: leg.from_month, to: leg.to_month, legs: [leg], offset: 0 });
  });
  return runs;
}

/** Range une ligne à côté de celles qui occupent déjà la même voie au même moment. */
function place(runs, taken, fixed) {
  for (const run of runs) {
    const busy = (offset) => taken.some((other) => other.lane === run.lane && other.offset === offset
      && other.from < run.to && run.from < other.to);
    run.offset = fixed ?? SIDE.find((offset) => !busy(offset)) ?? 0;
    taken.push(run);
  }
}

/** Les sommets d'une ligne. Elle suit sa voie ; à un changement, l'aiguillage part de la gare et rejoint la voie suivante. */
function linePoints(runs, start) {
  const yOf = (run) => LANE_Y[run.lane] + run.offset;
  const points = [start ?? { x: xOf(runs[0].from), y: yOf(runs[0]) }];
  for (const run of runs) {
    const from = points.at(-1), y = yOf(run), x1 = xOf(run.from), x2 = xOf(run.to);
    if (from.y !== y) points.push({ x: x1 + Math.min(Math.abs(y - from.y) * SLOPE, 0.8 * (x2 - x1)), y });
    points.push({ x: x2, y });
  }
  return points;
}

function pointAt(points, x) {
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i];
    if (x <= b.x || i === points.length - 1) {
      const t = b.x === a.x ? 0 : Math.min(1, Math.max(0, (x - a.x) / (b.x - a.x)));
      return { x, y: a.y + t * (b.y - a.y) };
    }
  }
  return { ...points.at(-1) };
}

/** Le morceau d'une ligne entre deux abscisses. */
function slice(points, x1, x2) {
  return [pointAt(points, x1), ...points.filter((p) => p.x > x1 + 0.01 && p.x < x2 - 0.01), pointAt(points, x2)];
}

/** Un tracé aux angles arrondis. */
function pathOf(points, radius = 13) {
  let d = `M${fmt(points[0])}`;
  for (let i = 1; i < points.length - 1; i++) {
    const a = points[i - 1], b = points[i], c = points[i + 1];
    const toward = (from, to, r) => {
      const length = Math.hypot(to.x - from.x, to.y - from.y) || 1;
      const k = Math.min(r, length / 2) / length;
      return { x: from.x + (to.x - from.x) * k, y: from.y + (to.y - from.y) * k };
    };
    d += ` L${fmt(toward(b, a, radius))} Q${fmt(b)} ${fmt(toward(b, c, radius))}`;
  }
  return `${d} L${fmt(points.at(-1))}`;
}

/**
 * Dessine l'arbre : le trajet en cours, ses gares, ses stations, et les branches qui le quittent.
 * @param trip       la réponse de /path pour le trajet en cours
 * @param pathways   la réponse de /pathways pour ce trajet
 * @param branches   les branches à dessiner : [{ id, label, from_month, legs, by_world }]
 * @param picked     l'identifiant de la branche choisie, ou null : ses petits feux restent affichés
 * @param node       la réponse de /node pour la gare ouverte, ou null
 * @param world      { id, name } : le monde affiché
 * @param selected   { kind: 'station' | 'gare', key | month } ou null
 * @returns la géométrie du trajet en cours, pour le métro : { rail, stops, tunnels }
 */
export function renderMap({ svg, labels, profile, months, trip, pathways, branches, picked, node, world, selected, onStation, onGare, onBranch }) {
  const startAge = profile.age;
  const when = (month) => ageAtMonth(month, startAge);
  const shown = trip.by_world[world.id];
  const light = (key, byWorld = trip.by_world) => lightOf(key, byWorld, world.id);
  const dated = trip.doors.filter((door) => !door.whole_trip).sort((a, b) => a.month - b.month);
  const whole = trip.doors.filter((door) => door.whole_trip);
  const rows = Object.fromEntries((pathways?.by_world[world.id]?.doors ?? []).map((row) => [row.key, row]));
  const focus = selected?.kind === 'station' ? [rows[selected.key]].filter(Boolean) : Object.values(rows);
  const lastTransfers = new Set(focus.filter((row) => row.last_transfer).map((row) => row.last_transfer.gare_month));

  // ------------------------------------------------------------ la géométrie
  const taken = [];
  const runs = runsOf(trip.legs);
  place(runs, taken, 0);
  const points = linePoints(runs);
  const end = xOf(months), tail = points.at(-1);
  const drawn = branches.filter((branch) => branch.legs.length).map((branch) => {
    const branchRuns = runsOf(branch.legs);
    place(branchRuns, taken);
    return { ...branch, lanes: branchRuns.map((run) => run.lane), points: linePoints(branchRuns, pointAt(points, xOf(branch.from_month))) };
  });

  // ---------------------------------------------------------------- le dessin
  const years = Math.round(months / 12);
  const gareMonths = Array.from({ length: Math.max(0, years - 1) }, (_, i) => 12 * (i + 1));
  let art = '<defs><filter id="glow" filterUnits="userSpaceOnUse" x="0" y="0" width="980" height="520">'
    + '<feGaussianBlur stdDeviation="9"/></filter></defs>';
  // Seules les voies utilisées sont dessinées : celles du trajet, et celles des branches de la gare ouverte.
  const inUse = new Set([...runs.map((run) => run.lane), ...drawn.flatMap((branch) => branch.lanes)]);
  const usedLanes = Object.keys(LANE_Y).filter((lane) => inUse.has(lane));          // toujours dans le même ordre, de haut en bas
  const usedY = [...usedLanes].map((lane) => LANE_Y[lane]);
  const top = Math.min(...usedY) - 44, bottom = Math.max(...usedY) + 44;
  art += gareMonths.map((m) => `<path class="guide" d="M${xOf(m)} ${top} V${bottom}"/>`).join('');
  for (const lane of usedLanes) {
    art += `<path class="lane" d="M${X0} ${LANE_Y[lane]} H${end}"/>`;
    art += gareMonths.map((m) => `<circle class="stop" cx="${xOf(m)}" cy="${LANE_Y[lane]}" r="6"/>`).join('');
  }
  // Les branches, sous le trajet en cours : un trait fin. Ses petits feux, un par station datée, n'apparaissent
  // qu'au survol ou quand la branche est choisie.
  for (const branch of drawn) {
    const d = pathOf(branch.points);
    art += `<g class="branch${branch.id === picked ? ' picked' : ''}" data-branch="${escapeHtml(branch.id)}">`
      + `<path class="hit" d="${d}"/><path class="alt" d="${d}"/>`;
    for (const door of dated.filter((dd) => dd.month > branch.from_month)) {
      const at = pointAt(branch.points, xOf(door.month));
      art += `<circle class="dot ${light(door.key, branch.by_world)}" cx="${at.x}" cy="${at.y}" r="7"/>`;
    }
    art += '</g>';
  }
  // Le trajet en cours : chaque tronçon prend la couleur de la station où il mène.
  let from = xOf(0), sections = '', works = '';
  for (const door of dated) {
    const to = xOf(door.month), state = light(door.key);
    if (to > from) {
      const d = pathOf(slice(points, from, to));
      sections += `<path class="section" d="${d}"/>`;
      // Un tronçon fragile, ouvert ici mais fermé dans un autre monde testé, s'affiche « en travaux ».
      if (state === 'ajar') works += `<path class="works" d="${d}"/>`;
    }
    from = to;
  }
  if (from < end) sections += `<path class="section" d="${pathOf(slice(points, from, end))}"/>`;
  art += `<g class="glow" filter="url(#glow)">${sections}</g>${sections}${works}`;
  // Le tunnel : les mois où un financement du découvert est en cours, dans le monde affiché.
  const tunnels = ranges(shown.financing_months);
  for (const [first, last] of tunnels) {
    art += `<path class="tunnel" d="${pathOf(slice(points, xOf(Math.max(first, 0.4)), xOf(Math.min(last + 1, months))))}"/>`;
  }
  // Le butoir : le point de bascule d'une station qui porte sur tout le trajet.
  for (const door of whole) {
    const tipping = rows[door.key]?.tipping;
    if (!tipping) continue;
    const at = pointAt(points, xOf(tipping.month));
    art += `<path class="butoir" d="M${at.x} ${at.y - 15} V${at.y + 15}"><title>${escapeHtml(T.map.tipping(when(tipping.month)))}</title></path>`;
  }
  art += `<circle class="start" cx="${points[0].x}" cy="${points[0].y}" r="14"/>`;
  svg.innerHTML = art;

  // ---------------------------------------------------------------- les textes, les gares et les feux
  labels.replaceChildren();
  const add = (tag, className, html, x, y) => {
    const node = document.createElement(tag);
    node.className = className;
    node.innerHTML = html;
    node.style.left = `${x}px`;
    node.style.top = `${y}px`;
    if (tag === 'button') node.type = 'button';
    labels.appendChild(node);
    return node;
  };
  const isGare = (month) => selected?.kind === 'gare' && selected.month === month;
  const isStation = (key) => selected?.kind === 'station' && selected.key === key;

  const names = tripName(trip.legs);
  const tunnelLine = tunnels.length ? T.map.tunnel(when(tunnels.at(-1)[1] + 1), chf(shown.peak_financing_chf)) : T.map.noTunnel;
  // Les objectifs qui portent sur tout le trajet (« ne jamais passer dans le rouge ») : un indicateur près du titre,
  // suivi de ce que dit le tunnel.
  const indicators = whole.map((door) => `<button type="button" class="indicator ${light(door.key)}" data-station="${escapeHtml(door.key)}" `
    + `aria-pressed="${isStation(door.key)}" aria-label="${escapeHtml(T.map.station(door.name, T.wholeTrip, T.states[light(door.key)]))}">`
    + `<i></i>${escapeHtml(door.name)}</button>`).join('');
  const route = add('div', 'route', `<h1>${escapeHtml(names)}</h1>`
    + `<p>${escapeHtml(T.map.counts(shown.doors_open, shown.doors_total, world.name))}</p>`
    + `<p class="tunnel-line num">${indicators}<span>${escapeHtml(tunnelLine)}</span></p>`, 24, 16);
  route.querySelectorAll('.indicator').forEach((button) => button.addEventListener('click', () => onStation(button.dataset.station)));

  for (const lane of usedLanes) add('div', 'lane-name used', escapeHtml(T.lanes[lane]), X0 - 26, LANE_Y[lane]);
  for (let year = 0; year <= years; year++) add('div', 'age num', escapeHtml(T.age(startAge + year)), xOf(12 * year), 462);

  // Le nom de chaque branche, au début de sa partie droite. Un clic ouvre la gare d'où elle part.
  for (const branch of drawn) {
    let longest = [branch.points[0], branch.points[0]];
    branch.points.forEach((point, i) => {
      const before = branch.points[i - 1];
      if (before && before.y === point.y && point.x - before.x > longest[1].x - longest[0].x) longest = [before, point];
    });
    // Au-dessus de la ligne quand elle passe au-dessus de sa voie, en dessous sinon ; et après le passage du trajet en cours.
    const y = longest[0].y, width = branch.label.length * 6.6 + 16;
    const above = Object.values(LANE_Y).some((lane) => y < lane && lane - y < 37);
    const band = above ? [y - 28, y - 4] : [y + 4, y + 28];
    const crossed = (x) => {
      for (let dx = 0; dx <= width; dx += 6) {
        const main = pointAt(points, x + dx).y;
        if (main + 9 > band[0] && main - 9 < band[1]) return true;
      }
      return false;
    };
    let x = longest[0].x + 18;
    while (crossed(x) && x + width < longest[1].x - 8) x += 8;
    const tag = add('button', `alt-name${above ? '' : ' below'}`, escapeHtml(branch.label), x, y + (above ? -8 : 8));
    tag.dataset.branch = branch.id;
    tag.setAttribute('aria-label', T.map.branch(branch.label));
    const group = svg.querySelector(`g.branch[data-branch="${branch.id}"]`);
    tag.addEventListener('mouseenter', () => group?.classList.add('hover'));
    tag.addEventListener('mouseleave', () => group?.classList.remove('hover'));
    tag.addEventListener('click', () => onBranch(branch.id));
  }

  // Le départ se lit à gauche, au-dessus du nom de sa voie : aucune ligne n'y passe.
  add('div', 'start-name', `${escapeHtml(T.map.start)}<span>${escapeHtml(T.map.startWhere(profile))}</span>`,
    X0 - 26, points[0].y - 22);

  // Les gares de correspondance du trajet en cours. Sous la ligne quand une station occupe déjà la place.
  for (const gare of pathways?.gares ?? []) {
    const month = gare.gare_month, at = pointAt(points, xOf(month));
    const busy = dated.some((door) => door.month === month);
    const classes = ['gare', month === 0 ? 'departure' : '', gare.branches > 1 ? 'known' : 'quiet',
                     gare.matters ? 'matters' : '', lastTransfers.has(month) ? 'last' : '', busy ? 'under' : '',
                     trip.observation?.gare_month === month ? 'seen' : '']
      .filter(Boolean).join(' ');
    const button = add('button', classes, month === 0 ? '' : symbol('gare'), at.x - (busy ? 21 : 0), at.y - (busy ? 21 : 0));
    button.dataset.gare = String(month);
    button.setAttribute('aria-label', (month === 0 ? T.map.departure(gare.age, gare.branches) : T.map.gare(gare.age, gare.branches))
      + (lastTransfers.has(month) ? `, ${T.map.lastTransfer}` : '')
      + (trip.observation?.gare_month === month ? `, ${T.map.seen}` : ''));
    button.setAttribute('aria-pressed', String(isGare(month)));
    button.addEventListener('click', () => onGare(month));
    // La jauge de flexibilité de la gare ouverte : une barre par porte, comme dans sa fiche.
    if (node && node.gare_month === month && isGare(month)) {
      const flex = node.flexibility;
      const lost = flex.doors_total - flex.robust.length - flex.possible.length;
      const pips = [...flex.robust.map(() => 'robust'), ...flex.possible.map(() => 'possible'), ...Array.from({ length: lost }, () => 'lost')];
      const gauge = add('div', 'gauge on-map', pips.map((kind) => `<i class="${kind}"></i>`).join(''), at.x, at.y - (month === 0 ? 34 : 26));
      gauge.setAttribute('role', 'img');
      gauge.setAttribute('aria-label', T.card.flexibility(flex.robust.length, flex.possible.length, flex.doors_total));
    }
  }

  // Les stations datées, à leur âge sur le trajet, avec leur nom en tête de colonne.
  for (const door of dated) {
    const at = pointAt(points, xOf(door.month)), state = light(door.key);
    // Une seule rangée de noms : l'âge se lit sur l'axe, en bas.
    const head = add('div', `head${isStation(door.key) ? ' picked' : ''}`, escapeHtml(door.name), at.x, HEADS);
    head.dataset.station = door.key;
    const button = add('button', `light ${state}`, symbol(state), at.x, at.y);
    button.dataset.station = door.key;
    button.setAttribute('aria-label', T.map.station(door.name, T.age(door.age), T.states[state]));
    button.setAttribute('aria-pressed', String(isStation(door.key)));
    button.addEventListener('click', () => onStation(door.key));
  }
  // La géométrie du trajet en cours, pour le métro : le tracé, les stations datées et les tunnels.
  return { rail: pathOf(points),
           stops: dated.map((door) => ({ key: door.key, x: xOf(door.month), light: light(door.key) })),
           tunnels: tunnels.map(([first, last]) => [xOf(first), xOf(Math.min(last + 1, months))]) };
}

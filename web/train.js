// Le métro : il parcourt le trajet en cours, s'arrête aux stations ouvertes, marque un arrêt bref aux
// stations fragiles et passe sans s'arrêter devant les stations fermées.
// Une animation d'affichage : elle suit le tracé déjà dessiné, et ne calcule aucun montant.

const RUN_MS = 7000;                               // la durée du parcours, hors arrêts
const WAIT_MS = { open: 750, ajar: 320 };          // l'arrêt à une station ouverte, à une station fragile
let frame = null;

/** Arrête le métro et l'enlève de la carte. */
export function stopTrain(svg) {
  if (frame !== null) cancelAnimationFrame(frame);
  frame = null;
  svg.querySelectorAll('.train, #rail').forEach((node) => node.remove());
  delete document.body.dataset.train;
}

/**
 * Fait rouler le métro le long du trajet en cours.
 * @param geometry  ce que renderMap renvoie : { rail, stops: [{ key, x, light }], tunnels: [[x1, x2]] }
 * @param labels    le calque des feux, pour signaler la station desservie
 */
export function runTrain({ svg, labels, geometry, onEnd }) {
  stopTrain(svg);
  const rail = document.createElementNS(svg.namespaceURI, 'path');
  rail.setAttribute('id', 'rail');
  rail.setAttribute('d', geometry.rail);
  rail.setAttribute('fill', 'none');
  svg.appendChild(rail);
  const total = rail.getTotalLength();
  // Le trajet avance toujours vers la droite : la distance parcourue se retrouve à partir de l'abscisse.
  const lengthAt = (x) => {
    let low = 0, high = total;
    for (let i = 0; i < 24; i++) {
      const middle = (low + high) / 2;
      if (rail.getPointAtLength(middle).x < x) low = middle;
      else high = middle;
    }
    return low;
  };
  const stops = geometry.stops.filter((stop) => WAIT_MS[stop.light]).map((stop) => ({ ...stop, at: lengthAt(stop.x) }));
  const tunnels = geometry.tunnels.map(([from, to]) => [lengthAt(from), lengthAt(to)]);

  const train = document.createElementNS(svg.namespaceURI, 'g');
  train.setAttribute('class', 'train');
  train.innerHTML = '<rect x="-20" y="-9" width="40" height="18" rx="9"/><circle class="lamp" cx="14" cy="0" r="3.4"/>';
  svg.appendChild(train);

  let done = 0, last = null, pause = 0, next = 0;
  document.body.dataset.train = 'en route';
  const step = (now) => {
    const elapsed = last === null ? 0 : Math.min(now - last, 80);
    last = now;
    if (pause > 0) pause -= elapsed;
    else {
      done = Math.min(total, done + (elapsed * total) / RUN_MS);
      if (next < stops.length && done >= stops[next].at) {
        done = stops[next].at;
        pause = WAIT_MS[stops[next].light];
        const light = labels.querySelector(`.light[data-station="${stops[next].key}"]`);
        light?.classList.remove('served');
        void light?.offsetWidth;                   // relance l'animation si la station vient d'être desservie
        light?.classList.add('served');
        next += 1;
      }
    }
    const here = rail.getPointAtLength(done), ahead = rail.getPointAtLength(Math.min(total, done + 1));
    const behind = rail.getPointAtLength(Math.max(0, done - 1));
    const angle = (Math.atan2(ahead.y - behind.y, ahead.x - behind.x) * 180) / Math.PI;
    train.setAttribute('transform', `translate(${here.x.toFixed(1)} ${here.y.toFixed(1)}) rotate(${angle.toFixed(1)})`);
    train.classList.toggle('in-tunnel', tunnels.some(([from, to]) => done >= from && done <= to));
    if (done >= total && pause <= 0) {
      frame = null;
      document.body.dataset.train = 'arrivé';
      onEnd?.();
      return;
    }
    frame = requestAnimationFrame(step);
  };
  frame = requestAnimationFrame(step);
}

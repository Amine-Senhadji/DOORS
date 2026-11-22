// Mise en forme des nombres et des dates. Aucun calcul financier : on écrit ce que l'API renvoie.
import { T } from './texts.fr.js';

const grouped = (n) => String(Math.abs(Math.round(n))).replace(/\B(?=(\d{3})+(?!\d))/g, "'");
const decimal = (n, digits) => Number(n.toFixed(digits)).toString().replace('.', ',');

/** Montant au format suisse : 8'000 CHF. */
export function chf(value) {
  return `${Math.round(value) < 0 ? '−' : ''}${grouped(value)} CHF`;
}

/** Un nombre écrit à la suisse, sans unité : 12'800 ou 0,5. */
export function plain(value) {
  const [whole, rest] = Math.abs(value).toFixed(2).split('.');
  return `${value < 0 ? '−' : ''}${whole.replace(/\B(?=(\d{3})+(?!\d))/g, "'")}${rest === '00' ? '' : `,${rest.replace(/0$/, '')}`}`;
}

/** Un mois du trajet, écrit comme un âge : le mois 6 d'une personne de 20 ans est « 20 ans et 6 mois ». */
export function ageAtMonth(month, startAge) {
  return T.ageAt(startAge + Math.floor(month / 12), month % 12);
}

/** Une durée en mois, écrite en années et en mois : 24 donne « 2 ans », 27 donne « 2 ans et 3 mois ». */
export function durationOf(months) {
  return T.duration(Math.floor(months / 12), months % 12);
}

/** Des mois qui se suivent, regroupés en plages : [6, 7, 8, 12] donne [[6, 8], [12, 12]]. */
export function ranges(months) {
  const out = [];
  for (const month of months) {
    const last = out.at(-1);
    if (last && month === last[1] + 1) last[1] = month;
    else out.push([month, month]);
  }
  return out;
}

/** La valeur d'un paramètre de monde, écrite avec son unité : −30 %, 1,06, oui. */
export function worldValue(field, value) {
  if (typeof value === 'boolean') return value ? T.traffic.yes : '';
  if (field.endsWith('_monthly')) return `${value < 0 ? '−' : '+'}${decimal(Math.abs(value) * 100, 1)} %`;
  return decimal(value, 2);
}

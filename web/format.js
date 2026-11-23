// Mise en forme des nombres et des dates. Aucun calcul financier : on écrit ce que l'API renvoie.
import { T } from './i18n.js';

// To the franc, as the engine rounds when it writes an amount in a sentence: an exact half franc goes to the even franc
// (103'330.50 is written 103'330), so that the screen and the engine's sentences never differ by one franc.
const franc = (n) => {
  const up = Math.round(n);
  return up - n === 0.5 && up % 2 ? up - 1 : up;
};
const grouped = (n) => String(Math.abs(franc(n))).replace(/\B(?=(\d{3})+(?!\d))/g, "'");
const decimal = (n, digits) => Number(n.toFixed(digits)).toString().replace('.', T.decimalMark);

/** Montant au format suisse : 8'000 CHF. */
export function chf(value) {
  return `${franc(value) < 0 ? '−' : ''}${grouped(value)} CHF`;
}

/** Un nombre écrit à la suisse, sans unité : 12'800 ou 0,5. */
export function plain(value) {
  const [whole, rest] = Math.abs(value).toFixed(2).split('.');
  return `${value < 0 ? '−' : ''}${whole.replace(/\B(?=(\d{3})+(?!\d))/g, "'")}${rest === '00' ? '' : `${T.decimalMark}${rest.replace(/0$/, '')}`}`;
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

/** What sets a world apart from the reference world, one sentence per parameter, as the engine describes it. */
export function worldDetails(parameters, horizon, startAge) {
  const when = (month) => ageAtMonth(month, startAge);
  return parameters.map((p) => {
    const span = p.to_month >= horizon && p.months > 1 ? T.traffic.since(when(p.from_month))
      : T.traffic.span(when(p.from_month), when(p.months > 1 ? p.to_month : p.from_month));
    if (typeof p.value === 'boolean') return T.traffic.flag(p.label, span);
    return T.traffic.parameter(p.label, `${worldValue(p.field, p.value)} ${T.traffic.reference(worldValue(p.field, p.reference))}`, span);
  });
}

/** La valeur d'un paramètre de monde, écrite avec son unité : −30 %, 1,06, oui. */
export function worldValue(field, value) {
  if (typeof value === 'boolean') return value ? T.traffic.yes : '';
  if (field.endsWith('_monthly')) return T.percent(`${value < 0 ? '−' : '+'}${decimal(Math.abs(value) * 100, 1)}`);
  return decimal(value, 2);
}

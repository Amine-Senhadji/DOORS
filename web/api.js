// Les appels à l'API. Tout chiffre affiché vient d'ici, donc du moteur de l'équipe (engine/).
// Les formes des réponses sont décrites dans docs/API.md.
//
// Les routes de la version 3 (/worlds, /path, /node, /pathways) sont servies par api/main.py, à partir de engine/tree.py.
import { lang } from './i18n.js';

const V3 = '';

// Les hypothèses modifiées dans le tiroir : elles accompagnent chaque demande de calcul.
let overrides = {};
export function setAssumptions(values) {
  overrides = { ...values };
}

// Le jumeau qui apprend : ce qu'Alexia a vraiment de côté à une gare, { gare_month, value_chf }. Le moteur en tient compte
// dans chaque calcul du trajet en cours.
let observation = null;
export function setObservation(value) {
  observation = value ? { ...value } : null;
}
const seen = (path) => (path.length && observation ? { observation } : {});

// Les mondes testés, avec l'âge choisi pour chaque crise (« krach@25 »). Sans réglage : ceux du moteur, à leur âge d'origine.
let mondes = null;
export function setWorlds(ids) {
  mondes = ids ? [...ids] : null;
}
const tested = () => (mondes ? { mondes } : {});

async function call(address, body) {
  // Chaque appel dit dans quelle langue le moteur doit écrire ses phrases. Les chiffres sont les mêmes.
  const url = `${address}${address.includes('?') ? '&' : '?'}lang=${lang}`;
  let response;
  try {
    response = await fetch(url, body === undefined ? undefined : {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  } catch (error) {
    throw new Error('serveur');
  }
  const data = await response.json();
  if (!response.ok) {
    const refused = new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
    refused.refused = true;
    throw refused;
  }
  return data;
}

/** Le scénario : le profil et la durée. */
export const fetchScenario = (id = 'alexia') => call(`/scenario/${encodeURIComponent(id)}`);

/** Les mondes nommés, pour « Info trafic ». */
export const fetchWorlds = (ids) => call(`${V3}/worlds${ids ? `?mondes=${encodeURIComponent(ids.join(','))}` : ''}`);

/** Un trajet : ses tronçons, ses stations dans chaque monde testé, et sa vie mois par mois dans le monde affiché. */
export const fetchPath = (path, worldId) => call(`${V3}/path`, { path, world_id: worldId, assumptions: overrides, ...tested(), ...seen(path) });

/** Une gare du trajet : ses branches, sa flexibilité. `path` vide et mois 0 : les lignes de départ. */
export const fetchNode = (path, gareMonth) => call(`${V3}/node`, { path, gare_month: gareMonth, assumptions: overrides, ...tested(), ...seen(path) });

/** Le trajet suivi depuis le départ : points de bascule, dernières correspondances utiles, gares qui comptent. */
export const fetchPathways = (path) => call(`${V3}/pathways`, { path, gare_month: 0, assumptions: overrides, ...tested(), ...seen(path) });

/** Plan figé contre politique : le trajet sans changement, et le même trajet qui applique sa règle par défaut. */
export const fetchAdaptive = (path) => call(`${V3}/adaptive`, { path, assumptions: overrides, ...tested(), ...seen(path) });

/** Le tableau de valeur : le plan figé et les trois politiques, dans les mondes du tableau (ceux du moteur, pas ceux d'« Info trafic »). */
export const fetchPolicies = (path) => call(`${V3}/policies`, { path, assumptions: overrides });

/** Une règle répandue, mise à l'épreuve par le moteur dans deux états d'Alexia. */
export const fetchFolkRule = (path) => call(`${V3}/folk-rule`, { path, assumptions: overrides });

/** The AI layer. Its status: the mode (live or recorded), the model, and what is recorded. */
export const fetchAiStatus = () => call('/ai/status');
/** "Find what breaks my plan" for a route: the answer of the model if there is one, and what the engine finds on its own. */
export const askStress = (path) => call('/ai/stress', { path, assumptions: overrides });
/** "Ask in your own words": one sentence read into settings. Nothing is computed by this call. */
export const askSentence = (sentence, path) => call('/ai/ask', { sentence, path, assumptions: overrides });

/** Le tiroir : les hypothèses, les vérifications en direct, l'égalité avec le starter-kit relancée, les limites. */
export const fetchAssumptions = () => call('/assumptions');
export const fetchChecks = () => call('/checks');
export const runStarterKit = () => call('/checks/starter-kit', {});
export const fetchLimits = () => call('/limits');

// La langue de la page : l'anglais par défaut, le français avec ?lang=fr dans l'adresse.
// Les deux fichiers de textes ont les mêmes clés ; les chiffres, eux, ne dépendent pas de la langue.
import { T as EN } from './texts.en.js';
import { T as FR } from './texts.fr.js';

export const lang = new URLSearchParams(location.search).get('lang') === 'fr' ? 'fr' : 'en';
export const T = lang === 'fr' ? FR : EN;

/** L'adresse de la même page dans l'autre langue. Tout le reste de l'adresse est gardé. */
export function otherLanguageUrl() {
  const url = new URL(location.href);
  if (T.language.other === 'en') url.searchParams.delete('lang');
  else url.searchParams.set('lang', T.language.other);
  return url.pathname + url.search;
}

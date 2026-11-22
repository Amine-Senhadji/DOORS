// Tous les textes de l'interface, en un seul fichier.
// Les chiffres viennent de l'API : ces fonctions ne font que les placer dans des phrases.
// Règle du projet : les mots interdits n'apparaissent nulle part ici. On écrit « dans 4 des 6 mondes
// testés ». Aucune branche n'est classée ni suggérée : le bouton s'appelle « Prendre cette branche ».

const plural = (n, one, many) => `${n} ${n > 1 ? many : one}`;
// « d’Alexia », « de Samir » : l'élision devant une voyelle ou un h.
const of = (name) => (/^[aeiouyhàâéèêëîïôöùûü]/i.test(name) ? `d’${name}` : `de ${name}`);
const lower = (text) => text.charAt(0).toLowerCase() + text.slice(1);
const list = (items) => (items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} et ${items.at(-1)}`);
const open = (n, total) => `${plural(n, 'station ouverte', 'stations ouvertes')} sur ${total}`;

export const T = {
  brand: 'Doors',
  // Comment cette langue écrit les nombres, et comment passer à l'autre.
  decimalMark: ',',
  percent: (written) => `${written} %`,
  language: { other: 'en', switchTo: 'English', label: 'Langue' },
  quoted: (text) => `« ${text} »`,
  who: (p, cash) => `${p.name}, ${p.age} ans, ${p.city}, ${cash} de côté`,
  banner: 'Scénarios sous hypothèses, données fictives. Ni prévision, ni conseil.',

  loading: 'Chargement…',
  serverDown: 'Le serveur ne répond pas. Lancez « python -m api », puis rechargez la page.',
  refused: (message) => `Demande refusée par le moteur. ${message}`,

  // Les quatre voies de la carte : un choix d'affichage, pas une donnée du moteur.
  lanes: { study: 'Études', work: 'Emploi en Suisse', abroad: 'Emploi à l’étranger', project: 'Projet ou pause' },
  age: (age) => `${age} ans`,
  // Un âge au mois près. Mise en forme d'une date, pas un calcul financier.
  ageAt: (years, months) => (months ? `${years} ans et ${months} mois` : `${years} ans`),
  duration: (years, months) => [years ? plural(years, 'an', 'ans') : '', months ? `${months} mois` : ''].filter(Boolean).join(' et '),

  trip: {
    title: 'Ton trajet',
    name: (names) => names.map((name, i) => (i ? lower(name) : name)).join(', puis '),
    lasting: (name, duration) => `${name} ${duration}`,
    when: (from, to) => `${from} → ${to}`,
    catalog: (ids) => `${ids.length > 1 ? 'scénarios' : 'scénario'} ${ids.join(', ')} du défi`,
  },

  traffic: {
    title: 'Info trafic',
    group: 'Monde affiché',
    span: (from, to) => (from === to ? `à ${from}` : `de ${from} à ${to}`),
    since: (from) => `à partir de ${from}`,
    yes: 'oui',
    parameter: (label, value, when) => `${label} : ${value}, ${when}.`,
    flag: (label, when) => `${label} ${when}.`,
    reference: (value) => `(${value} dans le monde de référence)`,
    // L'âge où la crise affichée commence, réglable d'une gare à l'autre.
    age: 'Début de la crise',
    years: (age) => `${age} ans`,
    earlier: 'Un an plus tôt',
    later: 'Un an plus tard',
    range: (from, to) => `Réglable de ${from} à ${to} ans`,
    origin: (age) => `revenir à ${age} ans`,
  },

  // L'état affiché d'une station. « ajar » : ouverte dans le monde affiché, fermée dans un autre monde testé.
  states: { open: 'Station ouverte', ajar: 'Station ouverte ici, fermée dans un autre monde testé',
            closed: 'Station fermée', unknown: 'Station non calculée' },
  doorState: { ouverte: 'ouverte', fermee: 'fermée' },
  // La nature d'une hypothèse, telle que le moteur la donne (engine/assumptions.py).
  kinds: { observe: 'données synthétiques du défi', starter_kit: 'hypothèse illustrative du starter-kit', hypothese: 'hypothèse de l’équipe',
           a_verifier: 'ordre de grandeur suisse, à vérifier', regle: 'règle simplifiée de l’équipe' },
  wholeTrip: 'tout le trajet',
  worldsOpen: (n, total) => (n === total ? `Ouverte dans les ${total} mondes testés.`
    : n === 0 ? `Fermée dans les ${total} mondes testés.` : `Ouverte dans ${n} des ${total} mondes testés.`),

  map: {
    start: 'Départ',
    startWhere: (p) => `${p.age} ans, ${p.city}`,
    counts: (n, total, world) => `${open(n, total)} · ${world}`,
    station: (name, when, state) => `${name}, ${when} : ${state}`,
    gare: (age, branches) => `Gare de correspondance, ${age} ans : ${plural(branches, 'branche', 'branches')}`,
    departure: (age, branches) => `Départ, ${age} ans : ${plural(branches, 'ligne', 'lignes')}`,
    lastTransfer: 'dernière correspondance utile',
    seen: 'épargne constatée',
    tipping: (when) => `Point de bascule, ${when}`,
    // Le tunnel : les mois où le moteur inscrit un financement du découvert.
    tunnel: (to, amount) => `Tunnel jusqu’à ${to} · ${amount} à financer au plus`,
    noTunnel: 'Aucun tunnel : le solde ne passe jamais dans le rouge.',
    branch: (label) => `Branche : ${label}`,
  },

  card: {
    pick: 'Clique sur une station, ou sur une gare de correspondance.',
    details: 'Détails',
    origin: 'Résultats calculés par le moteur, sous ses hypothèses. Ni prévision, ni conseil.',
    back: 'Revenir au trajet',

    // --- le trajet
    trip: 'Ton trajet',
    shown: (world) => `Dans le monde affiché : ${lower(world)}.`,
    open,
    noFinancing: 'Aucun financement nécessaire : le solde ne passe jamais dans le rouge.',
    financing: (n, from, to, amount) => `Financement nécessaire pendant ${n} mois, entre ${from} et ${to}, jusqu’à ${amount}.`,
    netWorth: (age, amount) => `Patrimoine à ${age} ans : ${amount}.`,
    worlds: (n) => `Dans les ${n} mondes testés`,
    columns: ['Monde', 'Stations ouvertes', 'Financement max.', 'Patrimoine à la fin'],

    // --- une station
    stateAt: (state, when) => `${state} · ${when}`,
    whyTitle: 'Où ce trajet cesse de la tenir',
    tipping: (when) => `Point de bascule : ${when}. C’est le moment où ce trajet cesse de tenir cette station.`,
    noReturn: (age) => `Point de non-retour : la gare de ${age} ans. À partir d’elle, aucune branche calculée ne l’ouvre plus.`,
    noReturnAtStart: 'Aucune branche calculée ne l’ouvre, même au départ.',
    lastTransfer: (where, label) => `Dernière correspondance utile : ${where}, par la branche « ${label} ».`,
    atDeparture: (age) => `le départ, à ${age} ans`,
    atGare: (age) => `la gare de ${age} ans`,
    seeGare: 'Voir cette gare',
    signpost: 'À surveiller',
    holds: 'Ce trajet tient cette station dans le monde affiché.',
    source: (kind, source) => `Origine de l’objectif : ${kind}. ${source}`,
    margin: (value, required) => `${value} pour ${required} demandés`,
    here: (margin) => `Dans le monde affiché : ${margin}.`,

    // --- une gare
    gare: (age) => `Gare de correspondance · ${age} ans`,
    departure: (age) => `Départ · ${age} ans`,
    flexibility: (robust, some, total) => `Depuis ici, ${plural(robust, 'porte', 'portes')} sur ${total} `
      + `${robust > 1 ? 'restent atteignables' : 'reste atteignable'} quoi qu’il arrive dans les mondes testés`
      + (some ? ` ; ${some === 1 ? '1 autre seulement' : `${some} autres seulement`} dans certains mondes.` : '.'),
    horizon: (text) => `Compté ${text}.`,
    robust: (names) => `Quoi qu’il arrive : ${list(names)}.`,
    possible: (names) => `Dans certains mondes seulement : ${list(names)}.`,
    lost: (names) => `Plus atteignable d’ici : ${list(names)}.`,
    matters: 'Cette gare compte : selon la branche, les stations ouvertes ne sont pas les mêmes.',
    quiet: 'À cette gare, changer de branche ne change aucune station dans les mondes testés. Les montants, eux, changent.',
    alone: 'Aucune autre branche n’est calculée à cette gare pour l’instant.',
    state: (world, cash, debt, worth) => `À cette gare, dans le monde affiché (${lower(world)}) : ${cash} sur le compte, ${debt} de dette, patrimoine de ${worth}.`,
    // Où en sont les crises testées quand on arrive à cette gare.
    // Trois états, tels que le moteur les donne : déjà eu lieu, en cours, à venir.
    shocks: (age, over, running, coming) => [
      over.length ? `À ${age} ans, ${over.length > 1 ? 'ces crises testées ont' : 'cette crise testée a'} déjà eu lieu : ${list(over.map(lower))}.` : '',
      running.length ? `${over.length ? 'En cours' : `À ${age} ans, en cours`} : ${list(running.map(lower))}.` : '',
      coming.length ? `${over.length || running.length ? 'À venir' : `À ${age} ans, aucune crise testée n’a encore eu lieu. À venir`} : ${list(coming.map(lower))}.` : '',
    ].filter(Boolean).join(' '),
    // Un monde à deux crises : où en est chacune à cette gare, tel que le moteur le dit.
    crisisStatus: { passee: 'déjà eu lieu', en_cours: 'en cours', a_venir: 'à venir' },
    combined: (age, crises) => `Monde à deux crises, à ${age} ans : ${list(crises.map((c) => `${lower(c.name)} (${T.card.crisisStatus[c.status]})`))}.`,
    // Le jumeau qui apprend : Alexia dit ce qu'elle a vraiment de côté à cette gare.
    observe: {
      ask: 'Combien as-tu vraiment de côté ?',
      hint: 'Cash + placements − dettes, à cet âge.',
      unit: 'CHF',
      apply: 'Utiliser',
      forget: 'Revenir à l’épargne simulée',
      simulated: (world, amount) => `Le jumeau simule ${amount} de côté à cette gare, dans le monde affiché (${lower(world)}).`,
      instead: (world, amount) => `Le jumeau simulait ${amount} dans le monde affiché (${lower(world)}). Les branches ci-dessous repartent de ta valeur, dans chaque monde testé.`,
      noSignal: 'Ce trajet n’a pas de signal à surveiller à cette gare : ta valeur change la suite, sans seuil auquel la comparer.',
      elsewhere: (age, amount) => `Épargne constatée à ${age} ans : ${amount}. Saisir une valeur ici la remplace.`,
      trip: (age, amount) => `Épargne constatée à ${age} ans : ${amount}. À partir de cet âge, la carte suit cette valeur, pas l’épargne simulée.`,
    },
    branches: 'Les branches',
    current: 'ton trajet actuel',
    take: 'Prendre cette branche',
    summary: (stations, financing, worth) => `${stations} · financement max. ${financing} · patrimoine à la fin ${worth}`,
    more: (label, n) => `Référence clairvoyante : en connaissant ce monde à l’avance, la branche « ${label} » garderait ${plural(n, 'porte', 'portes')} de plus que ton trajet actuel. Personne ne le connaît à l’avance.`,
    barred: 'Branche fermée',
    partial: (ages) => `Branches calculées pour l’instant : ${list(ages)}. Les autres gares arrivent avec la suite du moteur.`,
    partialAt: { departure: 'au départ', gare: (age) => `à ${age} ans` },
  },

  // Plan figé contre politique. Aucun des deux n'est classé : on montre ce que chacun garde.
  plan: {
    button: 'Plan figé ou politique',
    title: 'Plan figé ou politique',
    rule: 'La règle.',
    fixed: 'Plan figé',
    adaptive: 'Politique',
    kept: 'Objectifs gardés',
    borrowing: 'Emprunt maximal',
    worth: 'Patrimoine à la fin',
    count: (n, total) => `${n} sur ${total}`,
    observed: (world, age, amount, applies) => `Dans le monde affiché (${lower(world)}), à ${age} ans : ${amount} de côté. `
      + (applies ? 'La règle s’applique.' : 'La règle ne s’applique pas : les deux plans sont les mêmes.'),
    seen: (age, amount, applies) => `Tu as dit avoir ${amount} de côté à ${age} ans : la règle lit cette valeur, dans chaque monde testé. `
      + (applies ? 'La règle s’applique.' : 'La règle ne s’applique pas : les deux plans sont les mêmes.'),
    since: (age, amount) => `Les deux plans suivent le trajet vécu depuis l’épargne constatée à ${age} ans (${amount}).`,
    tooLate: (age) => `L’épargne constatée à ${age} ans arrive après la gare de la règle : la règle lit l’épargne simulée.`,
    reopened: (names) => `La règle garde ${list(names)}, que le plan figé perd.`,
    lost: (names) => `Elle perd ${list(names)}, que le plan figé garde.`,
    avoided: (amount) => `Emprunt évité : ${amount}.`,
    summary: (door, adaptive, fixed, worlds) => `La règle garde « ${door} » dans ${plural(adaptive, 'monde', 'mondes')} sur ${worlds}, le plan figé dans ${fixed}.`,
    columns: ['Monde', 'Figé', 'Adaptatif', 'Emprunt évité'],
    same: 'mêmes plans',
    onlyState: 'La décision ne regarde que l’état atteint à la gare, jamais la suite.',
    none: (message) => `Pas de politique pour ce trajet. ${message}`,
  },

  // Trois bandes pour un résultat, sans fréquence chiffrée : le pire monde testé, le monde de référence, un monde prudent.
  bands: {
    title: 'Trois bandes : trois mondes, pas des fréquences',
    pire: 'Pire monde testé',
    central: 'Central',
    prudent: 'Prudent',
    columns: ['', 'Stations ouvertes', 'Financement max.', 'Patrimoine à la fin'],
    count: (n, total) => `${n} sur ${total}`,
    everywhere: 'tous les mondes testés',
    note: (points) => `Pire monde testé : le moins favorable des mondes testés, chiffre par chiffre. Central : le monde de référence. `
      + `Prudent : le monde de référence, avec un rendement des placements diminué de ${points} par an. Aucune bande n’est une promesse.`,
    points: (n, written) => `${written} ${n > 1 ? 'points' : 'point'}`,
    station: (worst, where, central, prudent, required) => `Pire monde testé : ${worst} (${where}) · central : ${central} · prudent : ${prudent}. Demandé : ${required}.`,
    stationState: (worst, where, central, prudent) => `Pire monde testé : ${worst} (${where}) · central : ${central} · prudent : ${prudent}.`,
    worth: 'Patrimoine à la fin',
    sheetNote: 'Pour une politique, le pire monde testé peut être le monde sans choc : elle y suit le plan, master compris, et les six objectifs ne mesurent pas ce que vaut le diplôme.',
  },

  // Des politiques, pas des plans : le tableau de valeur. Une politique lit l'état présent et décide ; elle ne lit jamais la suite.
  policies: {
    button: 'Politiques',
    title: 'Des politiques, pas des plans',
    close: 'Fermer',
    intro: 'Un plan figé ne regarde rien. Une politique est une règle : arrivée à sa date, elle regarde ce que tu as de côté, puis décide. '
      + 'Elle ne lit jamais la suite. Ce tableau montre ce que chaque choix achète comme résilience, et ce qu’il coûte.',
    target: (name, amount, age) => `Objectif visé par les trois politiques : « ${name} », ${amount} à ${age} ans (objectif d’Alexia, données synthétiques du défi).`,
    noShock: 'Pas de choc',
    world: (name, age, months, gravity) => `${name} à ${age} ans` + (months ? ` (${months} mois)` : '') + (gravity !== 100 ? `, gravité ${gravity} %` : ''),
    long: 'choc long',
    kept: (n, total) => `${plural(n, 'objectif', 'objectifs')} sur ${total}`,
    fate: {
      termine: (age) => `Master terminé à ${age} ans`,
      termine_en_travaillant: (age) => `Master terminé à ${age} ans, en travaillant`,
      arrete: (age) => `Master arrêté à ${age} ans`,
      pas_commence: () => 'Master pas commencé',
    },
    borrowing: 'Emprunt maximal',
    regret: 'Regret',
    applies: 'la règle s’applique',
    follows: 'suit le plan',
    fixedRule: 'Le trajet, sans rien changer. Il ne lit rien.',
    how: {
      securite: 'Décide avant de commencer le master.',
      equilibre: 'Commence le master, et l’arrête si l’épargne manque.',
      ambition: 'Commence le master, et le finit en travaillant si l’épargne manque.',
    },
    seer: 'Référence clairvoyante',
    seerHow: 'Ce qu’on aurait choisi en connaissant le monde à l’avance.',
    regretIs: 'Regret : ce qui manque pour l’objectif visé, alors qu’une des quatre options l’aurait tenu. C’est le prix de ne pas savoir. Il est nul quand l’objectif tient.',
    seerIs: 'La référence clairvoyante n’est pas une action possible : personne ne connaît le monde à l’avance. Elle sert d’étalon, pas de marche à suivre.',
    limit: 'La valeur d’un diplôme au-delà de 30 ans n’est pas mesurée par les six objectifs ; comparer à 30 ans pénalise le master.',
    // Alexia, et Alexia fragile : la même politique, deux états de départ.
    cases: 'Alexia ou Alexia fragile',
    caseOf: (amount) => `Alexia · ${amount} de côté à 20 ans`,
    fragileCase: (amount) => `Alexia fragile · ${amount} de côté à 20 ans`,
    caseShort: (amount) => `Alexia, ${amount} au départ`,
    fragileShort: (amount) => `Alexia fragile, ${amount} au départ`,
    sameRules: 'Mêmes règles, mêmes seuils pour les deux : une politique lit l’état, et c’est l’état qui change.',
    gapTitle: 'L’écart entre chaque politique et le plan figé, pour les deux Alexia',
    gapIntro: 'Ce que la politique change par rapport au plan figé, monde par monde : objectifs gardés en plus, emprunt maximal en plus ou en moins.',
    doorsMore: (n) => (n === 0 ? 'Autant d’objectifs' : `${n > 0 ? '+' : '−'}${plural(Math.abs(n), 'objectif', 'objectifs')}`),
    borrowingMore: (difference, written) => (difference === 0 ? 'Même emprunt maximal' : `Emprunt maximal : ${difference > 0 ? '+' : ''}${written}`),
    saved: (door) => `« ${door} » sauvée`,
    none: 'aucun seuil',
    choiceTitle: 'Comment chaque seuil est choisi',
    choice: 'Dans l’ordre : le plus de mondes où l’objectif tient ; puis le plus petit regret dans le monde le plus dur, puis dans le suivant ; '
      + 'à égalité, la règle qui quitte le plan dans le moins de mondes. Un seul seuil par règle, pris au milieu de la zone qui fonctionne, pas au bord.',
    zone: (name, threshold, low, high) => `${name} : seuil de ${threshold}, au milieu de la zone qui fonctionne. Bord bas, ${low} : le point de bascule `
      + `calculé par le moteur, sous lequel le plan perd l’objectif même sans choc. Bord haut, ${high} : la plus basse épargne d’un monde où le plan le tient.`,
    zoneOpen: (name, threshold, low) => `${name} : seuil de ${threshold}. Dans tous les mondes testés l’épargne est en dessous : la zone n’a pas de bord haut, le seuil est son bord bas (${low}).`,
    noZone: (name) => `${name} : aucun seuil ne sert l’objectif dans les mondes testés ; la règle ne s’applique pas.`,
    leftOutTitle: 'Un monde laissé de côté',
    leftOut: 'Le seuil est recalculé sans ce monde, puis essayé sur lui : le seuil trouvé, et si l’objectif visé y tient.',
    leftOutCell: (threshold, holds) => `${threshold} · ${holds ? 'tient' : 'perdu'}`,
    variantsTitle: 'Variantes des mondes : l’ensemble de test',
    variants: 'Les mêmes crises, un an plus tôt, un an plus tard, moins fortes, plus fortes. Les seuils ne changent pas : objectifs gardés, et l’objectif visé.',
    blind: 'Un choc qui arrive après la dernière date de décision ne se voit pas dans l’épargne : aucune règle sur l’épargne ne peut le voir venir.',
    variantCell: (n, total, holds) => `${n} sur ${total} · ${holds ? 'tient' : 'perdu'}`,
    drawnTitle: 'Variantes tirées au hasard',
    drawn: (n, seed, from, to, low, high) => `${n} variantes tirées avec une graine fixe (${seed}) : une crise du tableau, à un âge entre ${from} et ${to} ans, `
      + `d’une gravité entre ${low} et ${high} %. Elles servent à éprouver les politiques, jamais un plan figé. Ce sont des comptes, pas des fréquences attendues.`,
    drawnKept: (name, door, kept, n, applied) => `${name} : « ${door} » tient dans ${kept} des ${n} variantes tirées ; la règle s’applique dans ${applied}.`,
    drawnSeer: (kept, n) => `Référence clairvoyante : dans ${kept} des ${n}.`,
    refused: (message) => `Pas de tableau de politiques pour ce trajet. ${message}`,
  },

  // Une règle répandue, mise à l'épreuve par le moteur dans deux états d'Alexia.
  folk: {
    button: 'Une règle répandue, à l’épreuve',
    title: 'Une règle répandue, à l’épreuve',
    noShock: 'Pas de choc',
    world: (name, age) => `${name} à ${age} ans`,
    how: (age, months, window) => `L’épreuve : à ${age} ans, exactement ${months} mois de dépenses courantes sur le compte, et rien d’autre. `
      + `La règle tient si Alexia ne passe pas dans le rouge pendant les ${window} mois qui suivent. Deux états au même âge, les mêmes mondes.`,
    cushion: (expenses, months, cushion) => `Dépenses courantes : ${expenses} par mois. Coussin de ${months} mois : ${cushion}.`,
    kept: (n, total) => `La règle tient dans ${n} des ${total} mondes testés.`,
    needed: (amount, months, less) => (less ? `Il suffirait de ${amount} de côté, soit ${months} mois de dépenses.`
      : `Il faudrait ${amount} de côté, soit ${months} mois de dépenses.`),
    never: 'Aucun coussin testé ne suffit.',
    holds: 'Tient',
    breaks: 'Dans le rouge',
    red: (when, amount) => `dès ${when}, jusqu’à ${amount} à financer`,
    why: 'Une règle fixe ne lit pas l’état. Salariée, Alexia a un salaire qui couvre ses dépenses : le coussin n’a qu’un choc à absorber. '
      + 'En master, son budget est en déficit chaque mois : le coussin doit financer les études elles-mêmes. C’est ce qu’une politique lit, et qu’une règle répandue ignore.',
    limit: 'Le coussin est compté sur le compte seul, sans placements à vendre. Les mondes testés sont le monde de référence et chaque crise placée à cet âge.',
    refused: (message) => `Pas d’épreuve pour ce trajet. ${message}`,
  },

  // Le tiroir : ce qui prouve et ce qui limite.
  drawer: {
    open: 'Hypothèses et preuves',
    title: 'Hypothèses et preuves',
    close: 'Fermer',
    sections: { hypotheses: 'Les hypothèses', verifications: 'Les vérifications en direct', registre: 'Le registre d’un mois', limites: 'Les limites' },
    assumptionsHelp: 'Chaque valeur porte sa nature et sa source. Change une valeur : tout le trajet est recalculé par le moteur.',
    changed: (n) => `${plural(n, 'valeur modifiée', 'valeurs modifiées')}.`,
    modified: (value, unit) => `Valeur saisie par toi. Valeur d’origine : ${value} ${unit}.`,
    reset: 'Revenir à la valeur d’origine',
    resetAll: 'Tout remettre à l’origine',
    checksHelp: 'Ces contrôles sont lancés maintenant par le moteur, sur les lignes du scénario.',
    runKit: 'Relancer l’égalité avec le starter-kit du défi',
    kitResult: (passed, total, seconds, at) => `${passed} tests réussis sur ${total}, en ${String(seconds).replace('.', ',')} s, à ${at}.`,
    ledgerHelp: (world) => `Chaque franc du mois choisi, pour le trajet affiché, dans le monde affiché (${lower(world)}).`,
    month: (month, age) => `Mois ${month} · ${age}`,
    opening: 'Compte au début du mois',
    closing: 'Compte à la fin du mois',
    debt: 'Dettes à la fin du mois',
    netWorth: 'Patrimoine à la fin du mois',
    note: (label) => `Note : ${label}`,
    accounts: { cash: 'compte', placements: 'placements', pilier2: '2e pilier', logement: 'logement', dette: 'dette' },
    limitsHelp: (source) => `Ce que le modèle ne fait pas, ou fait en simplifiant (${source}).`,
  },

  train: {
    go: 'Faire rouler le métro',
    stop: 'Arrêter le métro',
    again: 'Refaire rouler le métro',
    how: 'Le métro s’arrête aux stations ouvertes, marque un arrêt bref aux stations fragiles et passe devant les stations fermées.',
  },

  legend: {
    open: 'Ouverte dans le monde affiché',
    ajar: 'Ouverte ici, fermée dans un autre monde testé',
    closed: 'Fermée dans le monde affiché',
    tunnel: 'Tunnel : financement nécessaire',
    gare: 'Gare de correspondance',
    last: 'Dernière correspondance utile',
  },
};

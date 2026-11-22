// Every text of the interface in English, in one file. Same keys as texts.fr.js.
// The figures come from the API: these functions only place them in sentences.
// Project rule: the banned words appear nowhere here. We write "in 4 of the 6 tested worlds".
// No branch is ranked or suggested: the button is called "Take this branch".

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const lower = (text) => text.charAt(0).toLowerCase() + text.slice(1);
const list = (items) => (items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`);
const open = (n, total) => `${plural(n, 'station open', 'stations open')} out of ${total}`;

export const T = {
  brand: 'Doors',
  // How this language writes numbers and switches to the other one.
  decimalMark: '.',
  percent: (written) => `${written}%`,
  language: { other: 'fr', switchTo: 'Français', label: 'Language' },
  quoted: (text) => `“${text}”`,
  who: (p, cash) => `${p.name}, ${p.age}, ${p.city}, ${cash} set aside`,
  banner: 'Scenarios under assumptions, fictional data. Not a forecast, not advice.',

  loading: 'Loading…',
  serverDown: 'The server does not answer. Run "python -m api", then reload the page.',
  refused: (message) => `Request refused by the engine. ${message}`,

  // The four lanes of the map: a display choice, not engine data.
  lanes: { study: 'Studies', work: 'Swiss job', abroad: 'Job abroad', project: 'Project or break' },
  age: (age) => `age ${age}`,
  // An age to the month. Formatting of a date, not a financial calculation.
  ageAt: (years, months) => (months ? `${years} years ${plural(months, 'month', 'months')}` : `age ${years}`),
  duration: (years, months) => [years ? plural(years, 'year', 'years') : '', months ? plural(months, 'month', 'months') : ''].filter(Boolean).join(' and '),

  trip: {
    title: 'Your route',
    name: (names) => names.map((name, i) => (i ? lower(name) : name)).join(', then '),
    lasting: (name, duration) => `${name} ${duration}`,
    when: (from, to) => `${from} → ${to}`,
    catalog: (ids) => `challenge ${ids.length > 1 ? 'scenarios' : 'scenario'} ${ids.join(', ')}`,
  },

  traffic: {
    title: 'Service updates',
    group: 'World shown',
    span: (from, to) => (from === to ? `at ${from}` : `from ${from} to ${to}`),
    since: (from) => `from ${from} on`,
    yes: 'yes',
    parameter: (label, value, when) => `${label}: ${value}, ${when}.`,
    flag: (label, when) => `${label} ${when}.`,
    reference: (value) => `(${value} in the reference world)`,
    // The age at which the crisis shown starts, adjustable from one junction to the next.
    age: 'Crisis starts at',
    years: (age) => `age ${age}`,
    earlier: 'One year earlier',
    later: 'One year later',
    range: (from, to) => `Adjustable from ${from} to ${to}`,
    origin: (age) => `back to age ${age}`,
  },

  // The state shown for a station. "ajar": open in the world shown, closed in another tested world.
  states: { open: 'Station open', ajar: 'Station open here, closed in another tested world',
            closed: 'Station closed', unknown: 'Station not computed' },
  doorState: { ouverte: 'open', fermee: 'closed' },
  // The nature of an assumption, as the engine gives it (engine/assumptions.py).
  kinds: { observe: 'challenge synthetic data', starter_kit: 'illustrative starter-kit assumption', hypothese: 'team assumption',
           a_verifier: 'Swiss order of magnitude, to be verified', regle: 'simplified team rule' },
  wholeTrip: 'the whole route',
  worldsOpen: (n, total) => (n === total ? `Open in the ${total} tested worlds.`
    : n === 0 ? `Closed in the ${total} tested worlds.` : `Open in ${n} of the ${total} tested worlds.`),

  map: {
    start: 'Departure',
    startWhere: (p) => `age ${p.age}, ${p.city}`,
    counts: (n, total, world) => `${open(n, total)} · ${world}`,
    station: (name, when, state) => `${name}, ${when}: ${state}`,
    gare: (age, branches) => `Junction, age ${age}: ${plural(branches, 'branch', 'branches')}`,
    departure: (age, branches) => `Departure, age ${age}: ${plural(branches, 'line', 'lines')}`,
    lastTransfer: 'last useful transfer',
    seen: 'observed savings',
    tipping: (when) => `Tipping point, ${when}`,
    // The tunnel: the months in which the engine records overdraft financing.
    tunnel: (to, amount) => `Tunnel until ${to} · up to ${amount} to finance`,
    noTunnel: 'No tunnel: the balance never goes into the red.',
    branch: (label) => `Branch: ${label}`,
  },

  card: {
    pick: 'Click a station, or a junction.',
    details: 'Details',
    origin: 'Results computed by the engine, under its assumptions. Not a forecast, not advice.',
    back: 'Back to the route',

    // --- the route
    trip: 'Your route',
    shown: (world) => `In the world shown: ${lower(world)}.`,
    open,
    noFinancing: 'No financing needed: the balance never goes into the red.',
    financing: (n, from, to, amount) => `Financing needed for ${n} months, between ${from} and ${to}, up to ${amount}.`,
    netWorth: (age, amount) => `Net worth at ${age}: ${amount}.`,
    worlds: (n) => `In the ${n} tested worlds`,
    columns: ['World', 'Stations open', 'Peak financing', 'Net worth at the end'],

    // --- a station
    stateAt: (state, when) => `${state} · ${when}`,
    whyTitle: 'Where this route stops holding it',
    tipping: (when) => `Tipping point: ${when}. That is when this route stops holding this station.`,
    noReturn: (age) => `Point of no return: the junction at ${age}. From there on, no computed branch opens it any more.`,
    noReturnAtStart: 'No computed branch opens it, even at the departure.',
    lastTransfer: (where, label) => `Last useful transfer: ${where}, by the branch “${label}”.`,
    atDeparture: (age) => `the departure, at ${age}`,
    atGare: (age) => `the junction at ${age}`,
    seeGare: 'See this junction',
    signpost: 'Signpost',
    holds: 'This route holds this station in the world shown.',
    source: (kind, source) => `Origin of the goal: ${kind}. ${source}`,
    margin: (value, required) => `${value} for ${required} required`,
    here: (margin) => `In the world shown: ${margin}.`,

    // --- a junction
    gare: (age) => `Junction · age ${age}`,
    departure: (age) => `Departure · age ${age}`,
    flexibility: (robust, some, total) => `From here, ${plural(robust, 'station', 'stations')} out of ${total} `
      + `${robust === 1 ? 'stays' : 'stay'} reachable whatever happens in the tested worlds`
      + (some ? `; ${some} more only in some worlds.` : '.'),
    horizon: (text) => `Counted ${text}.`,
    robust: (names) => `Whatever happens: ${list(names)}.`,
    possible: (names) => `In some worlds only: ${list(names)}.`,
    lost: (names) => `No longer reachable from here: ${list(names)}.`,
    matters: 'This junction matters: depending on the branch, the stations open are not the same.',
    quiet: 'At this junction, changing branch changes no station in the tested worlds. The amounts do change.',
    alone: 'No other branch is computed at this junction for now.',
    state: (world, cash, debt, worth) => `At this junction, in the world shown (${lower(world)}): ${cash} on the account, ${debt} of debt, net worth of ${worth}.`,
    // Where the tested crises stand when the route reaches this junction.
    shocks: (age, after, before) => [
      after.length ? `At ${age}, ${after.length > 1 ? 'these tested crises have' : 'this tested crisis has'} already happened: ${list(after.map(lower))}.` : '',
      before.length ? `${after.length ? 'Not yet' : `At ${age}, no tested crisis has happened yet. Still to come`}: ${list(before.map(lower))}.` : '',
    ].filter(Boolean).join(' '),
    // The twin that learns: Alexia says what she really has set aside at this junction.
    observe: {
      ask: 'How much do you really have set aside?',
      hint: 'Cash + investments − debts, at this age.',
      unit: 'CHF',
      apply: 'Use',
      forget: 'Back to the simulated savings',
      simulated: (world, amount) => `The twin simulates ${amount} set aside at this junction, in the world shown (${lower(world)}).`,
      instead: (world, amount) => `The twin simulated ${amount} in the world shown (${lower(world)}). The branches below start again from your value, in every tested world.`,
      noSignal: 'This route has no signpost at this junction: your value changes what follows, with no threshold to compare it with.',
      elsewhere: (age, amount) => `Observed savings at ${age}: ${amount}. Entering a value here replaces it.`,
      trip: (age, amount) => `Observed savings at ${age}: ${amount}. From that age on, the map follows this value, not the simulated savings.`,
    },
    branches: 'The branches',
    current: 'your current route',
    take: 'Take this branch',
    summary: (stations, financing, worth) => `${stations} · peak financing ${financing} · net worth at the end ${worth}`,
    more: (label, n) => `Clairvoyant benchmark: knowing this world in advance, the branch “${label}” would keep ${plural(n, 'more station', 'more stations')} than your current route. Nobody knows it in advance.`,
    barred: 'Branch closed',
    partial: (ages) => `Branches computed so far: ${list(ages)}. The other junctions come with the rest of the engine.`,
    partialAt: { departure: 'at the departure', gare: (age) => `at ${age}` },
  },

  // Fixed plan against policy. Neither is ranked: the panel shows what each one keeps.
  plan: {
    button: 'Fixed plan or policy',
    title: 'Fixed plan or policy',
    rule: 'The rule.',
    fixed: 'Fixed plan',
    adaptive: 'Policy',
    kept: 'Goals kept',
    borrowing: 'Peak borrowing',
    worth: 'Net worth at the end',
    count: (n, total) => `${n} out of ${total}`,
    observed: (world, age, amount, applies) => `In the world shown (${lower(world)}), at ${age}: ${amount} set aside. `
      + (applies ? 'The rule applies.' : 'The rule does not apply: the two plans are the same.'),
    seen: (age, amount, applies) => `You said you have ${amount} set aside at ${age}: the rule reads this value, in every tested world. `
      + (applies ? 'The rule applies.' : 'The rule does not apply: the two plans are the same.'),
    since: (age, amount) => `Both plans follow the route as lived since the observed savings at ${age} (${amount}).`,
    tooLate: (age) => `The observed savings at ${age} come after the junction of the rule: the rule reads the simulated savings.`,
    reopened: (names) => `The rule keeps ${list(names)}, which the fixed plan loses.`,
    lost: (names) => `It loses ${list(names)}, which the fixed plan keeps.`,
    avoided: (amount) => `Borrowing avoided: ${amount}.`,
    summary: (door, adaptive, fixed, worlds) => `The rule keeps “${door}” in ${plural(adaptive, 'world', 'worlds')} out of ${worlds}, the fixed plan in ${fixed}.`,
    columns: ['World', 'Fixed', 'Policy', 'Borrowing avoided'],
    same: 'same plans',
    onlyState: 'The decision only looks at the state reached at the junction, never at what follows.',
    none: (message) => `No policy for this route. ${message}`,
  },

  // Three bands for a result, with no stated frequency: the worst tested world, the reference world, a cautious world.
  bands: {
    title: 'Three bands: three worlds, not frequencies',
    pire: 'Worst tested world',
    central: 'Central',
    prudent: 'Cautious',
    columns: ['', 'Stations open', 'Peak financing', 'Net worth at the end'],
    count: (n, total) => `${n} out of ${total}`,
    everywhere: 'every tested world',
    note: (points) => `Worst tested world: the least favourable of the tested worlds, figure by figure. Central: the reference world. `
      + `Cautious: the reference world, with the return on investments lowered by ${points} per year. No band is a promise.`,
    points: (n, written) => `${written} ${n === 1 ? 'point' : 'points'}`,
    station: (worst, where, central, prudent, required) => `Worst tested world: ${worst} (${where}) · central: ${central} · cautious: ${prudent}. Required: ${required}.`,
    stationState: (worst, where, central, prudent) => `Worst tested world: ${worst} (${where}) · central: ${central} · cautious: ${prudent}.`,
    worth: 'Net worth at the end',
    sheetNote: 'For a policy, the worst tested world can be the world with no shock: there it follows the plan, master\'s included, and the six goals do not measure what the degree is worth.',
  },

  // Policies, not plans: the value table. A policy reads the present state and decides; it never reads what follows.
  policies: {
    button: 'Policies',
    title: 'Policies, not plans',
    close: 'Close',
    intro: 'A fixed plan looks at nothing. A policy is a rule: when its date comes, it looks at what you have set aside, then decides. '
      + 'It never reads what follows. This table shows what each choice buys in resilience, and what it costs.',
    target: (name, amount, age) => `Goal aimed at by the three policies: “${name}”, ${amount} at ${age} (Alexia's goal, challenge synthetic data).`,
    noShock: 'No shock',
    world: (name, age, months, gravity) => `${name} at ${age}` + (months ? ` (${months} months)` : '') + (gravity !== 100 ? `, severity ${gravity}%` : ''),
    long: 'long shock',
    kept: (n, total) => `${plural(n, 'goal', 'goals')} out of ${total}`,
    fate: {
      termine: (age) => `Master's finished at ${age}`,
      termine_en_travaillant: (age) => `Master's finished at ${age}, while working`,
      arrete: (age) => `Master's stopped at ${age}`,
      pas_commence: () => 'Master\'s not started',
    },
    borrowing: 'Peak borrowing',
    regret: 'Regret',
    applies: 'the rule applies',
    follows: 'follows the plan',
    fixedRule: 'The route, with nothing changed. It reads nothing.',
    how: {
      securite: 'Decides before starting the master\'s.',
      equilibre: 'Starts the master\'s, and stops it if savings fall short.',
      ambition: 'Starts the master\'s, and finishes it while working if savings fall short.',
    },
    seer: 'Clairvoyant benchmark',
    seerHow: 'What one would have chosen knowing the world in advance.',
    regretIs: 'Regret: what is missing for the goal aimed at, when one of the four options would have held it. It is the price of not knowing. It is zero when the goal holds.',
    seerIs: 'The clairvoyant benchmark is not a possible action: nobody knows the world in advance. It is a yardstick, not a course to follow.',
    limit: 'The value of a degree beyond the age of 30 is not measured by the six goals; comparing at 30 penalises the master\'s.',
    // Alexia, and fragile Alexia: the same policy, two starting states.
    cases: 'Alexia or fragile Alexia',
    caseOf: (amount) => `Alexia · ${amount} set aside at 20`,
    fragileCase: (amount) => `Fragile Alexia · ${amount} set aside at 20`,
    caseShort: (amount) => `Alexia, ${amount} at the start`,
    fragileShort: (amount) => `Fragile Alexia, ${amount} at the start`,
    sameRules: 'Same rules, same thresholds for both: a policy reads the state, and it is the state that changes.',
    gapTitle: 'The gap between each policy and the fixed plan, for both Alexias',
    gapIntro: 'What the policy changes compared with the fixed plan, world by world: more goals kept, more or less peak borrowing.',
    doorsMore: (n) => (n === 0 ? 'As many goals' : `${n > 0 ? '+' : '−'}${plural(Math.abs(n), 'goal', 'goals')}`),
    borrowingMore: (difference, written) => (difference === 0 ? 'Same peak borrowing' : `Peak borrowing: ${difference > 0 ? '+' : ''}${written}`),
    saved: (door) => `“${door}” saved`,
    none: 'no threshold',
    choiceTitle: 'How each threshold is chosen',
    choice: 'In this order: the most worlds in which the goal holds; then the smallest regret in the hardest world, then in the next one; '
      + 'when tied, the rule that leaves the plan in the fewest worlds. One threshold per rule, taken in the middle of the zone that works, not at its edge.',
    zone: (name, threshold, low, high) => `${name}: threshold of ${threshold}, in the middle of the zone that works. Lower edge, ${low}: the tipping point `
      + `computed by the engine, below which the plan loses the goal even with no shock. Upper edge, ${high}: the lowest savings of a world in which the plan holds it.`,
    zoneOpen: (name, threshold, low) => `${name}: threshold of ${threshold}. In every tested world the savings are below it: the zone has no upper edge, the threshold is its lower edge (${low}).`,
    noZone: (name) => `${name}: no threshold serves the goal in the tested worlds; the rule does not apply.`,
    leftOutTitle: 'One world left out',
    leftOut: 'The threshold is recomputed without this world, then tried on it: the threshold found, and whether the goal aimed at holds there.',
    leftOutCell: (threshold, holds) => `${threshold} · ${holds ? 'holds' : 'lost'}`,
    variantsTitle: 'Variants of the worlds: the test set',
    variants: 'The same crises, one year earlier, one year later, milder, stronger. The thresholds do not change: goals kept, and the goal aimed at.',
    blind: 'A shock that comes after the last decision date does not show in the savings: no rule on savings can see it coming.',
    variantCell: (n, total, holds) => `${n} out of ${total} · ${holds ? 'holds' : 'lost'}`,
    drawnTitle: 'Randomly drawn variants',
    drawn: (n, seed, from, to, low, high) => `${n} variants drawn with a fixed seed (${seed}): one crisis of the table, at an age between ${from} and ${to}, `
      + `with a severity between ${low} and ${high}%. They are used to try the policies, never a fixed plan. They are counts, not expected frequencies.`,
    drawnKept: (name, door, kept, n, applied) => `${name}: “${door}” holds in ${kept} of the ${n} drawn variants; the rule applies in ${applied}.`,
    drawnSeer: (kept, n) => `Clairvoyant benchmark: in ${kept} of the ${n}.`,
    refused: (message) => `No policy table for this route. ${message}`,
  },

  // A widespread rule, put to the test by the engine in two states of Alexia.
  folk: {
    button: 'A widespread rule, put to the test',
    title: 'A widespread rule, put to the test',
    noShock: 'No shock',
    world: (name, age) => `${name} at ${age}`,
    how: (age, months, window) => `The test: at ${age}, exactly ${months} months of current expenses on the account, and nothing else. `
      + `The rule holds if Alexia does not go into the red during the ${window} months that follow. Two states at the same age, the same worlds.`,
    cushion: (expenses, months, cushion) => `Current expenses: ${expenses} per month. Cushion of ${months} months: ${cushion}.`,
    kept: (n, total) => `The rule holds in ${n} of the ${total} tested worlds.`,
    needed: (amount, months, less) => (less ? `${amount} set aside would be enough, that is ${months} months of expenses.`
      : `${amount} set aside would be needed, that is ${months} months of expenses.`),
    never: 'No tested cushion is enough.',
    holds: 'Holds',
    breaks: 'In the red',
    red: (when, amount) => `from ${when}, up to ${amount} to finance`,
    why: 'A fixed rule does not read the state. Employed, Alexia has a salary that covers her expenses: the cushion only has a shock to absorb. '
      + 'In a master\'s, her budget runs a deficit every month: the cushion has to pay for the studies themselves. That is what a policy reads, and what a widespread rule ignores.',
    limit: 'The cushion is counted on the account alone, with no investments to sell. The tested worlds are the reference world and each crisis placed at that age.',
    refused: (message) => `No test for this route. ${message}`,
  },

  // The drawer: what proves, and what limits.
  drawer: {
    open: 'Assumptions & evidence',
    title: 'Assumptions & evidence',
    close: 'Close',
    sections: { hypotheses: 'The assumptions', verifications: 'Live checks', registre: 'The ledger of one month', limites: 'The limits' },
    assumptionsHelp: 'Each value carries its nature and its source. Change a value: the whole route is recomputed by the engine.',
    changed: (n) => `${plural(n, 'value changed', 'values changed')}.`,
    modified: (value, unit) => `Value entered by you. Original value: ${value} ${unit}.`,
    reset: 'Back to the original value',
    resetAll: 'Reset everything',
    checksHelp: 'These checks are run now by the engine, on the lines of the scenario.',
    runKit: 'Rerun the equality with the challenge starter kit',
    kitResult: (passed, total, seconds, at) => `${passed} tests passed out of ${total}, in ${seconds} s, at ${at}.`,
    ledgerHelp: (world) => `Every franc of the chosen month, for the route shown, in the world shown (${lower(world)}).`,
    month: (month, age) => `Month ${month} · ${age}`,
    opening: 'Account at the start of the month',
    closing: 'Account at the end of the month',
    debt: 'Debts at the end of the month',
    netWorth: 'Net worth at the end of the month',
    note: (label) => `Note: ${label}`,
    accounts: { cash: 'account', placements: 'investments', pilier2: '2nd pillar', logement: 'home', dette: 'debt' },
    limitsHelp: (source) => `What the model does not do, or does in a simplified way (${source}).`,
  },

  train: {
    go: 'Run the train',
    stop: 'Stop the train',
    again: 'Run the train again',
    how: 'The train stops at open stations, pauses briefly at fragile stations and passes closed stations.',
  },

  legend: {
    open: 'Open in the world shown',
    ajar: 'Open here, closed in another tested world',
    closed: 'Closed in the world shown',
    tunnel: 'Tunnel: financing needed',
    gare: 'Junction',
    last: 'Last useful transfer',
  },
};

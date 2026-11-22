# Couverture du catalogue de 120 scénarios

Généré par `python3 -m engine.catalog`. Chaque scénario couvert est réellement simulé (base et intervention, 120 mois), et ses identités comptables sont vérifiées.

- **98 / 120 scénarios tournent** : 56 modélisés, 42 approximés (approximation écrite).
- **22 non couverts**, chacun avec l'opération manquante.
- Identités comptables : **98 / 98** scénarios sans erreur.
- Familles : 15 hypothèse, 20 monde, 85 décision.

Opérations manquantes : `epargne_bloquee` (2), `friction_liquidite` (1), `menage` (1), `participation` (4), `placements_en_devise` (1), `plafond_de_financement` (1), `portefeuille_2_actifs` (4), `retraite` (8)

Les montants sont des conséquences d'hypothèses illustratives, pas des prévisions.

| ID | Catégorie | Scénario | Famille | Fidélité | Profil | Patrimoine base → intervention (CHF) | Δ | Financement max | Note |
|---|---|---|---|---|---|---|---:|---|---|
| S001 | Education & skills | Full-time master’s | décision | 🟢 modélisé | Alexia | 175'904 → 118'631 | -57'273 | 0 → 41'869 |  |
| S002 | Education & skills | Part-time master’s | décision | 🟢 modélisé | Alexia | 175'904 → 208'671 | +32'766 | 0 → 8'228 | Master en 3 ans à 60 % d'activité ; pas de job étudiant en plus de l'emploi. |
| S003 | Education & skills | Scholarship award | décision | 🟢 modélisé | Alexia | 118'631 → 142'774 | +24'143 | 41'869 → 21'555 |  |
| S004 | Education & skills | Tuition increase | hypothèse | 🟢 modélisé | Alexia | 118'631 → 113'466 | -5'165 | 41'869 → 46'144 | Frais d'études de 10 000 CHF par an au lieu de 8 000. |
| S005 | Education & skills | Internship year | décision | 🟠 approximé | Alexia | 118'631 → 162'324 | +43'693 | 41'869 → 42'461 | Stage traité comme un emploi salarié ordinaire. |
| S006 | Education & skills | Bootcamp reskilling | décision | 🟢 modélisé | Samir | 287'229 → 351'964 | +64'736 | 0 → 0 |  |
| S007 | Education & skills | Doctoral track | décision | 🟠 approximé | Alexia | 175'904 → 388'582 | +212'678 | 0 → 0 | Salaire de doctorant et de docteur supposés. |
| S008 | Education & skills | Study abroad | décision | 🟠 approximé | Alexia | 118'631 → 187'002 | +68'371 | 41'869 → 51'544 | Coût de la vie à l'étranger générique en EUR. |
| S009 | Education & skills | Student loan | décision | 🟠 approximé | Alexia | 118'631 → 119'267 | +636 | 41'869 → 25'844 | Remboursement dès l'emprunt (pas de différé). |
| S010 | Education & skills | Delayed graduation | décision | 🟢 modélisé | Alexia | 118'631 → 135'252 | +16'621 | 41'869 → 65'331 |  |
| S011 | Career & employment | Early job start | décision | 🟢 modélisé | Alexia | 118'631 → 175'904 | +57'273 | 41'869 → 0 |  |
| S012 | Career & employment | Salary negotiation | hypothèse | 🟢 modélisé | Samir | 287'229 → 333'296 | +46'068 | 0 → 0 |  |
| S013 | Career & employment | Promotion | décision | 🟢 modélisé | Samir | 287'229 → 340'029 | +52'801 | 0 → 0 |  |
| S014 | Career & employment | Unemployment gap | monde | 🟢 modélisé | Samir | 287'229 → 278'079 | -9'150 | 0 → 0 | Droit au chômage vérifié par le moteur. |
| S015 | Career & employment | Freelancing | décision | 🟠 approximé | Samir | 287'229 → 292'363 | +5'135 | 0 → 0 | AVS d'indépendant en taux unique. |
| S016 | Career & employment | Career switch | décision | 🟢 modélisé | Samir | 287'229 → 259'508 | -27'721 | 0 → 0 |  |
| S017 | Career & employment | Four-day week | décision | 🟢 modélisé | Samir | 287'229 → 166'881 | -120'347 | 0 → 0 |  |
| S018 | Career & employment | Equity compensation | décision | ⚪ non couvert |  |  |  |  | manque `participation`. Actions de l'employeur : actif non liquide à valeur incertaine. |
| S019 | Career & employment | Contract work | décision | 🟢 modélisé | Samir | 287'229 → 216'610 | -70'618 | 0 → 0 |  |
| S020 | Career & employment | Second income | décision | 🟢 modélisé | Samir | 287'229 → 448'779 | +161'550 | 0 → 0 | Deux employeurs : 2e pilier calculé par emploi. |
| S021 | Relocation & geography | Move to Zurich | décision | 🟠 approximé | Samir | 287'229 → 294'393 | +7'165 | 0 → 0 | Écart de loyer et de salaire supposés ; impôt zurichois non modélisé. |
| S022 | Relocation & geography | Move to Geneva | décision | 🟠 approximé | Samir | 287'229 → 295'986 | +8'757 | 0 → 0 | Écart de loyer et de salaire supposés ; impôt genevois non modélisé. |
| S023 | Relocation & geography | Move to Berlin | décision | 🟠 approximé | Samir | 287'229 → 141'072 | -146'156 | 0 → 0 | Coût de la vie et prélèvements allemands génériques. |
| S024 | Relocation & geography | Move to London | décision | 🟠 approximé | Samir | 287'229 → 350'581 | +63'352 | 0 → 0 | Livre sterling approximée par l'euro. |
| S025 | Relocation & geography | Move to Singapore | décision | 🟠 approximé | Samir | 287'229 → 425'014 | +137'785 | 0 → 0 | Dollar de Singapour approximé par l'euro. |
| S026 | Relocation & geography | Remote work abroad | décision | 🟠 approximé | Samir | 287'229 → 280'249 | -6'979 | 0 → 0 | Frontalier : cotisations suisses, coût de la vie en EUR, impôt à la source non modélisé. |
| S027 | Relocation & geography | Return migration | décision | 🟢 modélisé | Samir | 164'141 → 203'171 | +39'030 | 0 → 0 |  |
| S028 | Relocation & geography | Currency depreciation | monde | 🟢 modélisé | Samir | 280'249 → 245'785 | -34'464 | 0 → 0 | Le franc s'affaiblit : 0,94 → 1,05 CHF/EUR. |
| S029 | Relocation & geography | Dual-currency income | décision | 🟠 approximé | Samir | 287'229 → 278'152 | -9'077 | 0 → 0 | Prélèvements sur la part en EUR en taux unique. |
| S030 | Relocation & geography | High relocation cost | hypothèse | 🟢 modélisé | Samir | 164'141 → 161'641 | -2'500 | 0 → 0 |  |
| S031 | Housing & property | Rent alone | hypothèse | 🟢 modélisé | Samir | 351'304 → 287'229 | -64'076 | 0 → 0 | Base : colocation. |
| S032 | Housing & property | Move in with flatmates | hypothèse | 🟢 modélisé | Samir | 287'229 → 351'304 | +64'076 | 0 → 0 |  |
| S033 | Housing & property | Buy starter home | décision | 🟢 modélisé | Samir | 287'229 → 348'836 | +61'607 | 0 → 0 | Achat dès que possible d'un bien à 350 000 CHF, le maximum que permet le test de capacité. |
| S034 | Housing & property | Higher down payment | décision | 🟢 modélisé | Samir | 348'836 → 332'406 | -16'430 | 0 → 0 | 30 % de fonds propres au lieu de 20 %. |
| S035 | Housing & property | Mortgage rate reset | monde | 🟠 approximé | Samir | 348'836 → 331'849 | -16'987 | 0 → 0 | Renouvellement simulé par une hausse de 1,5 point du taux à partir du mois 60. |
| S036 | Housing & property | Home renovation | décision | 🟠 approximé | Samir | 348'836 → 308'393 | -40'443 | 0 → 0 | La rénovation n'augmente pas la valeur du logement. |
| S037 | Housing & property | Rent increase | hypothèse | 🟠 approximé | Samir | 287'229 → 269'146 | -18'083 | 0 → 0 | Hausse unique de 10 % au lieu d'une hausse annuelle. |
| S038 | Housing & property | Buy later | décision | 🟢 modélisé | Samir | 348'836 → 317'434 | -31'402 | 0 → 0 | Base : achat dès que possible. Intervention : pas avant le mois 72. |
| S039 | Housing & property | Property price decline | monde | 🟢 modélisé | Samir | 348'836 → 292'191 | -56'645 | 0 → 0 | Baisse de 15 % du prix du logement au mois 60. |
| S040 | Housing & property | Unexpected maintenance | décision | 🟢 modélisé | Samir | 348'836 → 323'683 | -25'153 | 0 → 0 |  |
| S041 | Spending & lifestyle | Budget reduction | hypothèse | 🟢 modélisé | Samir | 287'229 → 306'687 | +19'459 | 0 → 0 |  |
| S042 | Spending & lifestyle | Car purchase | décision | 🟢 modélisé | Samir | 287'229 → 213'622 | -73'607 | 0 → 0 |  |
| S043 | Spending & lifestyle | Public transport switch | décision | 🟢 modélisé | Samir | 228'853 → 273'241 | +44'388 | 0 → 0 |  |
| S044 | Spending & lifestyle | Travel sabbatical | décision | 🟠 approximé | Samir | 287'229 → 230'089 | -57'140 | 0 → 0 | Au retour, le salaire repart du niveau d'avant (hausses perdues). |
| S045 | Spending & lifestyle | Subscription audit | décision | 🟢 modélisé | Samir | 267'770 → 282'040 | +14'270 | 0 → 0 |  |
| S046 | Spending & lifestyle | Lifestyle inflation | décision | 🟠 approximé | Samir | 287'229 → 251'239 | -35'989 | 0 → 0 | Hausse du train de vie par paliers, pas indexée sur le salaire. |
| S047 | Spending & lifestyle | Large purchase | décision | 🟢 modélisé | Samir | 287'229 → 281'004 | -6'225 | 0 → 0 |  |
| S048 | Spending & lifestyle | Emergency expense | décision | 🟢 modélisé | Samir | 287'229 → 279'036 | -8'192 | 0 → 0 |  |
| S049 | Spending & lifestyle | Shared household | hypothèse | 🟠 approximé | Samir | 287'229 → 383'735 | +96'507 | 0 → 0 | Partage approximé par un loyer et une vie courante plus bas. |
| S050 | Spending & lifestyle | Energy cost spike | monde | 🟠 approximé | Samir | 287'229 → 285'659 | -1'570 | 0 → 0 | L'énergie double : environ +4 % du budget pendant un an. |
| S051 | Savings & liquidity | Emergency fund target | hypothèse | 🟢 modélisé | Alexia | 186'665 → 183'720 | -2'945 | 0 → 0 | Testé sur Alexia (8 000 CHF) : la réserve ne contraint que si l'épargne de départ est faible. |
| S052 | Savings & liquidity | Automated saving | décision | 🟢 modélisé | Samir | 270'599 → 286'157 | +15'558 | 0 → 0 |  |
| S053 | Savings & liquidity | Savings rate increase | hypothèse | 🟢 modélisé | Samir | 280'577 → 293'880 | +13'304 | 0 → 0 |  |
| S054 | Savings & liquidity | Short-term cash goal | décision | 🟠 approximé | Samir | 287'229 → 272'042 | -15'187 | 0 → 0 | L'objectif est représenté par la dépense ; pas de porte dédiée. |
| S055 | Savings & liquidity | Liquidity lockup | décision | ⚪ non couvert |  |  |  |  | manque `epargne_bloquee`. |
| S056 | Savings & liquidity | Interest on deposits | hypothèse | 🟢 modélisé | Samir | 287'229 → 295'297 | +8'069 | 0 → 0 |  |
| S057 | Savings & liquidity | Unexpected windfall | décision | 🟢 modélisé | Samir | 287'229 → 321'183 | +33'955 | 0 → 0 | Une donation n'est pas un revenu imposable. |
| S058 | Savings & liquidity | Income interruption | monde | 🟢 modélisé | Samir | 287'229 → 281'166 | -6'063 | 0 → 0 |  |
| S059 | Savings & liquidity | Buffer depletion | décision | 🟢 modélisé | Samir | 287'229 → 281'018 | -6'211 | 0 → 0 |  |
| S060 | Savings & liquidity | Multiple goals | décision | 🟠 approximé | Samir | 287'229 → 261'900 | -25'329 | 0 → 0 | Les objectifs sont des dépenses datées. |
| S061 | Investments & allocation | Start investing | décision | 🟢 modélisé | Samir | 270'599 → 286'157 | +15'558 | 0 → 0 |  |
| S062 | Investments & allocation | Higher equity share | décision | ⚪ non couvert |  |  |  |  | manque `portefeuille_2_actifs`. |
| S063 | Investments & allocation | Bond allocation | décision | ⚪ non couvert |  |  |  |  | manque `portefeuille_2_actifs`. |
| S064 | Investments & allocation | Fee reduction | hypothèse | 🟠 approximé | Samir | 284'263 → 287'229 | +2'966 | 0 → 0 | Les frais sont représentés par un rendement net plus bas. |
| S065 | Investments & allocation | Market drawdown | monde | 🟢 modélisé | Samir | 287'229 → 275'895 | -11'334 | 0 → 0 |  |
| S066 | Investments & allocation | Recovery sequence | monde | 🟢 modélisé | Samir | 287'474 → 289'445 | +1'972 | 0 → 0 | Base : reprise immédiate. Pour qui épargne chaque mois, une reprise lente permet d'acheter moins cher. |
| S067 | Investments & allocation | Contribution holiday | décision | 🟢 modélisé | Samir | 286'157 → 282'456 | -3'701 | 0 → 0 |  |
| S068 | Investments & allocation | Rebalancing rule | décision | ⚪ non couvert |  |  |  |  | manque `portefeuille_2_actifs`. |
| S069 | Investments & allocation | Concentrated holding | décision | ⚪ non couvert |  |  |  |  | manque `portefeuille_2_actifs`. |
| S070 | Investments & allocation | Currency exposure | décision | ⚪ non couvert |  |  |  |  | manque `placements_en_devise`. |
| S071 | Debt & credit | Student loan repayment | décision | 🟢 modélisé | Samir | 287'229 → 285'665 | -1'564 | 0 → 0 |  |
| S072 | Debt & credit | Credit-card balance | décision | 🟢 modélisé | Samir | 287'229 → 286'037 | -1'192 | 0 → 0 |  |
| S073 | Debt & credit | Refinance loan | décision | 🟠 approximé | Samir | 280'936 → 282'199 | +1'263 | 0 → 0 | Montant refinancé arrondi au capital restant. |
| S074 | Debt & credit | Early repayment | décision | 🟢 modélisé | Samir | 282'167 → 283'797 | +1'630 | 0 → 0 |  |
| S075 | Debt & credit | Interest rate shock | monde | 🟢 modélisé | Samir | 284'046 → 282'927 | -1'119 | 0 → 0 |  |
| S076 | Debt & credit | Debt consolidation | décision | 🟠 approximé | Samir | 283'497 → 285'326 | +1'829 | 0 → 0 | Taux de consolidation supposé. |
| S077 | Debt & credit | New personal loan | décision | 🟢 modélisé | Samir | 279'004 → 277'888 | -1'115 | 0 → 0 |  |
| S078 | Debt & credit | Missed payment | décision | 🟠 approximé | Samir | 284'690 → 284'519 | -171 | 0 → 0 | Seuls des frais de retard ; pas de pénalité de taux. |
| S079 | Debt & credit | Borrowing cap | décision | ⚪ non couvert |  |  |  |  | manque `plafond_de_financement`. Le moteur finance tout découvert ; un plafond rendrait le plan infaisable. |
| S080 | Debt & credit | Variable amortization | décision | 🟠 approximé | Samir | 282'167 → 280'366 | -1'801 | 0 → 0 | Amortissement flexible représenté par une mensualité plus basse et deux remboursements anticipés. |
| S081 | Family & life events | Partner cohabitation | hypothèse | 🟠 approximé | Samir | 287'229 → 383'735 | +96'507 | 0 → 0 | Vie à deux approximée par des coûts partagés. |
| S082 | Family & life events | Childcare costs | décision | 🟠 approximé | Samir | 287'229 → 170'324 | -116'905 | 0 → 0 | Allocations familiales non modélisées. |
| S083 | Family & life events | Parental leave | décision | 🟠 approximé | Samir | 287'229 → 256'996 | -30'232 | 0 → 0 | Congé indemnisé à 80 % (APG) ; hausses de salaire repartent à zéro. |
| S084 | Family & life events | Family support | décision | 🟢 modélisé | Samir | 287'229 → 222'367 | -64'862 | 0 → 0 |  |
| S085 | Family & life events | Marriage costs | décision | 🟢 modélisé | Samir | 287'229 → 267'036 | -20'192 | 0 → 0 |  |
| S086 | Family & life events | Caregiving break | décision | 🟠 approximé | Samir | 287'229 → 195'434 | -91'794 | 0 → 0 | Hausses de salaire repartent à zéro. |
| S087 | Family & life events | Divorce scenario | décision | ⚪ non couvert |  |  |  |  | manque `menage`. |
| S088 | Family & life events | Dependent education | décision | 🟢 modélisé | Samir | 287'229 → 237'396 | -49'832 | 0 → 0 |  |
| S089 | Family & life events | Insurance claim | décision | 🟠 approximé | Samir | 287'229 → 284'522 | -2'707 | 0 → 0 | Montant de franchise supposé. |
| S090 | Family & life events | Disability interruption | décision | 🟠 approximé | Samir | 287'229 → 245'028 | -42'201 | 0 → 0 | Indemnités de perte de gain à 80 %. |
| S091 | Retirement & pensions | Retire at 60 | décision | ⚪ non couvert |  |  |  |  | manque `retraite`. |
| S092 | Retirement & pensions | Retire at 67 | décision | ⚪ non couvert |  |  |  |  | manque `retraite`. |
| S093 | Retirement & pensions | Pension contribution increase | décision | ⚪ non couvert |  |  |  |  | manque `epargne_bloquee`. |
| S094 | Retirement & pensions | Career gap effect | décision | 🟢 modélisé | Samir | 287'229 → 136'490 | -150'738 | 0 → 22'120 | L'interruption réduit le 2e pilier, visible dans le patrimoine. |
| S095 | Retirement & pensions | Retirement relocation | décision | ⚪ non couvert |  |  |  |  | manque `retraite`. |
| S096 | Retirement & pensions | Inflation in retirement | monde | ⚪ non couvert |  |  |  |  | manque `retraite`. |
| S097 | Retirement & pensions | Withdrawal strategy | décision | ⚪ non couvert |  |  |  |  | manque `retraite`. |
| S098 | Retirement & pensions | Longer lifespan | hypothèse | ⚪ non couvert |  |  |  |  | manque `retraite`. |
| S099 | Retirement & pensions | Pension lump sum | décision | ⚪ non couvert |  |  |  |  | manque `retraite`. |
| S100 | Retirement & pensions | Healthcare costs later | monde | ⚪ non couvert |  |  |  |  | manque `retraite`. |
| S101 | Macroeconomic & systemic shocks | High inflation | monde | 🟠 approximé | Samir | 287'229 → 269'778 | -17'451 | 0 → 0 | Les prix montent de 6 % sans rattrapage des salaires. |
| S102 | Macroeconomic & systemic shocks | Deflation episode | monde | 🟠 approximé | Samir | 287'229 → 295'954 | +8'725 | 0 → 0 | Les prix baissent de 3 % sans baisse des salaires. |
| S103 | Macroeconomic & systemic shocks | Rate hike | monde | 🟢 modélisé | Samir | 284'046 → 282'735 | -1'311 | 0 → 0 |  |
| S104 | Macroeconomic & systemic shocks | Recession | monde | 🟢 modélisé | Samir | 287'229 → 272'863 | -14'366 | 0 → 0 |  |
| S105 | Macroeconomic & systemic shocks | FX volatility | monde | 🟢 modélisé | Samir | 164'141 → 162'113 | -2'028 | 0 → 0 |  |
| S106 | Macroeconomic & systemic shocks | Energy shock | monde | 🟠 approximé | Samir | 287'229 → 285'659 | -1'570 | 0 → 0 | Choc énergétique : environ +4 % du budget pendant un an. |
| S107 | Macroeconomic & systemic shocks | Tax policy change | hypothèse | 🟠 approximé | Samir | 287'229 → 274'758 | -12'470 | 0 → 0 | Sur le barème illustratif. |
| S108 | Macroeconomic & systemic shocks | Housing downturn | monde | 🟢 modélisé | Samir | 348'836 → 267'737 | -81'099 | 0 → 0 | Le prix des logements baisse de 20 % en deux ans. |
| S109 | Macroeconomic & systemic shocks | Market liquidity shock | monde | ⚪ non couvert |  |  |  |  | manque `friction_liquidite`. |
| S110 | Macroeconomic & systemic shocks | Compound crisis | monde | 🟢 modélisé | Samir | 287'229 → 266'711 | -20'517 | 0 → 0 |  |
| S111 | Entrepreneurship & innovation | Start a business | décision | 🟠 approximé | Samir | 287'229 → 401'289 | +114'061 | 0 → 0 | Revenus d'indépendant supposés. |
| S112 | Entrepreneurship & innovation | Side project | décision | 🟢 modélisé | Samir | 287'229 → 344'621 | +57'392 | 0 → 0 |  |
| S113 | Entrepreneurship & innovation | Seed funding | décision | ⚪ non couvert |  |  |  |  | manque `participation`. |
| S114 | Entrepreneurship & innovation | Startup failure | décision | 🟠 approximé | Samir | 401'289 → 179'446 | -221'844 | 0 → 8'166 | Échec au mois 24 : retour au salariat. |
| S115 | Entrepreneurship & innovation | Revenue delay | décision | 🟠 approximé | Samir | 208'768 → 141'312 | -67'456 | 0 → 28'823 | Revenu d'indépendant constant une fois lancé ; le retard est une période sans revenu. |
| S116 | Entrepreneurship & innovation | Hire employee | décision | 🟠 approximé | Samir | 445'682 → 285'332 | -160'350 | 0 → 0 | Charges sociales de l'employeur non modélisées. |
| S117 | Entrepreneurship & innovation | Equity dilution | décision | ⚪ non couvert |  |  |  |  | manque `participation`. |
| S118 | Entrepreneurship & innovation | Founder salary | décision | 🟠 approximé | Samir | 445'682 → 184'683 | -260'999 | 0 → 0 | Le salaire du fondateur est traité comme un revenu d'indépendant ; la valeur de l'entreprise n'est pas modélisée. |
| S119 | Entrepreneurship & innovation | Business loan | décision | 🟠 approximé | Samir | 344'253 → 286'096 | -58'157 | 0 → 0 | Pas de rendement de l'investissement. |
| S120 | Entrepreneurship & innovation | Exit event | décision | ⚪ non couvert |  |  |  |  | manque `participation`. |

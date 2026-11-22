"""Les tables anglaises : ce que le moteur nomme par un libellé fixe (hypothèses, registre, portes, mondes, blocs).

Les clés sont celles du moteur. Les phrases construites à la volée ne sont pas ici : elles sont écrites dans les deux
langues à l'endroit où le moteur les compose (engine/i18n.py, `say`).
"""
from __future__ import annotations

PROFILE = "Data/synthetic-profiles.csv (P00001)"
KIT = "starter-kit/scenario_config.json"
TEAM = "Team's choice"
NET_TO_GROSS = "Derived from the starter kit's net figure: net / (1 − AVS/AI/APG − unemployment insurance)"
TAX_SCALE = "Team's illustrative scale"

UNITS = {
    "CHF/mois": "CHF/month", "EUR/mois": "EUR/month", "CHF/an": "CHF/year", "ans": "years", "mois": "months", "%/an": "%/year",
    "% du brut": "% of gross", "% du revenu": "% of income", "% du salaire coordonné": "% of coordinated salary",
    "% du prix": "% of price", "% du prix/an": "% of price/year", "% du revenu brut": "% of gross income",
    "mois de dépenses": "months of expenses",
}

# clé de l'hypothèse -> (libellé, source)
ASSUMPTIONS = {
    "loyer": ("Rent", PROFILE),
    "job_net_mensuel": ("Student job (net)", PROFILE),
    "vie_courante": ("Living costs while studying (excluding rent and health insurance)",
                     "Data/synthetic-cash-balances.csv (P00001): 2'231 CHF spent per month on average over 24 months "
                     "(net flow of −1'031 CHF for 1'200 CHF of income), minus rent and health insurance, rounded"),
    "depenses_emploi_sans_master": ("Total expenses while employed, without a master's (rent and health insurance included)", f"{KIT}, “Start working”"),
    "depenses_emploi_apres_master": ("Total expenses while employed, after the master's (rent and health insurance included)", f"{KIT}, “Master's degree”"),
    "lamal_jeune": ("Health insurance (LAMal), ages 19–25", "[to be verified] priminfo.admin.ch, canton of Vaud"),
    "lamal_adulte": ("Health insurance (LAMal), from age 26", "[to be verified] priminfo.admin.ch, canton of Vaud"),
    "age_lamal_adulte": ("Age of the adult health-insurance rate", "[to be verified] priminfo.admin.ch"),
    "taxe_semestre": ("Tuition per semester", "Data/scenario-assumptions.csv (AS-P00001-02): 8'000 CHF per year for Alexia, that is 4'000 CHF per semester"),
    "taxe_semestre_universite_publique": ("Alternative: fee of a public university, per semester",
                                          "[to be verified] unil.ch, tuition fees. Not used by default: to try it, give this value to “taxe_semestre”"),
    "salaire_net_sans_master": ("Salary without a master's (net of social contributions)", f"{KIT}, “Start working”"),
    "salaire_net_apres_master": ("Salary after the master's (net of social contributions)", f"{KIT}, “Master's degree”"),
    "salaire_sans_master": ("Salary without a master's (gross)", NET_TO_GROSS),
    "salaire_apres_master": ("Salary after the master's (gross)", NET_TO_GROSS),
    "recherche_emploi_mois": ("Job search after the master's", TEAM),
    "recherche_apres_arret_mois": ("Job search after stopping the master's", TEAM),
    "hausse_salaire_annuelle": ("Yearly salary increase (real)", TEAM),
    "salaire_net_etranger_chf": ("Salary abroad (net, in francs)", f"{KIT}, “Move abroad”"),
    "depenses_etranger_chf": ("Total expenses abroad (in francs)", f"{KIT}, “Move abroad”"),
    "salaire_etranger_eur": ("Salary abroad (gross)",
                             "Derived from the starter kit's net figure: net in francs / initial exchange rate / (1 − taxes and contributions abroad)"),
    "cout_vie_etranger_eur": ("Cost of living abroad (housing and health included)",
                              "Derived from the starter kit's expenses: expenses in francs / initial exchange rate"),
    "taux_global_etranger": ("Taxes + contributions abroad", "Simplified single rate"),
    "cout_demenagement": ("Cost of a move", f"{KIT}, “Move abroad”"),
    "fx_initial": ("Initial exchange rate", "[to be verified] snb.ch, rate of the chosen day"),
    "taux_avs_ai_apg": ("AVS/AI/APG, employee share", "[to be verified] ahv-iv.ch"),
    "taux_ac": ("Unemployment insurance, employee share", "[to be verified] arbeit.swiss"),
    "avs_min_annuel": ("Minimum AVS contribution when not working", "[to be verified] ahv-iv.ch"),
    "taux_avs_independant": ("AVS/AI/APG for the self-employed", "[to be verified] ahv-iv.ch, sliding scale simplified to a single rate"),
    "age_avs_sans_activite": ("Age at which AVS starts when not working", "[to be verified] ahv-iv.ch"),
    "lpp_age_epargne": ("Age at which 2nd-pillar savings start", "[to be verified] admin.ch, LPP"),
    "lpp_seuil_entree": ("2nd-pillar entry threshold", "[to be verified] admin.ch, LPP"),
    "lpp_deduction_coordination": ("2nd-pillar coordination deduction", "[to be verified] admin.ch, LPP"),
    "lpp_taux_total": ("Total 2nd-pillar credit, ages 25–34", "[to be verified] admin.ch, LPP. Half paid by the employer"),
    "impot_seuil": ("Income tax: exempt taxable income", TAX_SCALE),
    "impot_taux_min": ("Income tax: rate above the threshold", TAX_SCALE),
    "impot_pente": ("Income tax: rate increase per 100'000 CHF", TAX_SCALE),
    "impot_taux_max": ("Income tax: maximum rate", TAX_SCALE),
    "taux_indemnite_ch": ("Unemployment benefit in Switzerland", "[to be verified] arbeit.swiss, contribution conditions"),
    "chomage_mois_cotises_min": ("Unemployment: minimum months contributed to be entitled", "[to be verified] arbeit.swiss, contribution period"),
    "chomage_fenetre_mois": ("Unemployment: contribution window", "[to be verified] arbeit.swiss, framework period"),
    "taux_indemnite_etranger": ("Unemployment benefit abroad", TEAM),
    "taux_decouvert": ("Rate of overdraft financing", TEAM),
    "rendement_placements_annuel": ("Return on investments (reference world)", TEAM),
    "taux_interet_cash": ("Interest on the current account", TEAM),
    "part_epargne_placee": ("Share of the month's savings invested automatically", TEAM),
    "reserve_cash_mois": ("Cash reserve kept before investing", TEAM),
    "coussin_montant": ("Emergency savings station: amount to have set aside", "Data/synthetic-goals.csv (G-P00001-01, “Emergency savings”)"),
    "coussin_age": ("Emergency savings station: age of the test", TEAM),
    "etudes_annees": ("Back to study station: years to cover without income", TEAM),
    "etudes_age": ("Back to study station: age of the test", TEAM),
    "reconversion_montant": ("Career change station: amount to have set aside", "Data/synthetic-goals.csv (G-P00001-02, “Career transition”)"),
    "reconversion_age": ("Career change station: age of the test", TEAM),
    "regle_coussin_mois": ("Widespread rule put to the test: months of expenses set aside",
                           "The widespread rule “three months of emergency savings are enough”. It is not a rule of the engine: the engine tests it."),
    "regle_coussin_fenetre_mois": ("Widespread rule: how long the cushion has to last",
                                   "Team's choice: two years without going into the red, the length of a master's."),
    "epargne_depart_fragile": ("Fragile Alexia: starting savings",
                               "Team's choice: the same Alexia, with 2'000 CHF set aside at 20 instead of the 8'000 CHF of her profile."),
    "prudent_ecart_rendement": ("“Cautious” world: lower return on investments, per year",
                                "Team's choice: the reference world, with the return on investments lowered by one point."),
    "chomage_long_mois": ("“Long unemployment” world: length of the job loss",
                          "Team's choice: a single crisis, twice as long as the six months of scenario S014 of the challenge catalogue."),
    "perte_job_etudiant_mois": ("“Student job lost” world: months without the job",
                                "Team's choice, by analogy with the six months of unemployment of scenario S014 of the challenge catalogue. No benefit is counted."),
    "resilience_baisse": ("Resilience station: fall in investments to absorb", TEAM),
    "resilience_mois": ("Resilience station: months of expenses that must remain", TEAM),
    "resilience_age": ("Resilience station: age of the test", TEAM),
    "prix_logement": ("Home deposit station: price of the home", TEAM),
    "fonds_propres_min": ("Home deposit station: minimum own funds", "[to be verified] Swiss Bankers Association guidelines on mortgage lending"),
    "fonds_propres_durs_min": ("Home deposit station: own funds outside the 2nd pillar", "[to be verified] Swiss Bankers Association guidelines on mortgage lending"),
    "taux_theorique": ("Home deposit station: theoretical rate of the affordability test", "[to be verified] practice of Swiss banks"),
    "entretien_logement": ("Home deposit station: maintenance costs", "[to be verified] practice of Swiss banks"),
    "ratio_charges_max": ("Home deposit station: maximum housing costs", "[to be verified] practice of Swiss banks"),
    "amortissement_annees": ("Home deposit station: years to amortise down to 2/3 of the price", "[to be verified] Swiss Bankers Association guidelines"),
    "taux_hypotheque": ("Mortgage rate actually paid", "Team's choice, to compare with current 10-year fixed rates"),
    "frais_achat_logement": ("Purchase costs (transfer duty, notary, land register)", "[to be verified] vd.ch, transfer duty"),
    "valeur_locative_taux": ("Taxable imputed rental value", "[to be verified] vd.ch; federal reform voted in 2025, date of entry into force to be verified"),
    "hausse_prix_logement_annuelle": ("Change in home prices (reference world)", TEAM),
}

# clé de la porte -> (nom, règle). Les règles gardent les mêmes champs que les règles françaises (engine/explore.py).
DOORS = {
    "jamais_rouge": ("Never go into the red", "No overdraft financing over the whole period."),
    "coussin": ("Emergency savings",
                "At {coussin_age:n}, cash + investments − debts reach {coussin_montant:chf} (Alexia's goal in the challenge's synthetic data)."),
    "etudes": ("Going back to study",
               "At {etudes_age:n}, cash + investments − debts cover {etudes_annees:n} years of student life without income: "
               "rent, living costs, health insurance, minimum AVS and tuition."),
    "reconversion": ("Career change",
                     "At {reconversion_age:n}, cash + investments − debts reach {reconversion_montant:chf} (Alexia's goal in the challenge's synthetic data)."),
    "resilience": ("Resilience",
                   "At {resilience_age:n}, after a {resilience_baisse:pct} fall in investments, enough is left to cover "
                   "{resilience_mois:n} months of current expenses."),
    "logement": ("Home deposit",
                 "At the end of the period: own funds of at least {fonds_propres_min:pct} of a {prix_logement:chf} home "
                 "({fonds_propres_durs_min:pct} of it outside the 2nd pillar), theoretical costs under {ratio_charges_max:pct} of gross income."),
}
DOOR_ORIGIN = "Rule of the engine (engine/explore.py)"

# type du monde -> (nom, description)
WORLDS = {
    "reference": ("Reference world", "Nothing exceptional: average return on investments, stable prices, no job loss."),
    "krach": ("Market crash", "Investments fall sharply, within one month."),
    "chomage_6_mois": ("Six months of unemployment", "Job loss for six months, for someone who has a job at that time."),
    "perte_job_etudiant": ("Student job lost", "The student job stops for a few months, with no benefit, for someone studying with a job at that time."),
    "inflation": ("Inflation surge", "Prices rise, and salaries do not catch up."),
    "crise_immobiliere": ("Housing downturn", "Home prices fall for two years."),
    "franc_faible": ("Weaker franc", "The franc weakens against the euro. The opposite shock, of the 2015 kind, is not written in the engine yet."),
    "chomage_long": ("Long unemployment", "Job loss for twelve months, for someone who has a job at that time: a single, long crisis."),
    "prudent": ("Cautious world", "The reference world, with a lower return on investments every year. Neither a crisis nor a forecast."),
}
WORLD_FIELDS = {
    "market_return_monthly": "Return on investments, per month", "inflation_monthly": "Inflation, per month",
    "fx_chf_per_eur": "Euro rate, in francs", "job_lost": "Job lost",
    "cost_index": "Price level (1 in the reference world)", "rate_shift": "Rise in interest rates",
    "house_return_monthly": "Change in home prices, per month", "student_job_lost": "Student job lost",
}

BLOCKS = {"master": "Master's", "master_part_time": "Master's while working", "job": "Job in Lausanne", "job_abroad": "Job in Berlin",
          "recherche": "Job search"}
NOT_YET = {"phd": "a PhD", "internship": "an internship year", "independent": "self-employment", "startup": "starting a company", "pause": "a break"}
REFUSED_CITIES = {"london": "London", "singapore": "Singapore"}

# Le registre : libellé du moteur -> libellé anglais.
LEDGER = {
    "Effet du taux de change sur le cash en EUR": "Exchange-rate effect on cash held in EUR",
    "Intérêts du financement du découvert": "Interest on overdraft financing",
    "Job étudiant perdu : pas de revenu ce mois, et pas d'indemnité de chômage": "Student job lost: no income this month, and no unemployment benefit",
    "Job étudiant (net)": "Student job (net)",
    "Taxe d'études semestrielle": "Tuition for the semester",
    "Pas d'indemnité de chômage : les indépendants ne sont pas assurés": "No unemployment benefit: the self-employed are not insured",
    "Revenu d'indépendant": "Self-employment income",
    "AVS/AI/APG d'indépendant": "AVS/AI/APG, self-employed",
    "Indemnité de chômage": "Unemployment benefit",
    "Salaire brut": "Gross salary",
    "AVS/AI/APG + assurance chômage": "AVS/AI/APG + unemployment insurance",
    "2e pilier, part salarié": "2nd pillar, employee share",
    "2e pilier, versement salarié + employeur": "2nd pillar, employee + employer contribution",
    "Impôts et cotisations locaux": "Local taxes and contributions",
    "Virement vers les placements": "Transfer to investments",
    "Entretien du logement": "Home maintenance",
    "Vie courante": "Living costs",
    "Loyer": "Rent",
    "LAMal (19–25 ans)": "Health insurance, LAMal (ages 19–25)",
    "LAMal (adulte)": "Health insurance, LAMal (adult)",
    "AVS minimale (sans activité lucrative)": "Minimum AVS contribution (not working)",
    "Coût de la vie à l'étranger": "Cost of living abroad",
    "Impôt de l'année précédente (1/12)": "Income tax for the previous year (1/12)",
    "Rendement des placements": "Return on investments",
    "Variation de valeur du logement": "Change in the value of the home",
    "Intérêts sur le compte": "Interest on the account",
    "Conversion CHF → EUR": "Conversion CHF → EUR",
    "Financement du découvert": "Overdraft financing",
    "Remboursement du découvert": "Overdraft repayment",
    "Épargne placée automatiquement": "Savings invested automatically",
    "Vente de placements pour l'apport": "Investments sold for the deposit",
    "Apport en fonds propres": "Own-funds deposit",
    "Retrait du 2e pilier pour le logement": "2nd-pillar withdrawal for the home",
    "Achat du logement": "Home purchase",
    "Hypothèque": "Mortgage",
    "Frais d'achat (droits de mutation, notaire)": "Purchase costs (transfer duty, notary)",
    "Écart entre l'épargne constatée et l'épargne simulée": "Gap between the observed savings and the simulated savings",
    "Coussin mis à l'épreuve, à la place de l'épargne simulée": "Cushion put to the test, in place of the simulated savings",
}
# Les libellés composés : un motif, et sa phrase anglaise. Un groupe peut être lui-même un libellé du registre.
LEDGER_PATTERNS = (
    (r"Intérêts : (.+)", "Interest: {}"),
    (r"Remboursement anticipé : (.+)", "Early repayment: {}"),
    (r"Remboursement : (.+)", "Repayment: {}"),
    (r"Emprunt : (.+)", "Loan: {}"),
    (r"Déménagement \((.+)\)", "Move ({})"),
    (r"Pas d'indemnité de chômage : (\d+) mois cotisés sur (\d+), il en faut (\d+)",
     "No unemployment benefit: {} months contributed out of {}, {} are required"),
    (r"Achat impossible : fonds propres insuffisants \((.+) CHF disponibles ; (.+) CHF nécessaires hors 2e pilier, frais et réserve compris\)",
     "Purchase not possible: own funds too low ({} CHF available; {} CHF needed outside the 2nd pillar, costs and reserve included)"),
    (r"Achat refusé par le test de capacité : charges théoriques (.+) CHF/an ; plafond (.+) CHF/an \(1/3 du revenu brut\)",
     "Purchase refused by the affordability test: theoretical costs of {} CHF/year; ceiling of {} CHF/year (1/3 of gross income)"),
)
PLACES = {"etranger": "abroad", "CH": "Switzerland"}

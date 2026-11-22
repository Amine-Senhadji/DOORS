"""Hypothèses theta : chaque valeur a une nature et une source.

Nature :
  observe    : tiré des données synthétiques du challenge
  hypothese  : choix illustratif de l'équipe, modifiable
  a_verifier : ordre de grandeur réglementaire suisse, À VÉRIFIER sur la source indiquée
  regle      : règle simplifiée, documentée comme telle
  starter_kit : hypothèse illustrative du starter-kit, lue dans starter-kit/scenario_config.json

Ordre de priorité : les données d'Alexia d'abord (Data/), le starter-kit du défi ensuite, un choix de l'équipe en dernier.
"""
from __future__ import annotations

from dataclasses import replace

from engine.contract import Assumption
from engine.i18n import current

A = Assumption
SOURCE_PROFIL = "Data/synthetic-profiles.csv (P00001)"
SOURCE_KIT = "starter-kit/scenario_config.json"
# Cotisations sociales du salarié : ces deux taux servent aussi à retrouver le brut des salaires nets du starter-kit.
TAUX_AVS_AI_APG, TAUX_AC = 0.053, 0.011
# Le starter-kit du défi donne des revenus nets et des dépenses totales par mois.
KIT_NET_SANS_MASTER, KIT_NET_APRES_MASTER = 4200, 4800
KIT_DEPENSES_SANS_MASTER, KIT_DEPENSES_APRES_MASTER = 3000, 3100
KIT_NET_ETRANGER, KIT_DEPENSES_ETRANGER, KIT_DEMENAGEMENT = 3700, 2900, 6500      # « Move abroad », en CHF
# À l'étranger, le moteur compte en euros et prélève un taux unique, impôt compris.
FX_INITIAL, TAUX_GLOBAL_ETRANGER = 0.94, 0.22
# Les données d'Alexia donnent des frais d'études par an ; le moteur les compte par semestre.
FRAIS_ETUDES_ANNUELS = 8000


def brut_depuis_net(net: float) -> float:
    """Le brut dont il reste `net` après AVS/AI/APG et assurance chômage. Impôt et 2e pilier viennent ensuite, par les règles du moteur."""
    return net / (1 - TAUX_AVS_AI_APG - TAUX_AC)


def brut_etranger_eur(net_chf: float) -> float:
    """Le brut en euros dont il reste `net_chf` après le prélèvement unique à l'étranger (impôt et cotisations, retenus à la source)."""
    return net_chf / FX_INITIAL / (1 - TAUX_GLOBAL_ETRANGER)


ASSUMPTIONS: tuple[Assumption, ...] = (
    # --- Profil et vie courante
    A("loyer", "Loyer", 900, "CHF/mois", "observe", SOURCE_PROFIL),
    A("job_net_mensuel", "Job étudiant (net)", 1200, "CHF/mois", "observe", SOURCE_PROFIL),
    A("vie_courante", "Vie courante pendant les études (hors loyer et LAMal)", 950, "CHF/mois", "observe",
      "Data/synthetic-cash-balances.csv (P00001) : 2'231 CHF de dépenses par mois en moyenne sur 24 mois "
      "(flux net de −1'031 CHF pour 1'200 CHF de revenu), moins le loyer et la LAMal, arrondi"),
    A("depenses_emploi_sans_master", "Dépenses totales en emploi, sans master (loyer et LAMal compris)", KIT_DEPENSES_SANS_MASTER,
      "CHF/mois", "starter_kit", f"{SOURCE_KIT}, « Start working »"),
    A("depenses_emploi_apres_master", "Dépenses totales en emploi, après le master (loyer et LAMal compris)", KIT_DEPENSES_APRES_MASTER,
      "CHF/mois", "starter_kit", f"{SOURCE_KIT}, « Master's degree »"),
    A("lamal_jeune", "LAMal 19–25 ans", 380, "CHF/mois", "a_verifier", "[à vérifier] priminfo.admin.ch, canton VD"),
    A("lamal_adulte", "LAMal dès 26 ans", 520, "CHF/mois", "a_verifier", "[à vérifier] priminfo.admin.ch, canton VD"),
    A("age_lamal_adulte", "Âge du tarif LAMal adulte", 26, "ans", "a_verifier", "[à vérifier] priminfo.admin.ch"),
    # --- Études et parcours
    A("taxe_semestre", "Frais d'études par semestre", FRAIS_ETUDES_ANNUELS / 2, "CHF", "observe",
      "Data/scenario-assumptions.csv (AS-P00001-02) : 8'000 CHF par an pour Alexia, soit 4'000 CHF par semestre"),
    A("taxe_semestre_universite_publique", "Alternative : taxe d'une université publique, par semestre", 580, "CHF", "a_verifier",
      "[à vérifier] unil.ch, taxes d'études. Non utilisée par défaut : pour l'essayer, donner cette valeur à « taxe_semestre »"),
    A("salaire_net_sans_master", "Salaire sans master (net de cotisations sociales)", KIT_NET_SANS_MASTER, "CHF/mois",
      "starter_kit", f"{SOURCE_KIT}, « Start working »"),
    A("salaire_net_apres_master", "Salaire après le master (net de cotisations sociales)", KIT_NET_APRES_MASTER, "CHF/mois",
      "starter_kit", f"{SOURCE_KIT}, « Master's degree »"),
    A("salaire_sans_master", "Salaire sans master (brut)", brut_depuis_net(KIT_NET_SANS_MASTER), "CHF/mois", "regle",
      "Dérivé du net du starter-kit : net / (1 − AVS/AI/APG − assurance chômage)"),
    A("salaire_apres_master", "Salaire après le master (brut)", brut_depuis_net(KIT_NET_APRES_MASTER), "CHF/mois", "regle",
      "Dérivé du net du starter-kit : net / (1 − AVS/AI/APG − assurance chômage)"),
    A("recherche_emploi_mois", "Recherche d'emploi après le master", 3, "mois", "hypothese", "Choix de l'équipe"),
    A("recherche_apres_arret_mois", "Recherche d'emploi après un arrêt", 2, "mois", "hypothese", "Choix de l'équipe"),
    A("hausse_salaire_annuelle", "Hausse de salaire annuelle (réelle)", 0.02, "%/an", "hypothese", "Choix de l'équipe"),
    # --- Étranger et change
    A("salaire_net_etranger_chf", "Salaire à l'étranger (net, en francs)", KIT_NET_ETRANGER, "CHF/mois", "starter_kit",
      f"{SOURCE_KIT}, « Move abroad »"),
    A("depenses_etranger_chf", "Dépenses totales à l'étranger (en francs)", KIT_DEPENSES_ETRANGER, "CHF/mois", "starter_kit",
      f"{SOURCE_KIT}, « Move abroad »"),
    A("salaire_etranger_eur", "Salaire à l'étranger (brut)", brut_etranger_eur(KIT_NET_ETRANGER), "EUR/mois", "regle",
      "Dérivé du net du starter-kit : net en francs / taux de change initial / (1 − impôts et cotisations à l'étranger)"),
    A("cout_vie_etranger_eur", "Coût de la vie à l'étranger (logement et santé inclus)", KIT_DEPENSES_ETRANGER / FX_INITIAL, "EUR/mois",
      "regle", "Dérivé des dépenses du starter-kit : dépenses en francs / taux de change initial"),
    A("taux_global_etranger", "Impôts + cotisations à l'étranger", TAUX_GLOBAL_ETRANGER, "% du brut", "regle", "Taux unique simplifié"),
    A("cout_demenagement", "Coût d'un déménagement", KIT_DEMENAGEMENT, "CHF", "starter_kit", f"{SOURCE_KIT}, « Move abroad »"),
    A("fx_initial", "Taux de change initial", FX_INITIAL, "CHF/EUR", "a_verifier", "[à vérifier] snb.ch, cours du jour choisi"),
    # --- Cotisations sociales suisses (part salarié)
    A("taux_avs_ai_apg", "AVS/AI/APG, part salarié", TAUX_AVS_AI_APG, "% du brut", "a_verifier", "[à vérifier] ahv-iv.ch"),
    A("taux_ac", "Assurance chômage, part salarié", TAUX_AC, "% du brut", "a_verifier", "[à vérifier] arbeit.swiss"),
    A("avs_min_annuel", "AVS minimale sans activité lucrative", 530, "CHF/an", "a_verifier", "[à vérifier] ahv-iv.ch"),
    A("taux_avs_independant", "AVS/AI/APG des indépendants", 0.10, "% du revenu", "a_verifier", "[à vérifier] ahv-iv.ch, barème dégressif simplifié en taux unique"),
    A("age_avs_sans_activite", "Âge de début de l'AVS sans activité", 21, "ans", "a_verifier", "[à vérifier] ahv-iv.ch"),
    # --- 2e pilier (LPP), simplifié
    A("lpp_age_epargne", "Âge de début de l'épargne LPP", 25, "ans", "a_verifier", "[à vérifier] admin.ch, LPP"),
    A("lpp_seuil_entree", "Seuil d'entrée LPP", 22050, "CHF/an", "a_verifier", "[à vérifier] admin.ch, LPP"),
    A("lpp_deduction_coordination", "Déduction de coordination LPP", 25725, "CHF/an", "a_verifier", "[à vérifier] admin.ch, LPP"),
    A("lpp_taux_total", "Bonification LPP totale 25–34 ans", 0.07, "% du salaire coordonné", "a_verifier", "[à vérifier] admin.ch, LPP. Moitié employeur"),
    # --- Impôt sur le revenu : barème ILLUSTRATIF, pas le barème vaudois
    A("impot_seuil", "Impôt : revenu imposable exonéré", 18000, "CHF/an", "regle", "Barème illustratif de l'équipe"),
    A("impot_taux_min", "Impôt : taux au-dessus du seuil", 0.03, "%", "regle", "Barème illustratif de l'équipe"),
    A("impot_pente", "Impôt : hausse du taux par 100'000 CHF", 0.15, "%", "regle", "Barème illustratif de l'équipe"),
    A("impot_taux_max", "Impôt : taux maximum", 0.22, "%", "regle", "Barème illustratif de l'équipe"),
    # --- Chômage, financement, placements
    A("taux_indemnite_ch", "Indemnité chômage en Suisse", 0.70, "% du brut", "a_verifier", "[à vérifier] arbeit.swiss, conditions de cotisation"),
    A("chomage_mois_cotises_min", "Chômage : mois cotisés minimum pour avoir droit", 12, "mois", "a_verifier", "[à vérifier] arbeit.swiss, période de cotisation"),
    A("chomage_fenetre_mois", "Chômage : fenêtre de cotisation", 24, "mois", "a_verifier", "[à vérifier] arbeit.swiss, délai-cadre"),
    A("taux_indemnite_etranger", "Indemnité chômage à l'étranger", 0.40, "% du brut", "hypothese", "Choix de l'équipe"),
    A("taux_decouvert", "Taux du financement d'un découvert", 0.05, "%/an", "hypothese", "Choix de l'équipe"),
    A("rendement_placements_annuel", "Rendement des placements (monde de référence)", 0.03, "%/an", "hypothese", "Choix de l'équipe"),
    A("taux_interet_cash", "Intérêt sur le compte courant", 0.0, "%/an", "hypothese", "Choix de l'équipe"),
    A("part_epargne_placee", "Part de l'épargne du mois placée automatiquement", 0.5, "%", "hypothese", "Choix de l'équipe"),
    A("reserve_cash_mois", "Réserve gardée en cash avant de placer", 3, "mois de dépenses", "hypothese", "Choix de l'équipe"),
    # --- Portes (objectifs de vie)
    A("coussin_montant", "Porte épargne de précaution : montant à avoir de côté", 12800, "CHF", "observe",
      "Data/synthetic-goals.csv (G-P00001-01, « Emergency savings »)"),
    A("coussin_age", "Porte épargne de précaution : âge du test", 25, "ans", "hypothese", "Choix de l'équipe"),
    A("etudes_annees", "Porte reprendre des études : années à couvrir sans revenu", 2, "ans", "hypothese", "Choix de l'équipe"),
    A("etudes_age", "Porte reprendre des études : âge du test", 27, "ans", "hypothese", "Choix de l'équipe"),
    A("reconversion_montant", "Porte reconversion : montant à avoir de côté", 39365.95, "CHF", "observe",
      "Data/synthetic-goals.csv (G-P00001-02, « Career transition »)"),
    A("reconversion_age", "Porte reconversion : âge du test", 28, "ans", "hypothese", "Choix de l'équipe"),
    A("regle_coussin_mois", "Règle répandue mise à l'épreuve : mois de dépenses de côté", 3, "mois", "hypothese",
      "La règle répandue « trois mois d'épargne de précaution suffisent ». Ce n'est pas une règle du moteur : il la teste."),
    A("regle_coussin_fenetre_mois", "Règle répandue : durée pendant laquelle le coussin doit tenir", 24, "mois", "hypothese",
      "Choix de l'équipe : deux ans sans passer dans le rouge, la durée d'un master."),
    A("epargne_depart_fragile", "Alexia fragile : épargne de départ", 2000, "CHF", "hypothese",
      "Choix de l'équipe : la même Alexia, avec 2'000 CHF de côté à 20 ans au lieu des 8'000 CHF de son profil."),
    A("prudent_ecart_rendement", "Monde « prudent » : rendement des placements en moins, par an", 0.01, "%/an", "hypothese",
      "Choix de l'équipe : le monde de référence, avec un rendement des placements diminué d'un point."),
    A("chomage_long_mois", "Monde « chômage long » : durée de la perte d'emploi", 12, "mois", "hypothese",
      "Choix de l'équipe : une seule crise, deux fois plus longue que les six mois du scénario S014 du catalogue du défi."),
    A("perte_job_etudiant_mois", "Monde « perte du job étudiant » : durée sans job", 6, "mois", "hypothese",
      "Choix de l'équipe, par analogie avec les six mois de chômage du scénario S014 du catalogue du défi. Aucune indemnité n'est comptée."),
    A("resilience_baisse", "Porte résilience : baisse des placements à encaisser", 0.30, "%", "hypothese", "Choix de l'équipe"),
    A("resilience_mois", "Porte résilience : mois de dépenses qui doivent rester", 6, "mois", "hypothese", "Choix de l'équipe"),
    A("resilience_age", "Porte résilience : âge du test", 29, "ans", "hypothese", "Choix de l'équipe"),
    A("prix_logement", "Porte logement : prix du bien", 500000, "CHF", "hypothese", "Choix de l'équipe"),
    A("fonds_propres_min", "Porte logement : fonds propres minimum", 0.20, "% du prix", "a_verifier", "[à vérifier] directives ASB sur le financement hypothécaire"),
    A("fonds_propres_durs_min", "Porte logement : fonds propres hors 2e pilier", 0.10, "% du prix", "a_verifier", "[à vérifier] directives ASB sur le financement hypothécaire"),
    A("taux_theorique", "Porte logement : taux théorique du test de capacité", 0.05, "%/an", "a_verifier", "[à vérifier] pratique des banques suisses"),
    A("entretien_logement", "Porte logement : frais d'entretien", 0.01, "% du prix/an", "a_verifier", "[à vérifier] pratique des banques suisses"),
    A("ratio_charges_max", "Porte logement : charges maximum", 1 / 3, "% du revenu brut", "a_verifier", "[à vérifier] pratique des banques suisses"),
    A("amortissement_annees", "Porte logement : années pour amortir jusqu'à 2/3 du prix", 15, "ans", "a_verifier", "[à vérifier] directives ASB"),
    # --- Propriété du logement
    A("taux_hypotheque", "Taux hypothécaire réel payé", 0.02, "%/an", "hypothese", "Choix de l'équipe, à comparer aux taux fixes 10 ans du moment"),
    A("frais_achat_logement", "Frais d'achat (droits de mutation, notaire, registre)", 0.04, "% du prix", "a_verifier", "[à vérifier] vd.ch, droits de mutation"),
    A("valeur_locative_taux", "Valeur locative imposable", 0.035, "% du prix/an", "a_verifier", "[à vérifier] vd.ch ; réforme fédérale votée en 2025, entrée en vigueur à vérifier"),
    A("hausse_prix_logement_annuelle", "Évolution du prix des logements (monde de référence)", 0.01, "%/an", "hypothese", "Choix de l'équipe"),
)


def defaults() -> dict[str, float]:
    return {a.key: float(a.value) for a in ASSUMPTIONS}


def localized() -> tuple[Assumption, ...]:
    """Les hypothèses avec leur libellé, leur unité et leur source dans la langue courante. Les valeurs sont les mêmes."""
    if current() == "fr":
        return ASSUMPTIONS
    from engine.english import ASSUMPTIONS as english, UNITS
    return tuple(replace(a, label=english[a.key][0], unit=UNITS.get(a.unit, a.unit), source=english[a.key][1]) for a in ASSUMPTIONS)


def by_key() -> dict[str, Assumption]:
    return {a.key: a for a in localized()}

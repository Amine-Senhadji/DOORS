"""Les 120 scénarios du catalogue (Data/scenario-catalog.csv), encodés avec le vocabulaire du moteur.

Chaque scénario appartient à une famille :
  A  changer une hypothèse   (theta)   même ligne, hypothèses différentes
  B  changer le monde        (w_t)     même ligne, monde différent
  C  prendre une décision    (a_t)     ligne de base vs ligne d'intervention

Et a un niveau de fidélité :
  modelise     les règles financières utilisées existent et sont testées
  approxime    le scénario tourne, avec une approximation écrite dans `note`
  non_couvert  il manque une opération ; `missing` dit laquelle

Rapport :  python3 -m engine.catalog   ->   reports/coverage.md et reports/coverage.json
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from engine.checks import _identities
from engine.contract import Line, Operation, Profile, World
from engine.simulate import load_scenario, materialize, reference_world, run_ops, theta_for
from engine.transition import monthly_rate

ROOT = Path(__file__).resolve().parents[1]
H = 120
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
SAMIR = Profile("P01010", "Samir", 29, "Lausanne", "VD", 24033.33, 4643.03, 1393.94)
PROFILES = {"etu": ALEXIA.profile, "sal": SAMIR}
# Samir : loyer observé ; brut estimé depuis le net observé (4 643 / ~0,91), hypothèse de l'équipe.
THETA = {"etu": {}, "sal": {"loyer": 1393.94, "salaire_sans_master": 5100}}


# ------------------------------------------------------------------ opérations (vocabulaire)
def W(g, s=0, e=H, **kw): return Operation("travailler", s, e, {"salaire_brut_mensuel": g, **kw})
def S(s=0, e=24, job="$job_net_mensuel"): return Operation("etudier", s, e, {"job_net_mensuel": job, "taxe_semestre": "$taxe_semestre"})
def J(s, e): return Operation("chercher_emploi", s, e)
def PZ(s, e): return Operation("pause", s, e)
def D(lieu, cout, s): return Operation("demenager", s, s + 1, {"lieu": lieu, "cout_chf": cout})
def E(lib, m, t, mens, s, var=False): return Operation("emprunter", s, s + 1, {"libelle": lib, "montant": m, "taux_annuel": t, "mensualite": mens, "taux_variable": var})
def R(m, s): return Operation("rembourser", s, s + 1, {"montant": m})
def I(m, s=0, e=H): return Operation("investir", s, e, {"montant_mensuel": m})
def DR(lib, m, s=0, e=H): return Operation("depense_recurrente", s, e, {"libelle": lib, "montant": m})
def DP(lib, m, s): return Operation("depense_ponctuelle", s, s + 1, {"libelle": lib, "montant": m})
def RP(lib, m, s): return Operation("revenu_ponctuel", s, s + 1, {"libelle": lib, "montant": m})
def RR(lib, m, s=0, e=H, imposable=True): return Operation("revenu_recurrent", s, e, {"libelle": lib, "montant": m, "imposable": imposable})
def BUY(prix, s=0, e=H, **kw): return Operation("acheter_logement", s, e, {"prix": prix, **kw})
IND = {"statut": "independant"}

# Les deux lignes d'Alexia, comme dans engine/scenarios/alexia.json : en emploi, les dépenses totales du starter-kit.
ETU_MASTER = [S(0, 24), J(24, 27), W("$salaire_apres_master", 27, depenses_mensuelles="$depenses_emploi_apres_master")]
ETU_WORK = [W("$salaire_sans_master", depenses_mensuelles="$depenses_emploi_sans_master")]
SAL = [W("$salaire_sans_master")]
ABROAD = [D("etranger", "$cout_demenagement", 0), W("$salaire_etranger_eur", devise="EUR")]
CROSS_BORDER = [D("etranger", 2000, 0), W("$salaire_sans_master")]
VAR_LOAN = SAL + [E("Prêt à taux variable", 30000, 0.03, 450, 0, var=True)]
START_UP = [W(3000, 0, 24, **IND), DP("Lancement de l'entreprise", 15000, 0), W(8000, 24, H, **IND)]
# Samir peut acheter au plus environ 350 000 CHF (test de capacité), dès qu'il a les fonds propres.
OWNER = SAL + [BUY(350000)]


# ------------------------------------------------------------------------- mondes (w_t)
Mod = Callable[[int, World, dict], World]
def job(s, n) -> Mod: return lambda t, w, th: replace(w, job_lost=True) if s <= t < s + n else w
def cautious() -> Mod:          # le monde « prudent » de l'équipe : la référence, avec un rendement des placements plus bas
    return lambda t, w, th: replace(w, market_return_monthly=monthly_rate(th["rendement_placements_annuel"] - th["prudent_ecart_rendement"]))
def job_long(s) -> Mod:         # le choc long de l'équipe : une seule perte d'emploi, dont la durée est une hypothèse affichée
    return lambda t, w, th: replace(w, job_lost=True) if s <= t < s + round(th["chomage_long_mois"]) else w
def student_job(s) -> Mod:      # crise de l'équipe, absente du catalogue du défi ; sa durée est une hypothèse affichée
    return lambda t, w, th: replace(w, student_job_lost=True) if s <= t < s + round(th["perte_job_etudiant_mois"]) else w
def crash(m, drop) -> Mod: return lambda t, w, th: replace(w, market_return_monthly=-drop) if t == m else w
def returns(s, e, r) -> Mod: return lambda t, w, th: replace(w, market_return_monthly=r) if s <= t < e else w
def rate_from(s, shift) -> Mod: return lambda t, w, th: replace(w, rate_shift=shift) if t >= s else w
def cost_window(s, e, level) -> Mod: return lambda t, w, th: replace(w, cost_index=level) if s <= t < e else w


def house(s, e, r) -> Mod: return lambda t, w, th: replace(w, house_return_monthly=r) if s <= t < e else w


def cost_ramp(s, e, level) -> Mod:
    def f(t, w, th):
        if t < s:
            return w
        k = min(1.0, (t - s) / max(1, e - s))
        return replace(w, cost_index=1 + (level - 1) * k)
    return f


def fx_ramp(s, e, v1) -> Mod:
    def f(t, w, th):
        if t < s:
            return w
        k = min(1.0, (t - s) / max(1, e - s))
        return replace(w, fx_chf_per_eur=th["fx_initial"] + (v1 - th["fx_initial"]) * k)
    return f


def fx_wave(amp, period) -> Mod:
    return lambda t, w, th: replace(w, fx_chf_per_eur=th["fx_initial"] + amp * math.sin(2 * math.pi * t / period))


def build_world(th: dict, mods: tuple[Mod, ...]) -> list[World]:
    out = []
    for t, w in enumerate(reference_world(th, H)):
        for mod in mods:
            w = mod(t, w, th)
        out.append(w)
    return out


# ------------------------------------------------------------------------ spécification
@dataclass(frozen=True)
class Spec:
    id: str
    family: str                       # A, B ou C
    fidelity: str                     # modelise, approxime, non_couvert
    profile: str = "sal"
    base: tuple = ()
    intervention: tuple = ()
    theta_base: dict = field(default_factory=dict)
    theta_int: dict = field(default_factory=dict)
    world_base: tuple = ()
    world_int: tuple = ()
    note: str = ""
    missing: str = ""


def C(id, fid, base, inter, note="", prof="sal", tb=None, ti=None):
    return Spec(id, "C", fid, prof, tuple(base), tuple(inter), tb or {}, ti if ti is not None else (tb or {}), note=note)


def A(id, fid, line, tb, ti, note="", prof="sal"):
    return Spec(id, "A", fid, prof, tuple(line), tuple(line), tb, ti, note=note)


def B(id, fid, line, wi, note="", prof="sal", wb=(), th=None):
    return Spec(id, "B", fid, prof, tuple(line), tuple(line), th or {}, th or {}, tuple(wb), tuple(wi), note=note)


def N(id, fam, missing, note=""):
    return Spec(id, fam, "non_couvert", missing=missing, note=note)


SPECS: tuple[Spec, ...] = (
    # --- Education & skills
    C("S001", "modelise", ETU_WORK, ETU_MASTER, prof="etu"),
    C("S002", "modelise", ETU_WORK, [S(0, 36, job=0), W("$salaire_sans_master", 0, 36, taux_activite=0.6),
                                     W("$salaire_apres_master", 36)],
      "Master en 3 ans à 60 % d'activité ; pas de job étudiant en plus de l'emploi.", prof="etu"),
    C("S003", "modelise", ETU_MASTER, ETU_MASTER + [RR("Bourse d'études", 800, 0, 24, imposable=False)], prof="etu"),
    A("S004", "modelise", ETU_MASTER, {}, {"taxe_semestre": 5000}, "Frais d'études de 10 000 CHF par an au lieu de 8 000.", prof="etu"),
    C("S005", "approxime", ETU_MASTER, [S(0, 12), W(2500, 12, 24), S(24, 36), J(36, 39), W("$salaire_apres_master", 39)],
      "Stage traité comme un emploi salarié ordinaire.", prof="etu"),
    C("S006", "modelise", SAL, [PZ(0, 4), DP("Bootcamp", 12000, 0), W(6000, 4)]),
    C("S007", "approxime", ETU_WORK, [W(4500, 0, 48), J(48, 51), W(7000, 51)],
      "Salaire de doctorant et de docteur supposés.", prof="etu"),
    C("S008", "approxime", ETU_MASTER, [S(0, 6), D("etranger", 2500, 6), S(6, 12), D("CH", 2500, 12), S(12, 24), J(24, 27),
                                        W("$salaire_apres_master", 27)], "Coût de la vie à l'étranger générique en EUR.", prof="etu"),
    C("S009", "approxime", ETU_MASTER, ETU_MASTER + [E("Prêt d'études", 20000, 0.03, 200, 0)],
      "Remboursement dès l'emprunt (pas de différé).", prof="etu"),
    C("S010", "modelise", ETU_MASTER, [S(0, 36), J(36, 39), W("$salaire_apres_master", 39)], prof="etu"),
    # --- Career & employment
    C("S011", "modelise", ETU_MASTER, ETU_WORK, prof="etu"),
    A("S012", "modelise", SAL, {}, {"salaire_sans_master": 5500}),
    C("S013", "modelise", SAL, [W(5100, 0, 24), W(5900, 24)]),
    B("S014", "modelise", SAL, (job(24, 6),), "Droit au chômage vérifié par le moteur."),
    C("S015", "approxime", SAL, [W(6000, **IND), DR("Frais professionnels", 400)], "AVS d'indépendant en taux unique."),
    C("S016", "modelise", SAL, [PZ(0, 3), W(4300, 3, 60), W(6200, 60)]),
    C("S017", "modelise", SAL, [W(5100, taux_activite=0.8)]),
    N("S018", "C", "participation", "Actions de l'employeur : actif non liquide à valeur incertaine."),
    C("S019", "modelise", SAL, [W(5100, 0, 24), J(24, 28), W(5100, 28, 52), J(52, 56), W(5100, 56)]),
    C("S020", "modelise", SAL, SAL + [W(1500)], "Deux employeurs : 2e pilier calculé par emploi."),
    # --- Relocation & geography
    C("S021", "approxime", SAL, [DP("Déménagement à Zurich", 3000, 0), DR("Loyer plus élevé à Zurich", 450), W(5700)],
      "Écart de loyer et de salaire supposés ; impôt zurichois non modélisé."),
    C("S022", "approxime", SAL, [DP("Déménagement à Genève", 3000, 0), DR("Loyer plus élevé à Genève", 350), W(5600)],
      "Écart de loyer et de salaire supposés ; impôt genevois non modélisé."),
    C("S023", "approxime", SAL, [D("etranger", 4000, 0), W(4800, devise="EUR")], "Coût de la vie et prélèvements allemands génériques."),
    C("S024", "approxime", SAL, [D("etranger", 6000, 0), W(6500, devise="EUR")], "Livre sterling approximée par l'euro.",
      ti={"cout_vie_etranger_eur": 2800}),
    C("S025", "approxime", SAL, [D("etranger", 8000, 0), W(7000, devise="EUR")], "Dollar de Singapour approximé par l'euro.",
      ti={"cout_vie_etranger_eur": 2600}),
    C("S026", "approxime", SAL, CROSS_BORDER, "Frontalier : cotisations suisses, coût de la vie en EUR, impôt à la source non modélisé."),
    C("S027", "modelise", ABROAD, [D("etranger", "$cout_demenagement", 0), W("$salaire_etranger_eur", 0, 36, devise="EUR"),
                                   D("CH", 4000, 36), J(36, 39), W(5100, 39)]),
    B("S028", "modelise", CROSS_BORDER, (fx_ramp(12, 36, 1.05),), "Le franc s'affaiblit : 0,94 → 1,05 CHF/EUR."),
    C("S029", "approxime", SAL, [W(3500), W(1800, devise="EUR")], "Prélèvements sur la part en EUR en taux unique."),
    A("S030", "modelise", ABROAD, {}, {"cout_demenagement": 9000}),
    # --- Housing & property
    A("S031", "modelise", SAL, {"loyer": 900}, {"loyer": 1393.94}, "Base : colocation."),
    A("S032", "modelise", SAL, {"loyer": 1393.94}, {"loyer": 900}),
    C("S033", "modelise", SAL, OWNER, "Achat dès que possible d'un bien à 350 000 CHF, le maximum que permet le test de capacité."),
    C("S034", "modelise", OWNER, SAL + [BUY(350000, part_fonds_propres=0.30)], "30 % de fonds propres au lieu de 20 %."),
    B("S035", "approxime", SAL + [BUY(350000, taux_variable=True)], (rate_from(60, 0.015),),
      "Renouvellement simulé par une hausse de 1,5 point du taux à partir du mois 60."),
    C("S036", "approxime", OWNER, OWNER + [DP("Rénovation", 40000, 72)], "La rénovation n'augmente pas la valeur du logement."),
    A("S037", "approxime", SAL, {}, {"loyer": 1393.94 * 1.10}, "Hausse unique de 10 % au lieu d'une hausse annuelle."),
    C("S038", "modelise", OWNER, SAL + [BUY(350000, 72)], "Base : achat dès que possible. Intervention : pas avant le mois 72."),
    B("S039", "modelise", OWNER, (house(60, 61, -0.15),), "Baisse de 15 % du prix du logement au mois 60."),
    C("S040", "modelise", OWNER, OWNER + [DP("Réparation majeure", 25000, 72)]),
    # --- Spending & lifestyle
    A("S041", "modelise", SAL, {}, {"vie_courante": 800}),
    C("S042", "modelise", SAL, SAL + [DP("Achat d'une voiture", 15000, 0), DR("Frais de voiture", 450)]),
    C("S043", "modelise", SAL + [DR("Frais de voiture", 450)],
      SAL + [RP("Vente de la voiture", 8000, 0), DR("Abonnement de transports publics", 180)]),
    C("S044", "approxime", SAL, [W(5100, 0, 24), PZ(24, 30), DP("Voyage sabbatique", 8000, 24), W(5100, 30)],
      "Au retour, le salaire repart du niveau d'avant (hausses perdues)."),
    C("S045", "modelise", SAL + [DR("Abonnements", 150)], SAL + [DR("Abonnements", 40)]),
    C("S046", "approxime", SAL, SAL + [DR("Train de vie en hausse", 200, 24, 60), DR("Train de vie en hausse", 450, 60)],
      "Hausse du train de vie par paliers, pas indexée sur le salaire."),
    C("S047", "modelise", SAL, SAL + [DP("Équipement coûteux", 6000, 12)]),
    C("S048", "modelise", SAL, SAL + [DP("Dépense imprévue", 8000, 30)]),
    A("S049", "approxime", SAL, {}, {"loyer": 800, "vie_courante": 800}, "Partage approximé par un loyer et une vie courante plus bas."),
    B("S050", "approxime", SAL, (cost_window(12, 24, 1.04),), "L'énergie double : environ +4 % du budget pendant un an."),
    # --- Savings & liquidity
    A("S051", "modelise", ETU_WORK, {"part_epargne_placee": 1.0, "reserve_cash_mois": 3},
      {"part_epargne_placee": 1.0, "reserve_cash_mois": 6},
      "Testé sur Alexia (8 000 CHF) : la réserve ne contraint que si l'épargne de départ est faible.", prof="etu"),
    C("S052", "modelise", SAL, SAL + [I(800)], tb={"part_epargne_placee": 0.0}),
    A("S053", "modelise", SAL, {"part_epargne_placee": 0.3}, {"part_epargne_placee": 0.7}),
    C("S054", "approxime", SAL, SAL + [DP("Achat prévu", 15000, 36)], "L'objectif est représenté par la dépense ; pas de porte dédiée."),
    N("S055", "C", "epargne_bloquee"),
    A("S056", "modelise", SAL, {}, {"taux_interet_cash": 0.01}),
    C("S057", "modelise", SAL, SAL + [RP("Donation", 30000, 24)], "Une donation n'est pas un revenu imposable."),
    B("S058", "modelise", SAL, (job(12, 4),)),
    C("S059", "modelise", SAL, SAL + [DP("Dépense urgente", 6000, 18)]),
    C("S060", "approxime", SAL, SAL + [DP("Objectif 1", 10000, 36), DP("Objectif 2", 15000, 60)], "Les objectifs sont des dépenses datées."),
    # --- Investments & allocation
    C("S061", "modelise", SAL, SAL + [I(800)], tb={"part_epargne_placee": 0.0}),
    N("S062", "C", "portefeuille_2_actifs"), N("S063", "C", "portefeuille_2_actifs"),
    A("S064", "approxime", SAL, {"rendement_placements_annuel": 0.025}, {"rendement_placements_annuel": 0.03},
      "Les frais sont représentés par un rendement net plus bas."),
    B("S065", "modelise", SAL, (crash(36, 0.30),)),
    B("S066", "modelise", SAL, (crash(36, 0.30), returns(37, 73, (1 / 0.7) ** (1 / 36) - 1)),
      "Base : reprise immédiate. Pour qui épargne chaque mois, une reprise lente permet d'acheter moins cher.",
      wb=(crash(36, 0.30), returns(37, 38, 1 / 0.7 - 1))),
    C("S067", "modelise", SAL + [I(800)], SAL + [I(800, 0, 36), I(800, 60)], tb={"part_epargne_placee": 0.0}),
    N("S068", "C", "portefeuille_2_actifs"), N("S069", "C", "portefeuille_2_actifs"), N("S070", "C", "placements_en_devise"),
    # --- Debt & credit
    C("S071", "modelise", SAL, SAL + [E("Prêt d'études à rembourser", 20000, 0.03, 400, 0)]),
    C("S072", "modelise", SAL, SAL + [E("Solde de carte de crédit", 5000, 0.12, 150, 0)]),
    C("S073", "approxime", SAL + [E("Prêt", 30000, 0.06, 500, 0)],
      SAL + [E("Prêt", 30000, 0.06, 500, 0), R(40000, 24), E("Prêt refinancé", 21000, 0.035, 500, 24)],
      "Montant refinancé arrondi au capital restant."),
    C("S074", "modelise", SAL + [E("Prêt", 30000, 0.05, 500, 0)], SAL + [E("Prêt", 30000, 0.05, 500, 0), R(10000, 24)]),
    B("S075", "modelise", VAR_LOAN, (rate_from(24, 0.02),)),
    C("S076", "approxime", SAL + [E("Prêt 1", 10000, 0.10, 300, 0), E("Prêt 2", 8000, 0.12, 250, 0)],
      SAL + [E("Prêt consolidé", 18000, 0.06, 550, 0)], "Taux de consolidation supposé."),
    C("S077", "modelise", SAL + [DP("Dépense", 8000, 12)], SAL + [DP("Dépense", 8000, 12), E("Crédit personnel", 8000, 0.08, 250, 12)]),
    C("S078", "approxime", SAL + [E("Prêt", 15000, 0.06, 300, 0)], SAL + [E("Prêt", 15000, 0.06, 300, 0), DP("Frais de retard", 150, 18)],
      "Seuls des frais de retard ; pas de pénalité de taux."),
    N("S079", "C", "plafond_de_financement", "Le moteur finance tout découvert ; un plafond rendrait le plan infaisable."),
    C("S080", "approxime", SAL + [E("Prêt", 30000, 0.05, 500, 0)], SAL + [E("Prêt", 30000, 0.05, 300, 0), R(5000, 36), R(5000, 72)],
      "Amortissement flexible représenté par une mensualité plus basse et deux remboursements anticipés."),
    # --- Family & life events
    A("S081", "approxime", SAL, {}, {"loyer": 800, "vie_courante": 800}, "Vie à deux approximée par des coûts partagés."),
    C("S082", "approxime", SAL, SAL + [DR("Frais de garde", 1800, 24, 84)], "Allocations familiales non modélisées."),
    C("S083", "approxime", SAL, [W(5100, 0, 36), W(5100, 36, 40, taux_activite=0.8), W(5100, 40)],
      "Congé indemnisé à 80 % (APG) ; hausses de salaire repartent à zéro."),
    C("S084", "modelise", SAL, SAL + [DR("Soutien familial", 500)]),
    C("S085", "modelise", SAL, SAL + [DP("Mariage", 20000, 30)]),
    C("S086", "approxime", SAL, [W(5100, 0, 48), W(5100, 48, 72, taux_activite=0.5), W(5100, 72)], "Hausses de salaire repartent à zéro."),
    N("S087", "C", "menage"),
    C("S088", "modelise", SAL, SAL + [DR("Frais d'études d'un proche", 800, 60)]),
    C("S089", "approxime", SAL, SAL + [DP("Franchise et quote-part", 2500, 24)], "Montant de franchise supposé."),
    C("S090", "approxime", SAL, [W(5100, 0, 36), W(5100, 36, 48, taux_activite=0.8), W(5100, 48)], "Indemnités de perte de gain à 80 %."),
    # --- Retirement & pensions
    N("S091", "C", "retraite"), N("S092", "C", "retraite"), N("S093", "C", "epargne_bloquee"),
    C("S094", "modelise", SAL, [W(5100, 0, 36), PZ(36, 60), W(5100, 60)], "L'interruption réduit le 2e pilier, visible dans le patrimoine."),
    N("S095", "C", "retraite"), N("S096", "B", "retraite"), N("S097", "C", "retraite"), N("S098", "A", "retraite"),
    N("S099", "C", "retraite"), N("S100", "B", "retraite"),
    # --- Macroeconomic & systemic shocks
    B("S101", "approxime", SAL, (cost_ramp(12, 36, 1.06),), "Les prix montent de 6 % sans rattrapage des salaires."),
    B("S102", "approxime", SAL, (cost_ramp(12, 36, 0.97),), "Les prix baissent de 3 % sans baisse des salaires."),
    B("S103", "modelise", VAR_LOAN, (rate_from(12, 0.015),)),
    B("S104", "modelise", SAL, (job(24, 6), crash(24, 0.20))),
    B("S105", "modelise", ABROAD, (fx_wave(0.08, 24),)),
    B("S106", "approxime", SAL, (cost_window(12, 24, 1.04),), "Choc énergétique : environ +4 % du budget pendant un an."),
    A("S107", "approxime", SAL, {}, {"impot_pente": 0.20, "impot_taux_max": 0.25}, "Sur le barème illustratif."),
    B("S108", "modelise", OWNER, (house(48, 72, 0.8 ** (1 / 24) - 1),), "Le prix des logements baisse de 20 % en deux ans."),
    N("S109", "B", "friction_liquidite"),
    B("S110", "modelise", SAL, (job(36, 6), crash(36, 0.30))),
    # --- Entrepreneurship & innovation
    C("S111", "approxime", SAL, START_UP, "Revenus d'indépendant supposés."),
    C("S112", "modelise", SAL, SAL + [RR("Projet à côté", 600, 12)]),
    N("S113", "C", "participation"),
    C("S114", "approxime", START_UP, [W(3000, 0, 24, **IND), DP("Lancement de l'entreprise", 15000, 0), J(24, 28), W(5100, 28)],
      "Échec au mois 24 : retour au salariat."),
    C("S115", "approxime", [PZ(0, 6), W(5000, 6, H, **IND)], [PZ(0, 18), W(5000, 18, H, **IND)],
      "Revenu d'indépendant constant une fois lancé ; le retard est une période sans revenu."),
    C("S116", "approxime", [W(7000, **IND)], [W(7000, 0, 24, **IND), W(13000, 24, H, **IND), DR("Salaire du premier employé", 5500, 24)],
      "Charges sociales de l'employeur non modélisées."),
    N("S117", "C", "participation"),
    C("S118", "approxime", [W(7000, **IND)], [W(4500, **IND)],
      "Le salaire du fondateur est traité comme un revenu d'indépendant ; la valeur de l'entreprise n'est pas modélisée."),
    C("S119", "approxime", [W(6000, **IND)], [W(6000, **IND), E("Prêt d'entreprise", 50000, 0.05, 900, 0),
                                              DP("Investissement dans l'entreprise", 50000, 0)], "Pas de rendement de l'investissement."),
    N("S120", "C", "participation"),
)


# ---------------------------------------------------------------------------- exécution
def _simulate(spec: Spec, ops: tuple, overrides: dict, mods: tuple):
    th = theta_for(ALEXIA, {**THETA[spec.profile], **overrides})
    line = Line(spec.id, spec.id, ops)
    return run_ops(PROFILES[spec.profile], materialize(line, th), H, th, build_world(th, mods))


def run_spec(spec: Spec) -> dict:
    out = {"id": spec.id, "family": spec.family, "fidelity": spec.fidelity, "note": spec.note, "missing": spec.missing}
    if spec.fidelity == "non_couvert":
        return out
    b = _simulate(spec, spec.base, spec.theta_base, spec.world_base)
    i = _simulate(spec, spec.intervention, spec.theta_int, spec.world_int)
    ok = all(_identities(r)[0] and _identities(r)[1] for r in (b, i))
    out.update({
        "profile": PROFILES[spec.profile].name,
        "net_worth_base": round(b.net_worth_end_chf), "net_worth_int": round(i.net_worth_end_chf),
        "delta": round(i.net_worth_end_chf - b.net_worth_end_chf),
        "financing_base": round(b.peak_financing_chf), "financing_int": round(i.peak_financing_chf),
        "identities_ok": ok,
        "changed": [m.net_worth_chf for m in b.months] != [m.net_worth_chf for m in i.months],
    })
    return out


def catalog_names() -> dict[str, dict]:
    with open(ROOT / "Data/scenario-catalog.csv", encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def report() -> tuple[list[dict], str]:
    names, rows = catalog_names(), [run_spec(s) for s in SPECS]
    count = lambda key, val: sum(1 for r in rows if r[key] == val)
    fam = {"A": "hypothèse", "B": "monde", "C": "décision"}
    fid = {"modelise": "🟢 modélisé", "approxime": "🟠 approximé", "non_couvert": "⚪ non couvert"}
    covered = [r for r in rows if r["fidelity"] != "non_couvert"]
    lines = [
        "# Couverture du catalogue de 120 scénarios",
        "",
        "Généré par `python3 -m engine.catalog`. Chaque scénario couvert est réellement simulé (base et intervention, "
        "120 mois), et ses identités comptables sont vérifiées.",
        "",
        f"- **{len(covered)} / 120 scénarios tournent** : {count('fidelity', 'modelise')} modélisés, "
        f"{count('fidelity', 'approxime')} approximés (approximation écrite).",
        f"- **{count('fidelity', 'non_couvert')} non couverts**, chacun avec l'opération manquante.",
        f"- Identités comptables : **{sum(r['identities_ok'] for r in covered)} / {len(covered)}** scénarios sans erreur.",
        f"- Familles : {count('family', 'A')} hypothèse, {count('family', 'B')} monde, {count('family', 'C')} décision.",
        "",
        "Opérations manquantes : " + ", ".join(
            f"`{m}` ({sum(1 for r in rows if r['missing'] == m)})" for m in sorted({r['missing'] for r in rows if r['missing']})),
        "",
        "Les montants sont des conséquences d'hypothèses illustratives, pas des prévisions.",
        "",
        "| ID | Catégorie | Scénario | Famille | Fidélité | Profil | Patrimoine base → intervention (CHF) | Δ | Financement max | Note |",
        "|---|---|---|---|---|---|---|---:|---|---|",
    ]
    for r in rows:
        n = names.get(r["id"], {})
        if r["fidelity"] == "non_couvert":
            cells = ["", "", "", "", f"manque `{r['missing']}`. {r['note']}".strip()]
        else:
            cells = [r["profile"], f"{r['net_worth_base']:,} → {r['net_worth_int']:,}".replace(",", "'"),
                     f"{r['delta']:+,}".replace(",", "'"),
                     f"{r['financing_base']:,} → {r['financing_int']:,}".replace(",", "'"), r["note"]]
        lines.append(f"| {r['id']} | {n.get('category', '')} | {n.get('scenario', '')} | {fam[r['family']]} | "
                     f"{fid[r['fidelity']]} | " + " | ".join(cells) + " |")
    return rows, "\n".join(lines) + "\n"


def _main() -> None:
    rows, md = report()
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "coverage.md").write_text(md, encoding="utf-8")
    (out / "coverage.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(md.splitlines()[4:9]))


if __name__ == "__main__":
    _main()

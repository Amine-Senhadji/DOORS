"""La fonction de transition F : x_{t+1} = F(x_t, a_t, w_t ; theta).

Pure et déterministe : aucune variable globale, aucun hasard, l'état d'entrée n'est jamais
modifié. Elle renvoie le nouvel état ET le registre du mois (liste de Flow).

Ordre de calcul d'un mois (sections de docs/scenario-modelling.md entre parenthèses) :
  0. En janvier : impôt de l'année écoulée, payé en 12 fois l'année suivante
  1. Réévaluation du cash en EUR si le taux de change a bougé (section 8, multi-devises)
  2. Intérêts du financement du découvert (section 6)
  3. Prêts : intérêts = dépense ; capital = cash −, dette − (section 6)
  4. Décisions actives : revenus brut -> net, cotisations, 2e pilier, événements (sections 3, 9)
  5. Dépenses courantes : loyer, vie courante, LAMal ou coût de la vie à l'étranger (section 3)
  6. Impôt dû (section 3, T_t)
  7. Rendement des placements, sur le solde d'ouverture (section 5)
  8. Équilibrage : EUR négatif couvert depuis le CHF, puis CHF négatif couvert par un
     financement explicite ; un CHF positif rembourse d'abord le financement (section 14)
  9. Épargne placée automatiquement : une part de l'excédent du mois, seulement sans
     découvert et au-delà d'une réserve de cash (section 5, I_{t+1} = I_t(1+r) + A_t)
"""
from __future__ import annotations

from dataclasses import replace

from engine.i18n import say
from engine.contract import Category as C
from engine.contract import Flow, Loan, Operation, State, World

REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "etudier": ("job_net_mensuel", "taxe_semestre"),
    "travailler": ("salaire_brut_mensuel",),
    "chercher_emploi": (),
    "pause": (),
    "demenager": ("lieu", "cout_chf"),
    "emprunter": ("libelle", "montant", "taux_annuel", "mensualite"),
    "rembourser": ("montant",),
    "investir": ("montant_mensuel",),
    "depense_recurrente": ("libelle", "montant"),
    "depense_ponctuelle": ("libelle", "montant"),
    "revenu_ponctuel": ("libelle", "montant"),
    "revenu_recurrent": ("libelle", "montant"),
    "acheter_logement": ("prix",),
}
EPS = 1e-9


def monthly_rate(annual: float) -> float:
    """Taux mensuel équivalent : (1 + r)^(1/12) − 1, et non r / 12."""
    return (1.0 + annual) ** (1.0 / 12.0) - 1.0


def income_tax(taxable_year: float, th: dict[str, float]) -> float:
    """Barème ILLUSTRATIF progressif (pas le barème vaudois officiel)."""
    if taxable_year <= th["impot_seuil"]:
        return 0.0
    rate = th["impot_taux_min"] + (taxable_year - th["impot_seuil"]) / 100_000 * th["impot_pente"]
    return taxable_year * min(th["impot_taux_max"], rate)


def validate(ops: tuple[Operation, ...]) -> None:
    """Donnée manquante : on refuse clairement plutôt que d'inventer une valeur."""
    for op in ops:
        if op.kind not in REQUIRED_PARAMS:
            raise ValueError(say(f"Unknown operation “{op.kind}”. Vocabulary: {sorted(REQUIRED_PARAMS)}",
                                 f"Opération inconnue « {op.kind} ». Vocabulaire : {sorted(REQUIRED_PARAMS)}"))
        if not 0 <= op.start <= op.end:
            raise ValueError(say(f"Operation “{op.kind}”: invalid month interval [{op.start}, {op.end}).",
                                 f"Opération « {op.kind} » : intervalle de mois invalide [{op.start}, {op.end})."))
        for p in REQUIRED_PARAMS[op.kind]:
            if p not in op.params:
                raise ValueError(say(f"Operation “{op.kind}” (months {op.start}–{op.end}): missing parameter "
                                     f"“{p}”. Add it to the scenario or define the matching assumption.",
                                     f"Opération « {op.kind} » (mois {op.start}–{op.end}) : paramètre manquant "
                                     f"« {p} ». Ajoute-le au scénario ou définis l'hypothèse correspondante."))


class _Ledger:
    def __init__(self, month: int, fx: float):
        self.month, self.fx, self.flows = month, fx, []

    def add(self, label: str, cat: C, account: str, amount: float, rule: str, currency: str = "CHF") -> None:
        if abs(amount) < EPS:
            return
        chf = amount if currency == "CHF" else amount * self.fx
        self.flows.append(Flow(self.month, label, cat, account, amount, currency, chf, rule))

    def add_fx_revaluation(self, amount_chf: float) -> None:
        if abs(amount_chf) >= EPS:
            self.flows.append(Flow(self.month, "Effet du taux de change sur le cash en EUR", C.CHANGE,
                                   "cash", 0.0, "EUR", amount_chf, "fx"))

    def total(self, account: str, currency: str | None = None) -> float:
        return sum(f.amount if currency else f.amount_chf for f in self.flows
                   if f.account == account and (currency is None or f.currency == currency))


def transition(x: State, ops: tuple[Operation, ...], w: World,
               th: dict[str, float]) -> tuple[State, list[Flow]]:
    m, age, fx = x.month, x.age, w.fx_chf_per_eur
    L = _Ledger(m, fx)
    active = [op for op in ops if op.start <= m < op.end]
    starting = [op for op in ops if op.start == m]

    # 0. Impôt de l'année écoulée, calculé en janvier, payé sur 12 mois
    tax_due, taxable = x.tax_due_monthly_chf, x.taxable_ytd_chf
    if m > 0 and m % 12 == 0:
        tax_due, taxable = income_tax(taxable, th) / 12.0, 0.0

    # 1. Réévaluation du cash détenu en EUR
    eur_open = x.cash.get("EUR", 0.0)
    if eur_open:
        L.add_fx_revaluation(eur_open * (fx - x.fx_chf_per_eur))

    # 2. Intérêts du financement du découvert
    if x.overdraft_chf > EPS:
        L.add("Intérêts du financement du découvert", C.INTERETS, "cash",
              -x.overdraft_chf * monthly_rate(th["taux_decouvert"] + w.rate_shift), "taux_decouvert")

    # 3. Prêts existants (un prêt à taux variable suit la hausse des taux du monde)
    loans: list[Loan] = []
    mortgage_interest = 0.0
    for ln in x.loans:
        interest = ln.principal_chf * monthly_rate(ln.annual_rate + (w.rate_shift if ln.variable else 0.0))
        if ln.fixed_amortization_chf:
            # Hypothèque : intérêts en plus, amortissement fixe jusqu'au plancher (2/3 du prix)
            capital = min(ln.fixed_amortization_chf, max(0.0, ln.principal_chf - ln.amortization_floor_chf))
            mortgage_interest += interest
        else:
            capital = min(ln.principal_chf, max(0.0, ln.monthly_payment_chf - interest)) if ln.monthly_payment_chf else 0.0
        L.add(f"Intérêts : {ln.label}", C.INTERETS, "cash", -interest, ln.id)
        L.add(f"Remboursement : {ln.label}", C.REMBOURSEMENT, "cash", -capital, ln.id)
        L.add(f"Remboursement : {ln.label}", C.REMBOURSEMENT, "dette", -capital, ln.id)
        if ln.principal_chf - capital > EPS:
            loans.append(replace(ln, principal_chf=ln.principal_chf - capital))

    # 4. Décisions
    status, location, working, contributed = x.status, x.location, False, False
    lifestyle = None                # dépenses totales du mois fixées par un emploi (paramètre depenses_mensuelles)
    gross_income_chf = 0.0          # revenu brut du mois, pour le test de capacité hypothécaire
    window = int(th["chomage_fenetre_mois"])
    months_contributed = sum(x.cotisations_ac[-window:])
    for op in starting:
        p = op.params
        if op.kind == "demenager":
            location = p["lieu"]
            L.add(f"Déménagement ({p['lieu']})", C.PONCTUEL, "cash", -p["cout_chf"], "cout_demenagement")
        elif op.kind == "emprunter":
            L.add(f"Emprunt : {p['libelle']}", C.EMPRUNT, "cash", p["montant"], "emprunter")
            L.add(f"Emprunt : {p['libelle']}", C.EMPRUNT, "dette", p["montant"], "emprunter")
            loans.append(Loan(f"pret_m{m}", p["libelle"], p["montant"], p["taux_annuel"], p["mensualite"],
                              bool(p.get("taux_variable", False))))
        elif op.kind == "rembourser":
            left = p["montant"]
            for i, ln in enumerate(loans):
                pay = min(left, ln.principal_chf)
                L.add(f"Remboursement anticipé : {ln.label}", C.REMBOURSEMENT, "cash", -pay, "rembourser")
                L.add(f"Remboursement anticipé : {ln.label}", C.REMBOURSEMENT, "dette", -pay, "rembourser")
                loans[i], left = replace(ln, principal_chf=ln.principal_chf - pay), left - pay
            loans = [ln for ln in loans if ln.principal_chf > EPS]
        elif op.kind == "depense_ponctuelle":
            L.add(p["libelle"], C.PONCTUEL, "cash", -p["montant"], "depense_ponctuelle")
        elif op.kind == "revenu_ponctuel":
            L.add(p["libelle"], C.REVENU, "cash", p["montant"], "revenu_ponctuel")

    for op in active:
        p = op.params
        if op.kind == "etudier":
            status = "etudiant"
            if w.student_job_lost and p["job_net_mensuel"] > 0:
                # Le job étudiant est perdu : pas de revenu, et pas d'indemnité. Une note dans le registre, de montant 0.
                L.flows.append(Flow(m, "Job étudiant perdu : pas de revenu ce mois, et pas d'indemnité de chômage",
                                    C.REVENU, "cash", 0.0, "CHF", 0.0, "perte_job_etudiant_mois"))
            else:
                L.add("Job étudiant (net)", C.REVENU, "cash", p["job_net_mensuel"], "job_net_mensuel")
            if (m - op.start) % 6 == 0:
                L.add("Taxe d'études semestrielle", C.ETUDES, "cash", -p["taxe_semestre"], "taxe_semestre")
        elif op.kind in ("chercher_emploi", "pause"):
            status = "recherche" if op.kind == "chercher_emploi" else "pause"
        elif op.kind == "revenu_recurrent":
            L.add(p["libelle"], C.REVENU, "cash", p["montant"], "revenu_recurrent")
            if location == "CH" and p.get("imposable", True):
                taxable += p["montant"]
        elif op.kind == "travailler":
            cur = p.get("devise", "CHF")
            independent = p.get("statut", "salarie") == "independant"
            status, working = ("independant" if independent else "salarie"), True
            if "depenses_mensuelles" in p:
                lifestyle = max(lifestyle or 0.0, p["depenses_mensuelles"])
            # Temps partiel : le salaire brut à plein temps est multiplié par le taux d'activité.
            # Ancienneté : les mois déjà travaillés avant cette opération comptent pour les hausses annuelles.
            # Sans elle, changer de taux d'activité ou reprendre après une pause remettrait les hausses à zéro.
            seniority = int(p.get("anciennete_mois", 0))
            gross = (p["salaire_brut_mensuel"] * p.get("taux_activite", 1.0)
                     * (1 + th["hausse_salaire_annuelle"]) ** ((m - op.start + seniority) // 12))
            if independent and cur == "CHF":
                # Indépendant : AVS propre, pas d'assurance chômage, pas de 2e pilier obligatoire.
                if w.job_lost:
                    L.flows.append(Flow(m, "Pas d'indemnité de chômage : les indépendants ne sont pas assurés",
                                        C.REVENU, "cash", 0.0, "CHF", 0.0, "taux_avs_independant"))
                    continue
                L.add("Revenu d'indépendant", C.REVENU, "cash", gross, "salaire_brut_mensuel")
                gross_income_chf += gross
                soc = gross * th["taux_avs_independant"]
                L.add("AVS/AI/APG d'indépendant", C.COTISATION, "cash", -soc, "taux_avs_independant")
                taxable += gross - soc
                continue
            if w.job_lost:
                if cur == "CHF":
                    eligible = months_contributed >= th["chomage_mois_cotises_min"]
                    rate = th["taux_indemnite_ch"] if eligible else 0.0
                    if not eligible:
                        L.flows.append(Flow(m, f"Pas d'indemnité de chômage : {months_contributed} mois cotisés "
                                               f"sur {window}, il en faut {th['chomage_mois_cotises_min']:.0f}",
                                            C.REVENU, "cash", 0.0, "CHF", 0.0, "chomage_mois_cotises_min"))
                else:
                    rate = th["taux_indemnite_etranger"]
                paid, label = gross * rate, "Indemnité de chômage"
            else:
                paid, label = gross, "Salaire brut"
                contributed = contributed or cur == "CHF"
                gross_income_chf += gross if cur == "CHF" else gross * fx
            L.add(label, C.REVENU, "cash", paid, "salaire_brut_mensuel", cur)
            if cur == "CHF":
                soc = paid * (th["taux_avs_ai_apg"] + th["taux_ac"])
                L.add("AVS/AI/APG + assurance chômage", C.COTISATION, "cash", -soc, "taux_avs_ai_apg")
                lpp_employee = 0.0
                if not w.job_lost and age >= th["lpp_age_epargne"] and gross * 12 >= th["lpp_seuil_entree"]:
                    coordinated = max(0.0, gross * 12 - th["lpp_deduction_coordination"]) / 12
                    total = coordinated * th["lpp_taux_total"]
                    lpp_employee = total / 2
                    L.add("2e pilier, part salarié", C.COTISATION, "cash", -lpp_employee, "lpp_taux_total")
                    L.add("2e pilier, versement salarié + employeur", C.PREVOYANCE, "pilier2", total, "lpp_taux_total")
                taxable += paid - soc - lpp_employee
            else:
                L.add("Impôts et cotisations locaux", C.COTISATION, "cash",
                      -paid * th["taux_global_etranger"], "taux_global_etranger", cur)
        elif op.kind == "investir":
            L.add("Virement vers les placements", C.TRANSFERT, "cash", -p["montant_mensuel"], "investir")
            L.add("Virement vers les placements", C.TRANSFERT, "placements", p["montant_mensuel"], "investir")
        elif op.kind == "depense_recurrente":
            L.add(p["libelle"], C.VIE_COURANTE, "cash", -p["montant"], "depense_recurrente")

    # 4 bis. Achat d'un logement : tenté chaque mois de la fenêtre, tant qu'il n'a pas eu lieu
    home = x.prix_achat_logement_chf          # valeur stable, pas le prix de marché du jour
    for op in active:
        if op.kind == "acheter_logement" and home <= EPS:
            if _try_buy(op.params, x, L, th, loans, gross_income_chf):
                home = op.params["prix"]

    # 5. Dépenses courantes (ajustées par l'indice des prix du monde ; 1 = référence)
    ci = w.cost_index
    if location == "CH":
        adult = age >= th["age_lamal_adulte"]
        if home > EPS:
            upkeep = home * th["entretien_logement"] / 12 * ci
            L.add("Entretien du logement", C.LOGEMENT, "cash", -upkeep, "entretien_logement")
            # Fiscalité du propriétaire : valeur locative imposée, intérêts et entretien déductibles.
            taxable += home * th["valeur_locative_taux"] / 12 - mortgage_interest - upkeep
        else:
            L.add("Loyer", C.LOGEMENT, "cash", -th["loyer"] * ci, "loyer")
        lamal = th["lamal_adulte"] if adult else th["lamal_jeune"]
        if lifestyle is None:
            L.add("Vie courante", C.VIE_COURANTE, "cash", -th["vie_courante"] * ci, "vie_courante")
        else:
            # En emploi, les dépenses totales sont données : la vie courante est ce qui reste après le loyer et la LAMal.
            L.add("Vie courante", C.VIE_COURANTE, "cash", -max(0.0, lifestyle - th["loyer"] - lamal) * ci, "depenses_mensuelles")
        L.add("LAMal (adulte)" if adult else "LAMal (19–25 ans)", C.SANTE, "cash", -lamal * ci,
              "lamal_adulte" if adult else "lamal_jeune")
        if not working and age >= th["age_avs_sans_activite"]:
            L.add("AVS minimale (sans activité lucrative)", C.COTISATION, "cash",
                  -th["avs_min_annuel"] / 12, "avs_min_annuel")
    else:
        L.add("Coût de la vie à l'étranger", C.VIE_COURANTE, "cash", -th["cout_vie_etranger_eur"] * ci,
              "cout_vie_etranger_eur", "EUR")

    # 6. Impôt dû
    L.add("Impôt de l'année précédente (1/12)", C.IMPOT, "cash", -tax_due, "impot_seuil")

    # 7. Rendement des placements (solde d'ouverture)
    L.add("Rendement des placements", C.RENDEMENT, "placements",
          x.placements_chf * w.market_return_monthly, "rendement_placements_annuel")
    L.add("Variation de valeur du logement", C.RENDEMENT, "logement",
          x.logement_chf * w.house_return_monthly, "hausse_prix_logement_annuelle")
    if x.cash.get("CHF", 0.0) > EPS and th["taux_interet_cash"]:
        L.add("Intérêts sur le compte", C.RENDEMENT, "cash",
              x.cash["CHF"] * monthly_rate(th["taux_interet_cash"]), "taux_interet_cash")

    # 8. Équilibrage des devises et financement explicite
    chf = x.cash.get("CHF", 0.0) + L.total("cash", "CHF")
    eur = eur_open + L.total("cash", "EUR")
    if eur < -EPS:
        L.add("Conversion CHF → EUR", C.TRANSFERT, "cash", -eur, "fx", "EUR")
        L.add("Conversion CHF → EUR", C.TRANSFERT, "cash", eur * fx, "fx", "CHF")
        chf, eur = chf + eur * fx, 0.0
    overdraft = x.overdraft_chf
    if chf < -EPS:
        L.add("Financement du découvert", C.EMPRUNT, "cash", -chf, "taux_decouvert")
        L.add("Financement du découvert", C.EMPRUNT, "dette", -chf, "taux_decouvert")
        overdraft, chf = overdraft - chf, 0.0
    elif chf > EPS and overdraft > EPS:
        pay = min(chf, overdraft)
        L.add("Remboursement du découvert", C.REMBOURSEMENT, "cash", -pay, "taux_decouvert")
        L.add("Remboursement du découvert", C.REMBOURSEMENT, "dette", -pay, "taux_decouvert")
        overdraft, chf = overdraft - pay, chf - pay

    # 9. Épargne placée automatiquement
    if overdraft <= EPS and th["part_epargne_placee"] > 0:
        surplus = sum(f.amount_chf for f in L.flows if f.account == "cash"
                      and f.category not in (C.TRANSFERT, C.CHANGE, C.EMPRUNT, C.REMBOURSEMENT))
        expenses = -sum(f.amount_chf for f in L.flows if f.account == "cash"
                        and f.category in (C.LOGEMENT, C.VIE_COURANTE, C.SANTE))
        source = "EUR" if location != "CH" and eur > EPS else "CHF"
        available_chf = (eur * fx if source == "EUR" else chf) - th["reserve_cash_mois"] * expenses
        amount_chf = min(th["part_epargne_placee"] * max(0.0, surplus), max(0.0, available_chf))
        if amount_chf > EPS:
            label = "Épargne placée automatiquement"
            if source == "EUR":
                L.add(label, C.TRANSFERT, "cash", -amount_chf / fx, "part_epargne_placee", "EUR")
                eur -= amount_chf / fx
            else:
                L.add(label, C.TRANSFERT, "cash", -amount_chf, "part_epargne_placee")
                chf -= amount_chf
            L.add(label, C.TRANSFERT, "placements", amount_chf, "part_epargne_placee")

    new = replace(
        x, month=m + 1, age=age + 1 / 12, cash={"CHF": chf, "EUR": eur},
        placements_chf=x.placements_chf + L.total("placements"),
        pilier2_chf=x.pilier2_chf + L.total("pilier2"),
        loans=tuple(loans), overdraft_chf=max(0.0, overdraft) if overdraft > EPS else 0.0,
        status=status, location=location, tax_due_monthly_chf=tax_due,
        taxable_ytd_chf=taxable, fx_chf_per_eur=fx,
        cotisations_ac=(x.cotisations_ac + (1 if contributed else 0,))[-window:],
        logement_chf=x.logement_chf + L.total("logement"),
        prix_achat_logement_chf=home,
    )
    return new, L.flows


def _try_buy(p: dict, x: State, L: _Ledger, th: dict[str, float], loans: list[Loan], gross_month: float) -> bool:
    """Achat selon les règles suisses simplifiées : fonds propres, puis test de capacité.
    En cas de refus, une ligne du registre explique pourquoi, et rien d'autre ne bouge."""
    m, price = L.month, p["prix"]
    share = p.get("part_fonds_propres", th["fonds_propres_min"])
    fees = price * th["frais_achat_logement"]
    equity = share * price
    p2_max = max(0.0, share - th["fonds_propres_durs_min"]) * price
    from_p2 = min(x.pilier2_chf, p2_max) if p.get("utiliser_pilier2", True) else 0.0
    cash_needed = equity - from_p2 + fees
    cash_now = x.cash.get("CHF", 0.0) + L.total("cash", "CHF") - x.overdraft_chf
    liquid = cash_now + x.placements_chf
    mortgage = price - equity
    amort_year = max(0.0, mortgage - 2 / 3 * price) / th["amortissement_annees"]
    charges = mortgage * th["taux_theorique"] + amort_year + price * th["entretien_logement"]
    gross_year = gross_month * 12
    # Après l'achat, on garde une réserve de quelques mois de dépenses de propriétaire.
    reserve = th["reserve_cash_mois"] * (th["vie_courante"] + th["lamal_adulte"] + price * th["entretien_logement"] / 12)
    chf = lambda v: f"{v:,.0f}".replace(",", "'")

    def refuse(reason: str) -> bool:
        L.flows.append(Flow(m, reason, C.PONCTUEL, "cash", 0.0, "CHF", 0.0, "acheter_logement"))
        return False

    if liquid < cash_needed + reserve:
        return refuse(f"Achat impossible : fonds propres insuffisants ({chf(liquid)} CHF disponibles ; "
                      f"{chf(cash_needed + reserve)} CHF nécessaires hors 2e pilier, frais et réserve compris)")
    if gross_year <= 0 or charges > th["ratio_charges_max"] * gross_year:
        return refuse(f"Achat refusé par le test de capacité : charges théoriques {chf(charges)} CHF/an ; "
                      f"plafond {chf(th['ratio_charges_max'] * gross_year)} CHF/an (1/3 du revenu brut)")

    sell = min(x.placements_chf, max(0.0, cash_needed + reserve - cash_now))   # la réserve reste en cash
    L.add("Vente de placements pour l'apport", C.TRANSFERT, "placements", -sell, "acheter_logement")
    L.add("Vente de placements pour l'apport", C.TRANSFERT, "cash", sell, "acheter_logement")
    L.add("Apport en fonds propres", C.TRANSFERT, "cash", -(equity - from_p2), "fonds_propres_min")
    L.add("Retrait du 2e pilier pour le logement", C.TRANSFERT, "pilier2", -from_p2, "fonds_propres_durs_min")
    L.add("Achat du logement", C.TRANSFERT, "logement", price, "acheter_logement")
    L.add("Hypothèque", C.EMPRUNT, "dette", mortgage, "taux_hypotheque")
    L.add("Frais d'achat (droits de mutation, notaire)", C.PONCTUEL, "cash", -fees, "frais_achat_logement")
    loans.append(Loan("hypotheque", "Hypothèque", mortgage, p.get("taux_hypotheque", th["taux_hypotheque"]), 0.0,
                      bool(p.get("taux_variable", False)), amort_year / 12, 2 / 3 * price))
    return True

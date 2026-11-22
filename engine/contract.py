"""Contrat partagé entre le moteur, l'API et l'interface.

Ce fichier ne calcule rien. Il fixe les formes de données que tout le monde utilise,
pour que le moteur et l'interface puissent avancer en parallèle.

Cadre (docs/scenario-modelling.md, section 2) :

    x_{t+1} = F(x_t, a_t, w_t ; theta)

    x_t   -> State        l'état financier au début du mois t
    a_t   -> Operation    les décisions actives ce mois-ci (ce que l'utilisateur choisit)
    w_t   -> World        les conditions extérieures du mois (ce que le monde impose)
    theta -> Assumption   les hypothèses affichées et modifiables

Règles :
  * F est pure et déterministe : mêmes entrées, même sortie. Aucun hasard dans F.
    Toute l'incertitude passe par World (monde de référence, crise rejouée, Monte Carlo).
  * Pas de temps : le mois. Montants exprimés en CHF d'aujourd'hui, sauf indication de devise.
  * Registre en partie double : chaque Flow modifie UN compte. Un virement cash -> placements
    produit deux Flow (cash -500, placements +500), donc le patrimoine ne bouge pas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Protocol

Currency = Literal["CHF", "EUR"]
Status = Literal["etudiant", "recherche", "salarie", "independant", "pause"]
Location = Literal["CH", "etranger"]

# Comptes du registre. Les actifs augmentent le patrimoine, les passifs le diminuent.
Account = Literal["cash", "placements", "pilier2", "logement", "dette"]
ASSET_ACCOUNTS: tuple[Account, ...] = ("cash", "placements", "pilier2", "logement")
LIABILITY_ACCOUNTS: tuple[Account, ...] = ("dette",)


class Category(str, Enum):
    """Catégorie d'un flux, pour le registre et les explications."""
    REVENU = "revenu"                  # salaire brut, job étudiant, revenu ponctuel
    COTISATION = "cotisation"          # AVS/AI/APG, AC, part salarié LPP
    IMPOT = "impot"
    LOGEMENT = "logement"
    SANTE = "sante"                    # LAMal
    VIE_COURANTE = "vie_courante"
    ETUDES = "etudes"
    PONCTUEL = "ponctuel"              # déménagement, achat, urgence
    INTERETS = "interets"              # intérêts payés : une dépense
    RENDEMENT = "rendement"            # rendement des placements, intérêts reçus
    TRANSFERT = "transfert"            # mouvement entre comptes : patrimoine inchangé
    EMPRUNT = "emprunt"                # nouvelle dette : cash +, dette +
    REMBOURSEMENT = "remboursement"    # capital remboursé : cash -, dette -
    PREVOYANCE = "prevoyance"          # versements au 2e pilier (salarié + employeur)
    CHANGE = "change"                  # effet du taux de change sur un solde en devise


AssumptionKind = Literal["observe", "hypothese", "a_verifier", "regle"]


@dataclass(frozen=True)
class Assumption:
    """Une hypothèse theta, affichée telle quelle dans le panneau « Hypothèses »."""
    key: str
    label: str
    value: float
    unit: str                    # "CHF/mois", "%", "mois", "CHF/EUR"...
    kind: AssumptionKind         # observe = tiré des données synthétiques
    source: str                  # URL officielle, fichier de données, ou "[à vérifier]"


@dataclass(frozen=True)
class Profile:
    """Profil fictif, lu dans Data/synthetic-profiles.csv."""
    id: str
    name: str
    age: int
    city: str
    canton: str
    cash_chf: float
    observed_monthly_income_chf: float
    observed_monthly_rent_chf: float


@dataclass(frozen=True)
class Loan:
    id: str
    label: str
    principal_chf: float         # capital restant dû, jamais négatif
    annual_rate: float
    monthly_payment_chf: float   # 0 = pas d'amortissement prévu
    variable: bool = False       # taux variable : suit World.rate_shift
    fixed_amortization_chf: float = 0.0   # hypothèque : capital remboursé chaque mois, intérêts en plus
    amortization_floor_chf: float = 0.0   # l'amortissement s'arrête à ce capital (2/3 du prix)


@dataclass(frozen=True)
class State:
    """x_t : l'état au début du mois `month`."""
    month: int
    age: float
    cash: dict[str, float]                  # solde par devise, ex. {"CHF": 8000.0}
    placements_chf: float = 0.0
    pilier2_chf: float = 0.0
    loans: tuple[Loan, ...] = ()
    overdraft_chf: float = 0.0              # financement du découvert (passif), >= 0
    status: Status = "etudiant"
    location: Location = "CH"
    tax_due_monthly_chf: float = 0.0        # impôt de l'année passée, payé en 12 fois
    taxable_ytd_chf: float = 0.0            # revenu imposable cumulé depuis janvier
    fx_chf_per_eur: float = 0.94            # dernier taux utilisé, pour réévaluer le cash en EUR
    cotisations_ac: tuple[int, ...] = ()    # 1 par mois cotisé à l'assurance chômage, derniers mois
    logement_chf: float = 0.0               # valeur de marché du logement possédé (0 = locataire)
    prix_achat_logement_chf: float = 0.0    # base de l'entretien et de la valeur locative


OperationKind = Literal[
    "etudier", "travailler", "chercher_emploi", "pause", "demenager",
    "emprunter", "rembourser", "investir",
    "depense_recurrente", "depense_ponctuelle", "revenu_ponctuel", "revenu_recurrent",
    "acheter_logement",
]


@dataclass(frozen=True)
class Operation:
    """a_t : une décision du vocabulaire, active sur [start, end) en mois."""
    kind: OperationKind
    start: int
    end: int
    params: dict = field(default_factory=dict)   # ex. {"salaire_brut_mensuel": 4800}


@dataclass(frozen=True)
class Station:
    """Un moment où l'on compare des lignes à partir du MÊME état."""
    id: str
    month: int
    question: str
    options: tuple[str, ...]          # ids des lignes comparées, A en premier
    axes: tuple[str, str]             # clés d'hypothèses pour la carte des frontières


@dataclass(frozen=True)
class Line:
    """Une ligne de métro = une politique : la suite des opérations choisies."""
    id: str
    name: str
    operations: tuple[Operation, ...]


@dataclass(frozen=True)
class Scenario:
    profile: Profile
    horizon_months: int
    lines: tuple[Line, ...]
    stations: tuple[Station, ...] = ()
    assumption_overrides: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class World:
    """w_t : les conditions extérieures d'un mois."""
    market_return_monthly: float = 0.0
    inflation_monthly: float = 0.0
    fx_chf_per_eur: float = 0.94
    job_lost: bool = False
    cost_index: float = 1.0      # prix des dépenses courantes par rapport aux salaires (1 = référence)
    rate_shift: float = 0.0      # hausse des taux : découvert et prêts à taux variable
    house_return_monthly: float = 0.0   # variation mensuelle du prix des logements
    student_job_lost: bool = False      # le job étudiant est perdu ce mois-ci (pour qui étudie avec un job)


@dataclass(frozen=True)
class Flow:
    """Une ligne du registre. `amount` = variation du solde du compte, dans sa devise."""
    month: int
    label: str
    category: Category
    account: Account
    amount: float
    currency: Currency
    amount_chf: float
    rule: str                    # clé de l'hypothèse ou de la règle qui a produit ce flux


@dataclass
class MonthRecord:
    month: int
    age: float
    opening_cash_chf: float
    closing_cash_chf: float
    placements_chf: float
    pilier2_chf: float
    debt_chf: float              # prêts + hypothèque + financement du découvert
    net_worth_chf: float
    flows: list[Flow]
    flags: list[str]             # ex. "financement_necessaire", "proprietaire"
    logement_chf: float = 0.0
    hypotheque_chf: float = 0.0
    overdraft_chf: float = 0.0   # financement du découvert en cours à la fin du mois (compris dans debt_chf)


@dataclass
class SimulationResult:
    line_id: str
    world_id: str
    months: list[MonthRecord]
    min_cash_chf: float                 # plus bas de (cash − financement du découvert)
    first_negative_month: int | None    # premier mois où un financement est nécessaire
    peak_financing_chf: float
    net_worth_end_chf: float


class Transition(Protocol):
    """Signature de F. Implémentée dans engine/transition.py."""
    def __call__(self, x: State, ops: tuple[Operation, ...], w: World,
                 theta: dict[str, float]) -> tuple[State, list[Flow]]: ...

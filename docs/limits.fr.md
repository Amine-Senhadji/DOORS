# Limites connues

Ce que le modèle ne fait pas, ou fait de façon simplifiée. Le tiroir « Hypothèses et preuves » affiche cette liste telle quelle.

- Chiffres suisses « [à vérifier] » non vérifiés (AVS, AC, LPP, LAMal, taxe UNIL, frais d'achat, valeur locative).
- Impôt : barème illustratif, pas le barème vaudois ; pas d'acomptes ; couple marié non modélisé.
- Chômage : durée d'indemnisation non plafonnée ; régime des personnes sortant des études non modélisé.
- 2e pilier : sans plafond de salaire coordonné ; retrait pour le logement non imposé à part.
- Logement : pas de revente ; valeur locative dont la suppression a été votée en 2025 (date à vérifier).
- Placements en CHF uniquement ; GBP et SGD approximés par l'EUR.
- Montants en CHF d'aujourd'hui (inflation nulle par convention, hausses de salaire réelles).
- Sept mondes nommés : le monde de référence, cinq crises reprises du catalogue et la perte du job étudiant (crise de l'équipe, durée de 6 mois par hypothèse, sans indemnité). L'âge de chaque crise se règle de 21 à 29 ans. Pas de Monte Carlo ni de crises calibrées sur données réelles ; le choc du franc de type 2015 n'est pas écrit.
- Crises combinées : un monde contient deux crises au plus (« krach@24+chomage_long@25 »), jamais trois. Là où les deux agissent sur la même grandeur le même mois, leurs écarts au monde de référence s'additionnent : c'est une convention, pas une loi mesurée ; deux pertes d'emploi qui se chevauchent n'en font qu'une. Rien ne dit à quelle fréquence deux crises arrivent ensemble. Un monde combiné n'est testé que sur demande : il ne fait pas partie des sept mondes affichés par défaut, ses âges ne se règlent pas à l'écran, et le tableau de valeur garde une crise par monde.
- À l'étranger, l'impôt est compris dans le prélèvement unique de 22 %, alors qu'en Suisse il s'ajoute au salaire net : cela avantage un peu la ligne de l'étranger.
- Blocs non traduits : doctorat, stage, indépendante, entreprise, pause, Zurich, Genève. Pas de plafond d'emprunt.
- Épargne constatée : une seule gare à la fois ; la même valeur est appliquée dans chaque monde testé ; l'écart avec l'épargne simulée est une ligne du registre, sans explication de sa cause. Le seuil du signal reste celui du trajet simulé.
- La valeur d'un diplôme au-delà de 30 ans n'est pas mesurée par les six objectifs ; comparer à 30 ans pénalise le master. À 30 ans, dans tous les mondes testés, le master abaisse les résultats financiers : sans choc, 3 objectifs sur 6 et 96'749 CHF avec le master de l'histoire A, 6 sur 6 et 175'904 CHF sans lui.
- Politiques : un seul seuil, sur une seule grandeur (ce qu'Alexia a de côté), à une seule date. Un choc qui arrive après la dernière date de décision ne se voit pas dans l'épargne (douze mois de chômage à 27 ans : les trois politiques suivent le plan, 1 objectif sur 6). Les seuils sont calibrés sur quatre mondes, pour un seul objectif (« Reconversion ») ; les zones qui fonctionnent sont étroites (2'600 CHF à 26 ans). Les variantes tirées au hasard sont des comptes, pas des fréquences attendues.
- Trois bandes : le « pire monde testé » ne vaut que pour les mondes testés ; le monde « prudent » ne change que le rendement des placements (un point de moins par an), qui pèse peu tant qu'Alexia a peu de placements. Aucune bande n'est une promesse.
- Alexia fragile ne diffère que par son épargne de départ (2'000 CHF au lieu de 8'000) : mêmes revenus, mêmes dépenses, mêmes seuils, calibrés sur Alexia.
- Règle répandue mise à l'épreuve : le coussin est compté sur le compte seul, sans placements à vendre ; « tenir » veut dire ne pas passer dans le rouge pendant 24 mois ; les dépenses courantes sont le logement, la vie courante et la santé, sans les frais d'études. Deux états seulement, à un seul âge (25 ans).
- Couche d'IA : le modèle propose des mondes ou des réglages et écrit des phrases ; il ne calcule rien. Le contrôleur vérifie que chaque chiffre d'un texte vient du moteur et du bon monde, et pour trois quantités (objectifs gardés, objectifs perdus, emprunt maximal) qu'il est à la bonne place. Il ne vérifie pas le raisonnement des mots autour des chiffres.
- « Trouver ce qui casse mon plan » : la recherche teste 40 mondes sur 49'140, elle peut donc manquer le plus dur. Le moteur simule lui-même les 315 crises seules et dit quand l'une d'elles est plus dure ; le balayage complet des 49'140 mondes n'existe que pour trois trajets, aux hypothèses inchangées.
- « Demande avec tes mots » : une phrase à la fois, lue dans les réglages que Doors a déjà. Un nombre est cherché dans la phrase, pas son rôle dans la phrase : c'est pourquoi chaque réglage est montré avant tout calcul.
- Hors du mode direct, les réponses du modèle sont des enregistrements, rejoués et contrôlés de nouveau sur le moteur : un trajet ou une phrase sans enregistrement n'a pas de réponse. La couche d'IA n'a pas encore été évaluée avec un vrai modèle dans ce dépôt : aucune réponse n'est enregistrée, et le banc d'essai de la recherche n'a tourné qu'avec un figurant.
- Données synthétiques : elles ne représentent pas la population suisse.

# Reconstruction des Gross Needs à partir des BOM SAP

**Approche à la granularité Part Number, fondée uniquement sur les données en amont du MRP**  
Version 1.0 — 13 août 2026  
Snapshot de référence des diagnostics historiques : 3 août 2026

---



## Résumé exécutif

**Résumé Exécutif :**

L'objectif est de produire une table de besoins bruts agrégée au niveau du **Part Number**, en recalculant les quantités depuis la demande amont et les nomenclatures SAP, sans utiliser les Planned Orders ni les Work Orders comme données d'entrée.

Ma conclusion est la suivante :

1. **Le calcul d'un besoin brut théorique issu de la demande et de la BOM est réalisable sans Planned Orders ni Work Orders.** Il faut partir des besoins indépendants, sélectionner une seule alternative de BOM, exploser récursivement la nomenclature, convertir les unités, puis agréger.
2. **La sélection de la bonne alternative de BOM est le point le plus critique.** Il ne faut jamais additionner toutes les alternatives ni choisir celle qui ressemble le plus aux Gross Needs observés.
3. Si une seule alternative est valide après application du système SAP, de l'usine, de l'usage, de la date, du statut et de l'effectivité, elle peut être sélectionnée avec le reason code `SINGLE_VALID_ALT`.
4. Si plusieurs alternatives restent possibles, la décision doit reproduire `MARC-ALTSL` : quantité/lot, date d'explosion, ou version de production `MKAL`. Une règle de quota ou une règle Airbus spécifique peut encore être nécessaire.
5. **Les données actuellement fournies ne suffisent pas encore à calculer toutes les quantités de façon déterministe en amont du MRP.** Il manque surtout la demande racine effective, les intervalles de lots de `MAST`, les attributs complets de `MKAL`, les états historiques complets `STKO`/`STAS`/`STPO`, les conversions `MARM`, ainsi que les règles de quota ou de sélection spécifiques lorsqu'elles existent.
6. La granularité publiée peut être le Part Number, mais le moteur doit travailler à une granularité beaucoup plus détaillée. Sinon il est impossible de sélectionner la bonne BOM, de gérer les dates et de diagnostiquer les écarts.
7. **Reproduire exactement un snapshot Gross Needs SAP est un objectif différent du besoin brut théorique.** L'exactitude au niveau SAP peut exiger une simulation du netting, du lot sizing, des stocks et des réceptions ouvertes. Sans ces états — et avec l'interdiction d'utiliser les PLO/WO — une égalité parfaite avec la table Gross Needs existante ne peut pas être garantie.

La recommandation principale est donc de construire d'abord un produit nommé par exemple **`BOM_GROSS_NEEDS_PRE_MRP`**, déterministe et auditable, puis de mesurer son écart à la table Gross Needs historique uniquement après le calcul.

```text
Demande amont
    |
    v
Sélection d'une seule BOM alternative
    |
    v
Explosion multi-niveaux + règles quantitatives
    |
    v
Conversion dans l'unité de base
    |
    v
Agrégation finale par Part Number
    |
    v
Comparaison aux Gross Needs historiques
        validation seulement, jamais règle de calcul
```

---

## 1. Objectif compris

### 1.1 Résultat métier attendu

Construire une table finale de la forme :

| Champ final | Rôle |
|---|---|
| `part_number` | Part Number du composant final |
| `base_uom` | Unité de base utilisée pour garantir une agrégation cohérente |
| `gross_need_qty_pre_mrp` | Quantité brute recalculée depuis la demande et la BOM |

Si l'unité de base est strictement unique et certifiée pour chaque Part Number, la clé métier affichée peut être limitée à `part_number`. En revanche, il ne faut jamais sommer des quantités `EA`, `ST`, `KG`, `M`, `L`, etc. sans normalisation préalable.

### 1.2 Contraintes non négociables

- Ne pas lire les Planned Orders comme données de calcul.
- Ne pas lire les Work Orders comme données de calcul.
- Ne pas récupérer `alternative_bom` depuis un PLO ou un WO.
- Ne pas récupérer la quantité réellement explosée depuis un composant PLO ou WO.
- Ne pas sélectionner une alternative parce qu'elle minimise l'écart aux Gross Needs.
- Utiliser seulement des données disponibles avant l'exécution du MRP : demande, paramètres MRP, BOM, versions de production, quotas, effectivité, unités et règles de configuration.
- Conserver les cas non résolus ; ne jamais les supprimer pour améliorer artificiellement un taux de correspondance.

### 1.3 Granularité publiée et granularité de calcul

La granularité finale demandée est simple. La granularité interne ne peut pas l'être.

```text
TABLE D'AUDIT INTERNE
sap_system + plant + mrp_area + demand_id + requirement_date
+ root_material + parent_material + selected_STLAL
+ bom_level + bom_path + component + component_uom
                         |
                         | agrégation après explosion complète
                         v
TABLE PUBLIÉE
part_number + base_uom + gross_need_qty_pre_mrp
```

Il faut notamment conserver `sap_system`, `WERKS`, la date, `STLAN`, `STLAL` et le chemin de BOM jusqu'à la dernière étape. Un même `MATNR` peut avoir une BOM différente selon le système, l'usine, l'usage et la date.

---

## 2. Deux objectifs à ne pas confondre

### 2.1 Cible A — besoin brut BOM théorique, 100 % amont MRP

Cette cible répond directement à la contrainte formulée :

> Demande indépendante × nomenclature sélectionnée = besoins composants théoriques.

Elle ne tient pas compte du stock disponible, des réceptions, du netting ni des propositions d'approvisionnement déjà créées.

### 2.2 Cible B — reproduction exacte de la table Gross Needs SAP

Une table Gross Needs dérivée de Planned Orders et Work Orders reflète non seulement la BOM, mais aussi les quantités de parents effectivement planifiées après :

- netting du stock et des réceptions ;
- lot sizing ;
- minimum, maximum, lot fixe et arrondis ;
- stock de sécurité ;
- horizon et time fence ;
- ordres ou éléments fermés ;
- calendriers et regroupements de besoins ;
- éventuelles règles de quota et de version de production.

```text
                         +-------------------------------+
Demande amont ---------->| Cible A : explosion BOM pure |----> besoin théorique
                         +-------------------------------+
            |
            | + stock + réceptions + paramètres MRP
            | + lot sizing + horizons + calendriers
            v
                         +-------------------------------+
                         | Cible B : mini-MRP simulé     |----> snapshot SAP attendu
                         +-------------------------------+
```

### 2.3 Recommandation de cadrage

Commencer par la **cible A**. Elle est explicable, compatible avec l'interdiction PLO/WO et utile pour analyser la demande structurelle issue de la BOM.

La cible B doit devenir une phase distincte. Elle nécessite tous les états MRP à une date donnée. Si les PLO/WO existants sont interdits même comme état initial, certains éléments de la situation SAP ne seront pas reconstructibles exactement.

---

## 3. Ce qui a été trouvé jusque-là

### 3.1 Baseline historique v69/v70

Sur le périmètre A320, MSN 12000–15000, avions non livrés, snapshot du 3 août 2026, la baseline couvre **58 610 405 clés Gross Needs** :

| Statut historique | Clés GN | Part des GN | Lecture |
|---|---:|---:|---|
| `EXACT_MEBOM_MATCH` | 24 115 257 | 41,15 % | Composant et quantité expliqués par la MEBOM sélectionnée |
| `QTY_DIFF` | 1 137 922 | 1,94 % | Composant trouvé, quantité différente |
| `MATERIAL_NOT_IN_MEBOM` | 18 572 138 | 31,69 % | Parent absent de la MEBOM visible |
| `COMPONENT_NOT_IN_SELECTED_BOM` | 14 785 088 | 25,23 % | Parent présent, composant absent de l'alternative retenue |
| **Total** | **58 610 405** | **100 %** | Population complète |

Parmi les 25 253 179 clés réellement comparables à la MEBOM, **95,49 %** ont déjà une quantité exacte. Le problème principal n'est donc pas uniquement la formule de quantité : il est surtout lié au périmètre de BOM visible, à l'alternative sélectionnée et à l'effectivité.

Ces résultats ont été produits avec des informations PLO/WO et servent uniquement de diagnostic historique. Ils ne doivent pas être réutilisés comme entrées du nouveau moteur amont MRP.

### 3.2 Résultats historiques v71 à v77

- En v71, environ **96 %** des parents absents de la MEBOM étaient associés à un lot-size différent de `E1`. C'est un signal structurel fort, mais pas une règle d'exclusion validée.
- En v73, la version de production n'était généralement pas disponible sur le header PLO générique ; cette voie n'a donc pas permis de retrouver l'alternative.
- En v75, une source PLO dédiée a permis de récupérer une alternative unique pour **1 183 714 ordres sur 1 183 862**, soit **99,9875 %**. Cela démontre que SAP avait bien effectué une sélection très déterministe en aval.
- En v76, sur 12 975 951 clés du sous-périmètre PLO/PR `E1`, 11 461 646 composants ont été retrouvés dans l'alternative MEBOM sélectionnée ; 10 495 407 avaient la quantité exacte, soit **91,57 %** des composants comparables.
- En v77, parmi les 966 239 cas `QTY_DIFF` de v76, **927 029**, soit **95,94 %**, avaient en réalité une quantité GN identique à la quantité du composant PLO effectivement explosé par SAP.
- Lorsque le composant PLO était disponible, la quantité GN correspondait à la quantité réellement explosée dans environ **99,67 %** des cas du sous-périmètre.
- Les premiers tests sur quantité fixe et scrap n'ont pas expliqué l'essentiel des `QTY_DIFF` résiduels.

Interprétation : la table GN historique semble généralement fidèle à l'explosion réellement faite par SAP. L'écart vient souvent de la difficulté à reconstruire **la même vue de BOM, la même alternative, la même effectivité et la même quantité de lot** à partir d'une MEBOM snapshot.

### 3.3 Profil de l'extrait MSN 13758

Les parquets fournis pour le MSN 13758 donnent le profil suivant :

| Objet | Mesure |
|---|---:|
| Lignes Gross Needs | 28 601 |
| Lignes GN d'origine `WO` | 15 565 |
| Lignes GN d'origine `PLO` | 13 036 |
| Lignes MEBOM | 65 703 |
| Occurrences parent/chemin analysées | 5 605 |
| Occurrences avec une seule alternative observée | 4 829 |
| Occurrences avec deux alternatives | 770 |
| Occurrences avec trois alternatives | 6 |
| Occurrences multi-alternatives | 776 |
| Lignes MEBOM sous une occurrence multi-alternatives | 27 645, soit 42,08 % |

La MEBOM de cet extrait est uniquement `sap_system = 'arp'`, alors que les Gross Needs contiennent également `apd`, `pgi`, `pda` et `spa`. Une réconciliation globale ne peut donc pas être complète avec cette seule MEBOM.

Un test volontairement naïf consistant à additionner toutes les alternatives MEBOM au niveau Part Number donne seulement 6 521 égalités exactes sur 17 209 couples `(part_number, uom)` observés dans GN. Ce chiffre n'est pas un KPI de performance. Il démontre surtout qu'il est interdit d'agréger avant d'avoir sélectionné exactement une alternative.

```text
Alternative 01 ---- composants ----+
                                    |
Alternative 02 ---- composants ----+--> SOMME NAÏVE --> surcomptage
                                    |
Alternative 03 ---- composants ----+

Bonne logique :

{01, 02, 03} -- règle SAP --> UNE alternative --> explosion --> agrégation
```

### 3.4 Conclusion issue des diagnostics

Les PLO/WO ont été utiles pour comprendre a posteriori ce que SAP avait choisi. Ils ont montré que la logique cible est déterministe dans la très grande majorité des cas. Mais la nouvelle solution doit retrouver cette décision **avant MRP**, à partir de `MARC`, `MKAL`, `MAST`, `STKO`, `STAS`, `STPO`, des règles de quota et de l'effectivité.

---

## 4. Modèle de données SAP recommandé

### 4.1 Vue d'ensemble

```text
DEMANDE RACINE
PBIM / PBED / PBID
VBBE / VBBS / VBEP selon stratégie
          |
          v
PARAMÈTRES MATÉRIAU ET MRP
MARC / MDMA / MARA
          |
          +----------------------------+
          |                            |
          v                            v
SÉLECTION DE BOM                  VERSION / QUOTA
MAST + STKO                       MKAL + QMAT/QUOT
          |                            |
          +-------------+--------------+
                        v
MEMBRES ET ITEMS DE BOM
STAS + STPO + AENR
                        |
                        v
QUANTITÉS ET UNITÉS
STKO-BMENG/BMEIN + STPO-MENGE/MEINS + MARM
                        |
                        v
EXPLOSION RÉCURSIVE ET AGRÉGATION PAR PART NUMBER
```

### 4.2 Demande amont du MRP

| Table SAP | Champs principaux | Utilité |
|---|---|---|
| `PBIM` | `BDZEI`, `MATNR`, `WERKS`, `VERSB`, `BEDAE` | En-tête/index des Planned Independent Requirements |
| `PBED` | `BDZEI`, `PDATU`, `PLNMG`, `ENTLI` | Dates et quantités des PIR |
| `PBID` | Clés PIR et MRP Area selon la version | Index des PIR par zone MRP |
| `PBHI` | Historique des PIR | Reconstruction historique si nécessaire |
| `VBBE` / `VBBS` | Matériau, usine, date, quantité ouverte selon modèle | Besoins individuels ou agrégés issus des ventes |
| `VBEP` | `VBELN`, `POSNR`, `ETENR`, dates et quantités | Échéances de commandes client lorsque la stratégie les rend pertinentes |
| `MAPR`, `PROP`, `PROW` | Paramètres et résultats de prévision | Sources de forecast ; elles ne deviennent une demande MRP qu'après transfert vers un besoin actif |

Le dossier SAP Airbus fourni mentionne également `MDPB` dans le contexte des besoins indépendants. Il faut vérifier le DDIC et l'extracteur de la release concernée avant de le considérer comme table autoritative.

Le point essentiel est d'identifier **la vraie demande racine utilisée par le MRP Airbus** : PIR, besoin client, besoin projet/WBS, besoin par MSN ou table Z. Les Gross Needs actuels ne peuvent pas jouer ce rôle, car ils sont précisément la sortie à reconstruire.

### 4.3 Paramètres matériau et MRP

| Table | Champs SAP | Rôle dans le calcul |
|---|---|---|
| `MARA` | `MATNR`, `MEINS` | Matériau et unité de base globale |
| `MARC` | `MATNR`, `WERKS`, `ALTSL` | Méthode de sélection de BOM |
| `MARC` | `DISMM`, `DISLS` | Type MRP et procédure de lot sizing |
| `MARC` | `BSTMI`, `BSTMA`, `BSTFE`, `BSTRF` | Lot minimum, maximum, fixe et valeur d'arrondi |
| `MARC` | `BESKZ`, `SOBSL` | Type et type spécial d'approvisionnement |
| `MARC` | `AUSSS`, `KAUSF` | Scrap d'assemblage et scrap composant selon release |
| `MARC` | `SBDKZ`, `SCHGT` | Besoins individuels/collectifs et bulk material |
| `MARC` | `EISBE`, `PLIFZ`, `DZEIT` | Stock de sécurité et délais utiles à une simulation MRP |
| `MDMA` | Données matériau par MRP Area | Paramètres spécifiques à la zone MRP lorsque activée |
| `T460A` ou customizing équivalent | Paramétrage lié à `SOBSL` | Interprétation du special procurement, dont les phantoms |

Dans le catalogue Foundry, la plupart de ces attributs apparaissent déjà dans le dataset `material_procurement`, notamment `selection_method`, `lot_size_materials_planning`, `minimum_lot_size`, `maximum_lot_size`, `fixed_lot_size`, `rounding_value_for_purchase_order_quantity`, `mrp_type`, `procurement_type`, `special_procurement_type`, `assembly_scrap_in_percent`, `component_scrap_in_percent` et `is_bulk_material`.

### 4.4 Structure de la BOM

| Table SAP | Champs essentiels | Rôle |
|---|---|---|
| `MAST` | `MATNR`, `WERKS`, `STLAN`, `STLNR`, `STLAL`, `LOSVN`, `LOSBS` | Affectation matériau/usine/usage vers BOM et intervalle de lot de l'alternative |
| `STKO` | `STLTY`, `STLNR`, `STLAL`, `STKOZ`, `DATUV`, `AENNR`, `BMENG`, `BMEIN`, `STLST`, `LOEKZ`, `LKENZ` | En-tête, validité, quantité de base, unité et statut |
| `STAS` | `STLTY`, `STLNR`, `STLAL`, `STLKN`, `STASZ`, `DATUV`, `AENNR`, `LKENZ` | Affectation des nœuds/items à une alternative précise |
| `STPO` | `STLTY`, `STLNR`, `STLKN`, `STPOZ`, `POSNR`, `IDNRK`, `POSTP`, `MENGE`, `MEINS` | Items et quantités de la BOM |
| `STPO` | `FMENG`, `AUSCH`, `AVOAU`, `NETAU` | Quantité fixe et paramètres de scrap |
| `STPO` | `ALPGR`, `ALPRF`, `ALPST`, `EWAHR` | Groupe, priorité, stratégie et probabilité des alternative items |
| `STPO` | `KZAUS`, `NFEAG`, `STLKZ`, `LKENZ` | Discontinuation, follow-up, assemblage et suppression |
| `AENR` | `AENNR`, `DATUV`, `AETXT`, `AEGRU` | Change master et date d'effet |

`STAS` est indispensable. Un `STLNR` peut contenir des nœuds partagés entre alternatives ; joindre `MAST` directement à tous les `STPO` du même `STLNR` risque d'associer des composants à la mauvaise `STLAL`.

```text
MAST
(MATNR, WERKS, STLAN, STLNR, STLAL)
                    |
                    v
STKO                STAS
(STLNR, STLAL) ---> (STLNR, STLAL, STLKN)
                                      |
                                      v
STPO
(STLNR, STLKN, STPOZ, IDNRK, MENGE)

Règle : l'appartenance de l'item à STLAL passe par STAS.
```

### 4.5 Versions de production et quotas

| Table SAP | Champs essentiels | Rôle |
|---|---|---|
| `MKAL` | `MATNR`, `WERKS`, `VERID` | Clé de version de production |
| `MKAL` | `ADATU`, `BDATU` | Intervalle de validité temporelle |
| `MKAL` | `BSTMI`, `BSTMA` | Intervalle de quantité de la version |
| `MKAL` | `STLAN`, `STLAL` | BOM usage et alternative sélectionnée |
| `MKAL` | `PLNTY`, `PLNNR`, `ALNAL` | Affectation gamme/routing |
| `MKAL` | `MKSP` | Statut de blocage selon release |
| `QMAT`, `QUOT` | Matériau, usine, quota, item de quota, version et quote-part | Arbitrage ou répartition quand plusieurs sources/versions sont valides |

Les noms exacts des champs de quota doivent être confirmés dans `SE11` pour la release utilisée. Une règle Airbus spécifique, par exemple une table de correspondance ligne/station vers version de production, doit être extraite si elle intervient réellement dans le MRP.

### 4.6 Unités de mesure

| Table | Champs | Rôle |
|---|---|---|
| `MARA` | `MATNR`, `MEINS` | Unité de base du matériau |
| `MARM` | `MATNR`, `MEINH`, `UMREZ`, `UMREN` | Conversion d'une unité alternative vers l'unité de base |
| `T006` | Unité et nombre de décimales | Contrôle d'arrondi et de précision |

---

## 5. Logique de sélection d'une BOM alternative

### 5.1 Construire d'abord le jeu d'alternatives valides

Pour un parent donné, le moteur doit filtrer dans cet ordre :

1. même `sap_system` ;
2. même `MATNR` ;
3. même `WERKS` ;
4. bon usage `STLAN` ;
5. BOM non supprimée et non archivée ;
6. statut `STKO-STLST` autorisé pour l'explosion ;
7. date d'explosion compatible avec `STKO-DATUV`, le change number `AENNR` et la validité de fin exposée par l'extracteur ;
8. effectivité avion/MSN si la MEBOM Airbus ajoute une contrainte de configuration ;
9. intervalle de lot ou version de production selon `MARC-ALTSL`.

```text
Toutes les BOM du MATNR
          |
          v
SAP_SYSTEM + WERKS + STLAN
          |
          v
Statut + suppression + validité date/change
          |
          v
Effectivité MSN / configuration Airbus
          |
          v
Nombre d'alternatives encore valides
       /          |           \
      0           1           >1
      |           |            |
NO_VALID_BOM  SINGLE_VALID_ALT  MARC-ALTSL
```

La règle « une seule alternative dans la BOM » doit donc signifier **une seule alternative valide dans le contexte**, et non une seule valeur observée dans un snapshot incomplet.

### 5.2 Arbre de décision `MARC-ALTSL`

| `MARC-ALTSL` | Méthode standard | Données nécessaires | Sortie recommandée |
|---|---|---|---|
| vide | Sélection par quantité d'ordre/lot | `MAST-LOSVN`, `MAST-LOSBS` et quantité de lot | `QTY_RANGE_SELECTED` |
| `1` | Sélection par date d'explosion | `STKO-DATUV`, `AENR`, historique et date d'explosion | `EXPLOSION_DATE_SELECTED` |
| `2` | Sélection par version de production, avec fallback quantité si aucune version adaptée | `MKAL` complet, puis intervalles `MAST` | `PV_UNIQUE_VALID` ou `QTY_RANGE_SELECTED` |
| `3` | Sélection uniquement par version de production | `MKAL` complet | `PV_UNIQUE_VALID` ou exception |

Cette table décrit la logique standard documentée par SAP ; il faut confirmer la correspondance de `selection_method` vers `MARC-ALTSL` dans l'extracteur Airbus.

```text
Plusieurs STLAL valides
          |
          v
Lire MARC-ALTSL
   |
   +-- vide --> calculer quantité de lot --> MAST-LOSVN/LOSBS
   |
   +-- 1 ----> appliquer date d'explosion --> STKO/AENR
   |
   +-- 2 ----> chercher MKAL valide
   |               |
   |               +-- trouvé --> MKAL-STLAL
   |               +-- absent --> fallback intervalle de lot
   |
   +-- 3 ----> chercher MKAL valide
                   |
                   +-- trouvé --> MKAL-STLAL
                   +-- absent --> NO_VALID_PRODUCTION_VERSION
```

### 5.3 Quantité de sélection et lot sizing

Le cas `ALTSL` vide est plus difficile qu'il n'y paraît. La quantité utilisée par SAP pour choisir l'intervalle `MAST-LOSVN`/`MAST-LOSBS` peut être la quantité de lot résultant du MRP, pas simplement le besoin brut du parent.

```text
Besoins datés du parent
          |
          v
Netting et regroupement de période
          |
          v
MARC-DISLS + BSTMI/BSTMA/BSTFE/BSTRF
          |
          v
Quantité de lot Q_select
          |
          v
MAST-LOSVN <= Q_select <= MAST-LOSBS
          |
          v
STLAL sélectionnée
```

Sans mini-calcul de lot sizing, deux comportements sont possibles :

- si une seule alternative reste valide indépendamment de la quantité, la sélection est déterministe ;
- si plusieurs intervalles sont possibles, classer `ALT_UNRESOLVED_LOT_QTY` plutôt que d'utiliser une quantité GN ou de choisir arbitrairement.

Utiliser la quantité brute du parent comme proxy ne doit être autorisé que par une règle métier explicite, avec un reason code distinct tel que `QTY_RANGE_PARENT_GROSS_PROXY`.

### 5.4 Sélection par version de production `MKAL`

Une version candidate doit au minimum satisfaire :

- `MKAL-MATNR = parent_material` ;
- `MKAL-WERKS = plant` ;
- date d'explosion comprise entre `MKAL-ADATU` et `MKAL-BDATU` ;
- quantité de sélection comprise entre `MKAL-BSTMI` et `MKAL-BSTMA` ;
- version non bloquée selon `MKAL-MKSP` ;
- `MKAL-STLAN` et `MKAL-STLAL` présents et compatibles avec la BOM.

```text
MKAL du MATNR/WERKS
          |
          v
Filtre ADATU/BDATU + BSTMI/BSTMA + MKSP
          |
       nombre de VERID
       /       |       \
      0        1       >1
      |        |        |
fallback   MKAL-STLAL   QMAT/QUOT ou règle Airbus
ALTSL=2                 |
ou erreur               +-- décision unique --> STLAL
ALTSL=3                 +-- ambiguïté --> ALT_UNRESOLVED_MULTIPLE_PV
```

Si plusieurs versions sont valides, il ne faut pas choisir la première par ordre lexical de `VERID`. Il faut vérifier les quotas `QMAT`/`QUOT`, une règle de ligne/station ou un autre paramétrage de sélection.

### 5.5 Alternative BOM et alternative item : deux logiques différentes

- `MAST-STLAL` / `STKO-STLAL` désigne une **alternative de BOM complète**.
- `STPO-ALPGR`, `ALPRF`, `ALPST`, `EWAHR` décrit des **alternative items à l'intérieur d'une BOM**.

```text
Alternative BOM STLAL = 02
          |
          +-- item normal A
          +-- item normal B
          +-- groupe d'alternative ALPGR = X
                    |
                    +-- composant C, priorité/probabilité
                    +-- composant D, priorité/probabilité
```

Sélectionner `STLAL = 02` ne signifie pas qu'il faut sommer C et D. La stratégie `ALPST`, la priorité `ALPRF` et la probabilité `EWAHR` doivent être appliquées selon le comportement d'explosion configuré.

---

## 6. Reconstruction de l'état historique de la BOM

La BOM doit être reconstruite à la date de calcul, et pas seulement lue dans son état courant.

```text
Date de besoin du parent
          |
          v
Calcul de la date d'explosion
          |
          v
STKO-DATUV + AENR-DATUV + statut/suppression
          |
          v
STAS : nœuds appartenant à la STLAL à cette date
          |
          v
STPO : version valide de chaque item
          |
          v
Effectivité MSN / configuration industrielle
```

Points de contrôle :

- gérer les change numbers `AENNR` ;
- respecter les flags de suppression `LOEKZ`/`LKENZ` ;
- ne pas prendre simultanément plusieurs états `STKOZ`, `STASZ` ou `STPOZ` ;
- utiliser la date d'effet et, si disponible, la date de fin de validité de l'extracteur ;
- appliquer l'effectivité MSN séparément de la seule validité calendaire ;
- conserver un reason code si l'état historique ne peut pas être reconstruit.

Une MEBOM dénormalisée avec `component_quantity_path` peut accélérer le calcul, mais uniquement si elle expose déjà la bonne `STLAL`, l'état temporel correct et l'effectivité avion. Sinon elle ne remplace pas les objets `MAST`/`STKO`/`STAS`/`STPO` nécessaires à l'audit.

---

## 7. Calcul des quantités

### 7.1 Item proportionnel

Pour un item proportionnel, la formule nominale de base est :

```text
q_child_nominal = q_parent * STPO-MENGE / STKO-BMENG
```

où :

- `q_parent` est la quantité du parent dans l'unité compatible avec `STKO-BMEIN` ;
- `STKO-BMENG` est la quantité de base de la BOM ;
- `STPO-MENGE` est la quantité composant ;
- `STPO-MEINS` est l'unité de cette quantité composant.

Oublier `STKO-BMENG` est une cause classique de facteur multiplicatif erroné.

### 7.2 Item à quantité fixe

Lorsque `STPO-FMENG` indique une quantité fixe, la quantité n'est pas simplement multipliée par `q_parent`. Elle s'applique selon la sémantique de quantité fixe de l'explosion et le nombre de lots.

```text
Item proportionnel : q_parent augmente --> q_child augmente proportionnellement

Item fixe FMENG    : quantité par explosion/lot
                     x nombre de lots calculés
```

Le nombre de lots peut dépendre de `MARC-DISLS`, `BSTMI`, `BSTMA`, `BSTFE` et `BSTRF`. Si ce nombre n'est pas déterminable en amont, la quantité exacte d'un item fixe doit être marquée comme non résolue.

### 7.3 Scrap et arrondis

Les champs à considérer sont notamment :

- scrap d'assemblage : `MARC-AUSSS` ;
- scrap composant : `MARC-KAUSF` ou champ équivalent de la release ;
- scrap item BOM : `STPO-AUSCH` ;
- operation scrap : `STPO-AVOAU` ;
- net scrap indicator : `STPO-NETAU` ;
- unité et décimales : `MARM`, `T006` ;
- arrondi de lot : `MARC-BSTRF`.

Il ne faut pas multiplier aveuglément tous les pourcentages. `NETAU` et les règles d'operation scrap changent la combinaison. La séquence exacte doit être validée sur quelques cas SAP connus, puis figée dans une règle versionnée.

### 7.4 Conversion d'unité

Pour une quantité exprimée dans `MARM-MEINH`, une conversion standard vers `MARA-MEINS` utilise le ratio `MARM-UMREZ / MARM-UMREN`, sous réserve de validation dans la release :

```text
q_component dans STPO-MEINS
          |
          v
Chercher MARM(MATNR, MEINH = STPO-MEINS)
          |
          v
q_base = q_component * UMREZ / UMREN
          |
          v
Arrondir selon unité/règle SAP
          |
          v
Sommer seulement dans MARA-MEINS
```

Si une conversion manque, ne pas convertir par hypothèse ; utiliser `UOM_UNRESOLVED`.

### 7.5 Multiplication multi-niveaux

À chaque niveau, la quantité du composant devient la quantité parent du niveau suivant, après sélection de sa propre BOM et de sa propre alternative.

```text
Demande A = 10 EA
 |
 +-- BOM A : 2 B / A  --> besoin B = 20
 |                         |
 |                         +-- BOM B : 3 C / B --> besoin C = 60
 |
 +-- BOM A : 4 D / A  --> besoin D = 40

Résultat final par Part Number :
B = 20, C = 60, D = 40
```

Dans un cas réel, les ratios doivent utiliser `STKO-BMENG`, les unités doivent être converties et chaque niveau doit refaire sa propre sélection de `STLAL`.

---

## 8. Récursion, procurement et phantoms

Le moteur doit décider si un composant est une feuille ou un parent à exploser à son tour.

```text
Composant IDNRK
       |
       v
BOM valide comme parent ? ---- non ----> feuille : accumuler le besoin
       |
      oui
       |
       v
Lire MARC-BESKZ / SOBSL et customizing T460A
       |
       +-- phantom ----> exploser immédiatement, sans stock intermédiaire
       |
       +-- in-house ---> sélectionner sa BOM puis exploser
       |
       +-- externe ----> généralement feuille, sauf règle spéciale
       |
       +-- ambigu -----> PROCUREMENT_RULE_UNRESOLVED
```

Il faut également :

- gérer les composants bulk via `MARC-SCHGT`/indicateur item ;
- détecter les cycles de BOM ;
- fixer une profondeur maximale de sécurité ;
- conserver le chemin complet ;
- ne pas doubler un nœud à cause d'une jointure `STAS`/`STPO` incorrecte ;
- distinguer la présence d'une sous-BOM de la décision métier de l'exploser.

---

## 9. Architecture de données recommandée

### 9.1 Tables intermédiaires

| Table logique | Contenu principal |
|---|---|
| `pre_mrp_demand_root_v1` | Demandes racines avec `demand_id`, `MATNR`, `WERKS`, date, quantité et UOM |
| `material_mrp_context_v1` | `MARC`/`MDMA`, dont `ALTSL`, lot sizing, procurement et scrap |
| `bom_alt_candidates_v1` | Alternatives candidates après filtres système/usine/usage/date/effectivité |
| `bom_alt_selection_v1` | Une ligne par parent/événement avec `selected_STLAL`, reason code et candidate count |
| `bom_effective_items_v1` | Items obtenus via `STAS`/`STPO` dans l'état historique valide |
| `bom_explosion_audit_v1` | Une ligne par chemin et niveau, avant agrégation |
| `bom_gross_needs_part_number_v1` | Résultat final par `part_number` et unité de base |
| `bom_gross_needs_exceptions_v1` | Cas non résolus, sans suppression silencieuse |

```text
pre_mrp_demand_root_v1
          |
          v
bom_alt_candidates_v1 ---> material_mrp_context_v1
          |
          v
bom_alt_selection_v1
          |
          v
bom_effective_items_v1
          |
          v
bom_explosion_audit_v1 -- boucle niveau N --> niveau N+1
          |
          +----------------------+
          |                      |
          v                      v
bom_gross_needs_          bom_gross_needs_
part_number_v1            exceptions_v1
```

### 9.2 Colonnes d'audit minimales

La table `bom_alt_selection_v1` devrait contenir au minimum :

- `sap_system` ;
- `plant` / `WERKS` ;
- `mrp_area` si applicable ;
- `demand_id` ;
- `requirement_date` et `explosion_date` ;
- `parent_material` / `MATNR` ;
- `parent_requirement_qty` et UOM ;
- `bom_usage` / `STLAN` ;
- `candidate_alt_count` ;
- `selection_method` / `MARC-ALTSL` ;
- `production_version` / `MKAL-VERID` si utilisée ;
- `selected_alternative_bom` / `STLAL` ;
- `selection_reason_code` ;
- `selection_confidence` ;
- `source_snapshot_date`.

### 9.3 Reason codes recommandés

| Reason code | Signification |
|---|---|
| `SINGLE_VALID_ALT` | Une seule alternative reste valide après tous les filtres |
| `PV_UNIQUE_VALID` | Une seule version `MKAL` valide sélectionne la BOM |
| `PV_QUOTA_SELECTED` | Version choisie par quota validé |
| `QTY_RANGE_SELECTED` | Intervalle `MAST-LOSVN/LOSBS` unique |
| `EXPLOSION_DATE_SELECTED` | Alternative sélectionnée par la date |
| `CUSTOM_LINE_SELECTED` | Règle Airbus ligne/station démontrée |
| `NO_VALID_BOM` | Aucune BOM valide |
| `NO_VALID_PRODUCTION_VERSION` | `ALTSL=3` et aucune version valide |
| `ALT_UNRESOLVED_MULTIPLE` | Plusieurs alternatives restent possibles |
| `ALT_UNRESOLVED_LOT_QTY` | Quantité de lot nécessaire mais non déterminable |
| `ALT_UNRESOLVED_MULTIPLE_PV` | Plusieurs versions valides sans règle d'arbitrage |
| `EFFECTIVITY_UNRESOLVED` | Effectivité date/MSN non reconstructible |
| `BOM_ITEM_VALID` | Item BOM retenu |
| `BOM_ITEM_DELETED_OR_NOT_EFFECTIVE` | Item exclu pour suppression ou validité |
| `UOM_UNRESOLVED` | Conversion d'unité absente |
| `PROCUREMENT_RULE_UNRESOLVED` | Décision d'explosion du composant indéterminée |

Chaque demande et chaque nœud d'explosion doivent terminer dans exactement un statut final.

---

## 10. Données disponibles et données manquantes

### 10.1 Ce qui est déjà disponible

- Un extrait Gross Needs du MSN 13758.
- Un extrait MEBOM multi-niveaux du MSN 13758.
- Des PLO/WO et composants associés, utilisables comme échantillon historique de validation mais désormais exclus des entrées.
- Les diagnostics SQL v68 à v78.
- Le dataset Foundry `material_procurement` et son catalogue de champs.
- Un dataset de versions de production identifié.
- Un dataset d'en-tête BOM avec quantité de base et validité identifié.
- Une MEBOM avec informations MSN/effectivité identifiée.
- Des documents SAP de forecasting et d'analyse des retards matière.

### 10.2 Ce qui manque pour un moteur amont MRP déterministe

| Priorité | Donnée requise | Tables/champs attendus | Situation actuelle |
|---:|---|---|---|
| 1 | Demande racine réellement consommée par le MRP | `PBIM`, `PBED`, `PBID`, `VBBE`/`VBBS`, `VBEP` ou tables Z/MSN | Non fournie dans les parquets actuels |
| 1 | Intervalles de lot des alternatives | `MAST-LOSVN`, `MAST-LOSBS` | Non exposés dans le dataset BOM header actuellement identifié |
| 1 | Versions de production complètes | `MKAL-VERID`, `ADATU`, `BDATU`, `BSTMI`, `BSTMA`, `STLAN`, `STLAL`, `MKSP` | Dataset identifié, couverture complète à confirmer |
| 1 | Appartenance des items par alternative | `STAS` historique complet | Non démontrée dans les données fournies |
| 1 | Items et règles quantitatives | `STPO` historique avec `MENGE`, `MEINS`, `FMENG`, scraps, alternative items | Partiellement visible via MEBOM, pas complet au format standard |
| 1 | En-têtes historiques | `STKO` avec `BMENG`, `BMEIN`, `DATUV`, `AENNR`, statut et suppression | Dataset identifié, historique exact à confirmer |
| 1 | Paramètres MRP par matériau/usine | `MARC-ALTSL`, `DISLS`, `BSTMI/BSTMA/BSTFE/BSTRF`, `BESKZ`, `SOBSL` | Champs catalogués ; données cibles à extraire |
| 1 | Conversions d'unité | `MARA-MEINS`, `MARM-MEINH/UMREZ/UMREN`, éventuellement `T006` | Non fournies |
| 1 | BOM pour tous les systèmes SAP | ARP, APD, PGI, PDA, SPA | MEBOM MSN 13758 limitée à ARP |
| 2 | Quotas et arbitrage de versions | `QMAT`, `QUOT` | Non fournis |
| 2 | Règles Airbus ligne/station/configuration | Table Z ou data product effectif | Existence supposée, activation non prouvée |
| 2 | Change master/effectivité complète | `AENR` et effectivité MSN | Partiellement identifiée, couverture à confirmer |
| 3 | États de netting pour une cible exacte | Stocks, réceptions ouvertes, calendriers, horizons, sécurité | Non fournis ; nécessaires seulement à la cible B |

### 10.3 Extraction minimale à demander

Toutes les extractions doivent ajouter `sap_system` et une date de snapshot, même si ces champs ne font pas partie de la clé SAP native.

| Objet | Champs minimum |
|---|---|
| Demande | `demand_id`, `MATNR`, `WERKS`, MRP Area, type de besoin, date, quantité, UOM, version/statut actif |
| `MARC` | `MATNR`, `WERKS`, `ALTSL`, `DISMM`, `DISLS`, `BSTMI`, `BSTMA`, `BSTFE`, `BSTRF`, `BESKZ`, `SOBSL`, `AUSSS`, `KAUSF`, `SBDKZ`, `SCHGT` |
| `MAST` | `MATNR`, `WERKS`, `STLAN`, `STLNR`, `STLAL`, `LOSVN`, `LOSBS` |
| `STKO` | `STLTY`, `STLNR`, `STLAL`, `STKOZ`, `DATUV`, `AENNR`, `BMENG`, `BMEIN`, `STLST`, `LOEKZ`, `LKENZ` |
| `STAS` | `STLTY`, `STLNR`, `STLAL`, `STLKN`, `STASZ`, `DATUV`, `AENNR`, `LKENZ` |
| `STPO` | `STLTY`, `STLNR`, `STLKN`, `STPOZ`, `POSNR`, `IDNRK`, `POSTP`, `MENGE`, `MEINS`, `FMENG`, `AUSCH`, `AVOAU`, `NETAU`, `ALPGR`, `ALPRF`, `ALPST`, `EWAHR`, `LKENZ` |
| `MKAL` | `MATNR`, `WERKS`, `VERID`, `ADATU`, `BDATU`, `BSTMI`, `BSTMA`, `STLAN`, `STLAL`, `PLNTY`, `PLNNR`, `ALNAL`, `MKSP` |
| Unités | `MARA-MATNR/MEINS`, `MARM-MATNR/MEINH/UMREZ/UMREN` |
| Change master | `AENR-AENNR/DATUV` et attributs d'effectivité disponibles |
| Quotas/custom | Clés matériau/usine/date/quantité, version/BOM cible, priorité ou quote-part |

---

## 11. Plan recommandé

### Phase 0 — figer la cible

Valider que la première livraison est la cible A : besoin brut BOM théorique amont MRP. Définir la population racine exacte, le snapshot, les systèmes SAP, les usines, les usages BOM et la date d'explosion.

### Phase 1 — construire le contrat de données

Extraire les tables listées ci-dessus. Vérifier la couverture par `sap_system`, `WERKS` et `MATNR`. Confirmer dans `SE11` les champs dont le nom peut varier selon la release ou l'extracteur.

### Phase 2 — pilote mono-niveau sur MSN 13758

1. Restreindre aux parents dont une seule alternative valide existe.
2. Sélectionner `STLAL` sans lire GN/PLO/WO.
3. Calculer `STPO-MENGE / STKO-BMENG`.
4. Convertir via `MARM`.
5. Comparer au GN historique après calcul.

### Phase 3 — cas multi-alternatives

Implémenter séparément :

1. `ALTSL=1` par date ;
2. `ALTSL=2/3` par `MKAL` ;
3. `ALTSL` vide par quantité de lot ;
4. quota `QMAT`/`QUOT` ;
5. règles Airbus spécifiques ;
6. reason codes non résolus.

### Phase 4 — explosion multi-niveaux

Ajouter la récursion, les phantoms, le procurement, la quantité fixe, les scraps, les alternative items, l'effectivité historique et la détection de cycles.

### Phase 5 — publication au niveau Part Number

Normaliser toutes les unités, agréger seulement après explosion complète, puis produire :

- `bom_gross_needs_part_number_v1` ;
- `bom_gross_needs_exceptions_v1` ;
- `bom_alt_selection_audit_v1`.

### Phase 6 — validation indépendante

Comparer ensuite aux Gross Needs gelés. La table GN ne doit être jointe qu'au dernier stade.

```text
CALCUL                                                   VALIDATION
Demande + MARC/MKAL + MAST/STKO/STAS/STPO + MARM
                         |
                         v
                  Résultat calculé -----------+
                                               |
                                               v
Gross Needs historique --------------------> comparaison

Interdit : Gross Needs --> choix de STLAL ou correction de quantité
```

### Phase 7 — mini-MRP uniquement si nécessaire

Si l'objectif devient l'égalité exacte avec le snapshot SAP, ajouter un moteur séparé de netting et lot sizing avec les états de stock, réceptions, calendriers et horizons. Cette phase ne doit pas dégrader la traçabilité de la cible A.

---

## 12. Contrôles d'acceptation

Le moteur devrait satisfaire les contrôles suivants :

1. **Aucune dépendance PLO/WO** dans les tables d'entrée du calcul.
2. **Aucune utilisation des GN** avant la phase de validation.
3. Une et une seule décision par parent, date et contexte : alternative sélectionnée ou reason code d'échec.
4. `candidate_alt_count` disponible avant et après chaque filtre.
5. Aucun `STPO` rattaché à une `STLAL` sans passage par `STAS` ou équivalent démontré.
6. `STKO-BMENG` non nul pour tout ratio proportionnel.
7. 100 % des quantités agrégées dans une unité de base certifiée.
8. 100 % des lignes initiales classées : expliqué ou exception explicite.
9. Conservation du chemin et du niveau pour permettre un drill-down depuis un Part Number final.
10. Contrôle de non-duplication à chaque jointure.
11. Contrôle des cycles et de la profondeur maximale.
12. Reproductibilité avec le même snapshot et les mêmes paramètres.

Les KPI doivent être séparés :

- taux de sélection déterministe de `STLAL` ;
- taux d'items avec état historique résolu ;
- taux de conversion UOM ;
- taux de quantité calculable ;
- taux de correspondance stricte au GN de validation ;
- taux d'exceptions, par reason code ;
- couverture de classification, qui doit atteindre 100 %.

---

## 13. Risques principaux

| Risque | Conséquence | Réponse recommandée |
|---|---|---|
| Agrégation des alternatives avant sélection | Surcomptage massif | Sélectionner une seule `STLAL` avant toute somme |
| `MATNR` utilisé seul comme clé | Mélange de systèmes/usines/usages | Garder `sap_system`, `WERKS`, `STLAN`, date |
| Oubli de `STAS` | Composants attribués à la mauvaise alternative | Joindre par les nœuds de l'alternative |
| Utilisation de la quantité GN pour choisir une BOM | Fuite de cible et résultat non auditable | GN réservé à la validation finale |
| Quantité parent utilisée comme lot SAP sans justification | Mauvais intervalle `LOSVN/LOSBS` | Simuler le lot sizing ou déclarer non résolu |
| MEBOM limitée à ARP | Faux manquants pour APD/PGI/PDA/SPA | Extraire la BOM de chaque système |
| Snapshot courant utilisé pour une date historique | Faux composants/quantités | Reconstruire l'état `STKO`/`STAS`/`STPO` à date |
| Somme de plusieurs UOM | Quantité sans signification | Convertir via `MARM` avant agrégation |
| Règle custom non extraite | Sélection ambiguë malgré `MKAL` | Identifier et versionner la table Z/règle |
| Objectif exact confondu avec BOM théorique | Attente impossible à tenir | Séparer cible A et cible B |

---

## 14. Recommandation finale

Je recommande de lancer la construction avec la règle suivante :

1. partir d'une demande racine SAP certifiée ;
2. former les candidates `MAST`/`STKO` valides à la date et pour le MSN ;
3. si une seule `STLAL` reste, la prendre ;
4. si plusieurs restent, appliquer `MARC-ALTSL` ;
5. pour `ALTSL=2/3`, filtrer `MKAL` par date, quantité et statut, puis appliquer quota/custom si nécessaire ;
6. pour la sélection par quantité, utiliser un lot calculé depuis les paramètres MRP ou laisser le cas non résolu ;
7. récupérer les items par `STAS` puis `STPO` ;
8. calculer les quantités avec `STKO-BMENG`, `STPO-MENGE`, quantité fixe, scrap et règles d'arrondi ;
9. convertir via `MARM` ;
10. exploser récursivement ;
11. agréger par Part Number seulement à la fin ;
12. comparer ensuite au GN gelé.

Le premier livrable ne devrait pas prétendre reproduire à l'identique le snapshot GN. Il devrait annoncer clairement :

> **Besoins bruts théoriques issus de la demande amont et des BOM SAP sélectionnées, avant netting MRP.**

À ce stade, les deux informations les plus urgentes à obtenir sont :

1. la table exacte de demande racine, avec quantité et date ;
2. les extraits complets `MAST` et `MKAL`, notamment les intervalles de quantité et la validité.

Sans ces données, il est possible de traiter proprement les cas à alternative unique, mais pas de résoudre honnêtement tous les cas multi-alternatives.

---

## Annexe A — Datasets Foundry identifiés

| Objet | Resource ID | Usage dans la nouvelle approche |
|---|---|---|
| Gross Needs historique | `ri.foundry.main.dataset.9a23f7f5-51aa-439e-b608-039849b86475` | Validation finale uniquement |
| MEBOM historique | `ri.foundry.main.dataset.6adc8752-20ec-4f38-920c-313942cd1280` | BOM dénormalisée/contrôle d'effectivité |
| Material procurement / vue `MARC` | `ri.foundry.main.dataset.c2174dfe-ca0e-46da-8e6e-ef89e495a1a7` | Entrée autorisée |
| Versions de production / vue `MKAL` | `ri.foundry.main.dataset.62d7303d-743d-4655-82f5-42a54cb96080` | Entrée autorisée |
| En-tête BOM, quantité de base, validité | `ri.foundry.main.dataset.9c10c58b-d850-4d0c-b199-c73e3559a6fe` | Entrée autorisée, champs de lots à compléter |
| MEBOM MSN/effectivité | `ri.foundry.main.dataset.cf7ad1df-1ed8-4399-a389-3e96f9d23281` | Entrée autorisée si elle représente bien l'amont |
| Routing Components | `ri.foundry.main.dataset.a513dde7-2049-437c-add7-bdb1fc180396` | Complément éventuel pour operation scrap/allocation |
| Header demande/ordre générique | `ri.foundry.main.dataset.3934bbcd-6c82-4437-8621-6e46c2180a12` | Exclu si PLO/WO |
| Header PLO dédié | `ri.foundry.main.dataset.0b2b4308-05d3-426f-913d-d8d34f7a1766` | Validation historique uniquement, exclu du calcul |
| Composants PLO | `ri.foundry.main.dataset.83afbf07-e51d-49a9-a6d1-7c14f0873318` | Validation historique uniquement, exclu du calcul |

---

## Annexe B — Sources du projet consultées

- `01-PROMPT_REPRISE_BOM_GROSS_NEEDS_V2_2026-08-07-1.md`
- `BOM_Demand_reconciliation_v68_A320_MSN_12000_15000_all_materials.sql`
- `BOM_Demand_reconciliation_v69_A320_MSN_12000_15000_NON_DELIVERED_all_materials.sql`
- `BOM_GN_diagnostic_funnel_v70_A320_MSN_12000_15000.sql`
- `BOM_GN_diagnostic_v71_missing_profiles_time_horizon.sql`
- `BOM_GN_diagnostic_v72_E1_time_order_alt.sql`
- `BOM_GN_diagnostic_v73_PLO_E1_production_version_recovery.sql`
- `BOM_GN_diagnostic_v75_direct_PLO_header_explosion_lotsize.sql`
- `BOM_GN_diagnostic_v76_direct_PLO_alt_reconciliation.sql`
- `BOM_GN_diagnostic_v77_PLO_component_quantity_rules.sql`
- `BOM_GN_diagnostic_v78_PLO_vs_MEBOM_quantity_factor.sql`
- `BOM_Gross_Needs_Statut_Projet_2026-08-07(1).pdf`
- `SAP Design Dossier - Forecasting - SAP TABLES.pdf`
- `SAP_Material_Delay_Root_Cause_Guide.pdf`
- Parquets MSN 13758 : Gross Needs, MEBOM, PLO et WO.

---

## Annexe C — Références SAP officielles

- [Multiple BOMs — SAP Help](https://help.sap.com/docs/SAP_ERP/85d3fce10e264972a0155c8b46ecf93b/e7abce5314894208e10000000a174cb4.html)
- [BOM Selection Using Production Version — SAP Help](https://help.sap.com/docs/SAP_ERP/85d3fce10e264972a0155c8b46ecf93b/f0abce5314894208e10000000a174cb4.html?q=subcontracting+MRP+area)
- [BOM Selection Using Order Quantity — SAP Help](https://help.sap.com/docs/SAP_ERP/85d3fce10e264972a0155c8b46ecf93b/eaabce5314894208e10000000a174cb4.html?q=subcontracting+MRP+area&version=6.18.latest)
- [Determining the Valid BOM — SAP Help](https://help.sap.com/docs/SAP_ERP/85d3fce10e264972a0155c8b46ecf93b/d5abce5314894208e10000000a174cb4.html)
- [Planned Independent Requirement tables — SAP Support](https://help.sap.com/docs/SUPPORT_CONTENT/erpman/3138697931.html)
- [Production version and quota arrangement relevance — SAP Help](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/fe39e10a9a864a8f8dc9537704f0fa13/f0abce5314894208e10000000a174cb4.html)
- [Alternative items during BOM explosion — SAP Help](https://help.sap.com/docs/SAP_ERP/85d3fce10e264972a0155c8b46ecf93b/0dacce5314894208e10000000a174cb4.html)

---

## Annexe D — Points à confirmer avant développement

1. Version SAP et système de référence pour chaque usine : ECC, S/4HANA ou combinaison.
2. Mapping exact de `selection_method` vers `MARC-ALTSL`.
3. Usages BOM `STLAN` autorisés par périmètre.
4. Source réelle de la demande racine et stratégie MRP correspondante.
5. Définition de la date d'explosion par rapport à la date de besoin.
6. Présence d'une MRP Area et priorité de `MDMA` sur `MARC`.
7. Règles de quota et de production version actives.
8. Existence et rôle d'une table Airbus ligne/station/version.
9. Règles exactes d'effectivité MSN.
10. Règles de quantité fixe, scrap, alternative items, bulk et phantom.
11. Niveau d'arrondi attendu par unité.
12. Choix officiel entre cible A et cible B.

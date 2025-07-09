# <p align="center">Documentation - Plugin Top'Eau <br> <img src="icon.png" alt="logo" width="100"/></p>

## Présentation du Plugin Top'Eau

### Genèse du Plugin

<p align="justify"> Dans le cadre de la Licence Professionnelle Topographie, Cartographie et Système d’Information Géographique (SIG), chaque étudiant est tenu, à l’issue des cours, de suivre un stage de 4 à 5 mois, afin de l’encourager à mettre en application au sein du milieu professionnel les connaissances et compétences acquises en cours, tout en lui permettant de bénéficier d’une insertion dans le monde professionnel. Pour mon stage, j’ai eu l’opportunité d’être encadrée par Mr Frédéric Pouget au sein de l’Université, et d’être accueillie par Mr <strong>Julien Ancelin</strong> au sein de l’Unité Expérimentale (UE) de Saint-Laurent-de-la-Prée (SLP), de l’Institut National de Recherche pour l’Agriculture, l’alimentation et l’Environnement (INRAE). Ce stage a été effectué dans le cadre des Volets de Recherche (VR) 1 et 2 du Projet MAVI, et s’est tenu du 14 avril 2025 au 22 août 2025. Le stage comportait trois grandes missions très techniques et utiles au sein de l’Unité et au sein du réseau d’UE créé autour des marais atlantiques. La première mission consistait à créer un MNT exploitable sur le site de Saint-Laurent-de-la-Prée et à comparer différentes sources de données altimétriques pour dresser un référentiel à l’échelle du Projet MAVI. La deuxième mission se concentrait autour de la création automatique d’un référentiel raster et attributaire lié à la simulation de niveaux d’eau dans chacune des parcelles des 5 sites. La troisième mission se tournait vers la création d’un outil permettant l’automatisation de calculs liés aux niveaux d’eau relevés dans les parcelles et fossés adjacents et aux dates de saisie. Puisque les deux et troisième missions se rejoignaient sur le principe de l’automatisation du processus, et de possibilité d’étendre à l’échelle de tous les sites du Projet MAVI, il a été décidé de créer un outil concentrant les deux processus.<p>

<p align="justify">Le premier effort de recherche concernant l’automatisation s’est porté vers la création d’un Modeleur graphique QGIS, mais passer par un Modeleur s’est avéré moins efficace que prévu. En ce sens, au fur et à mesure des discussions avec <strong>Julien Ancelin</strong> et <strong>Lilia Mzali</strong>, il a été décidé de mettre en place un Plugin QGIS, codé en Python, avec plusieurs interfaces dédiées à chacune des étapes de l’analyse des données eau relevées par les bouées, les piézomètres ou les agents sur le terrain. Ces étapes comprennent, comme il sera détaillé en allant dans la notice, la création d’un GeoPackage contenant des informations raster et attributaires propres à chaque simulation de niveau d’eau dans une zone d’étude, l’import des données eau dans ces GeoPackage et les analyses. Pour satisfaire un plus grand nombre d’utilisateurs et de demandes, deux interfaces d’analyse ont été réalisées : une propre à l’écoute biodiversité, et une propre à la création d’indicateurs dédiés à la gestion de l’eau. <p>

<p align="justify">Ces analyses ont été jugées comme nécessitant une forme d’automatisation car elles se doivent d’être répétées en fonction des espèces étudiées, des périodes de l’année, des différents types de relevés… et les calculs seraient longs et plus complexes sans ce Plugin et surtout sans la préparation des données proposée par le Plugin. Ces analyses sont effectuées dans le cadre du Projet MAVI mis en place par l’INRAE. Le Plugin a en ce sens vocation à pouvoir effectuer rapidement des traitements sur les différents sites expérimentaux du Projet MAVI, sans se préoccuper de la latence impliquée dans la distance entre les serveurs.<p>

<p align="justify">La demande à l’origine du Plugin était celle-ci : “proposer un outil géographique capable de calculer les variables clefs sur l’inondation/assèchement des parcelles en fonction des données de hauteur d’eau acquises, de la topographie et des liens entre la parcelle et les canaux, et d’avoir une lecture visuelle. \[...\] proposer un outil capable de quantifier les volumes d’eau dans les canaux et sur les parcelles en fonction des hauteurs d’eau enregistrées.” (<i>Proposition de stage de Master 1 / Licence Pro - année 2024-2025</i>, soumise par <strong>Julien Ancelin</strong> auprès de <strong>Frédéric Pouget</strong>). Au fur et à mesure de la définition des besoins et objectifs, il a été convenu de répondre à ces demandes en créant un Plugin avec de multiples interfaces dédiées à la création d’une bibliothèque raster et attributaire permettant de visualiser l’inondation des parcelles et de connaître les surfaces et volumes d’inondation en fonction de classes, l’import de données terrain et l’analyse de données existantes. 

<p align="justify">La construction du Plugin s’est reposée sur de nombreuses discussions avec les membres de l’UE qui seraient les premiers utilisateurs (<strong>Lilia Mzali</strong>, <strong>Vincent Boutifard</strong> et <strong>Isis Binam</strong>), et <strong>Julien Ancelin</strong>, qui a encadré toute la partie technique et faisabilité de la solution. <p>


### Quels utilisateurs?

<p align="justify">Ce Plugin s’adresse premièrement aux membres de l’Unité Expérimentale de Saint-Laurent-de-la-Prée, qui ont été interrogés en tant que futurs utilisateurs pour définir les fonctionnalités du Plugin. Il s’agit même plus précisément de fonctionnalités jugées comme utiles, voire nécessaires à automatiser, dans le cadre des études réalisées au sein du Projet MAVI, sous la coordination de <strong>Lilia Mzali</strong> et <strong>Vincent Boutifard</strong>. <p>

<p align="justify">Malgré tout, ce Plugin Open Source a été conçu pour être partagé à plus large échelle. L’utilisation de variables utilisateurs a été privilégiée sur la plupart des entrées afin de permettre à cette extension de devenir un outil utile au plus grand nombre dès qu’il s’agit de gestion des zones hydriques et d’analyser les relations entre la biodiversité et les niveaux d’eau. Évidemment, compte tenu de la précision des calculs effectués, l’extension reste bien plus adaptée à des milieux caractérisés par leur micro-topographie, comme les marais. <p>

### Structuration du Plugin

<p align="justify">Le Plugin a été pensé selon une logique de séparation des étapes en interfaces. Ainsi, <p>

## Utilisation

### Simulation de niveaux d'eau au sein d'une zone d'étude

<p align="justify">Métiers concernés : gestion de l'eau, gestion de la biodiversité, <p>

### Analyse biodiversité

<p align="justify">Métiers concernés : gestion de la biodiversité, ingénieur biodiversité, <p>

### Indicateurs et variables hydriques

<p align="justify">Métiers concernés : gestion de l'eau,  <p>

### Aspect technique

<p align="justify">Métiers concernés : administrateur SIG, technicien SIG, développeur, géomaticien, informaticien,  <p>

## Annexes

### Collaborateurs

### Sources 




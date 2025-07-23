# -*- coding: utf-8 -*-
# Import module PyQt et API PyQGIS
from qgis import core, gui
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5 import uic
from PyQt5.QtGui import *
from qgis.core import *
from qgis.core import Qgis, QgsMessageLog
from qgis import processing
from qgis.core import QgsRasterLayer
import os
from osgeo import osr
# import des librairies nécessaires à la lecture de données géospatiales
import json
# import librairie nécessaire à certains calculs
import math
import statistics
# import librairie manipulation raster et gpkg
import rasterio
from rasterio.transform import from_origin
import numpy as np
import subprocess
from osgeo import gdal, ogr, osr
import sqlite3
# import fichiers de code supplémentaires contenant fonctions/variables
from . import query, visu, params, generation
# import des fonctinos une à une pour les utiliser indépendamment les unes des autres dans la boucle
from .generation import (decouper_raster, calcul_niveau_eau, resample_raster, vectoriser_raster,
                            calculer_stats_raster, ajouter_donnees_table_gpkg, ajouter_raster_au_gpkg)

# mise en place de la classe TraitementWidget pour regrouper l'ensemble des fonctions relatives aux traitements à réaliser
class TraitementWidget(QDialog, params.form_traitement):
    def __init__(self, iface):
        QDialog.__init__(self)
        # création de l'interface de la fenêtre QGIS
        self.setupUi(self)
        # nom donné à la fenêtre
        self.setWindowTitle("Top'Eau - Analyse raster : différence entre le niveau d'eau et la parcelle")

        # Bouton "OK / Annuler"
        self.terminer.rejected.connect(self.reject)
        # Bouton "Récupérer la valeur minimale d'élévation au sein de la zone d'étude"
        self.recuperer.clicked.connect(self.chargement_donnees_raster)
        # Bouton "Générer le raster"
        self.generer.clicked.connect(self.chargement_raster)
        # Bouton "Visualiser les données
        self.graphique.clicked.connect(self.lance_fenetre_graph)
        # boutons à cocher ("checkbox")
        self.oui = self.findChild(QCheckBox, "oui")
        self.non = self.findChild(QCheckBox, "non")
        # connexion des checkbox pour qu'ils soient mutuellement exclusifs
        self.oui.toggled.connect(self.on_checkbox_toggled)
        self.non.toggled.connect(self.on_checkbox_toggled)

        # connexion de la barre de progression
        self.progressBar.setValue(0)

        # initialisation de valeur_min pour qu'elle puisse être utilisée dans toutes les fonctions
        self.valeur_min = None
        # initialisation du niveau d'eau à étudier pour l'utiliser dans les différentes fonctions
        self.current_level = None

        # association de filtres à la sélection de couches dans le projet QGIS
        self.inputRaster_2.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.inputVecteur_2.setFilters(QgsMapLayerProxyModel.PolygonLayer)

        # association de l'import de fichiers aux fonctions de désactivation des listes déroulantes
        self.inputRaster.fileChanged.connect(self.maj_etat_inputRaster2)
        self.inputVecteur.fileChanged.connect(self.maj_etat_inputVecteur2)

    # instauration d'une fonction assurant l'exclusivité des boutons oui & non
    def on_checkbox_toggled(self):
        # si l'un est coché, décocher l'autre
        if self.sender() == self.oui and self.oui.isChecked():
            self.non.setChecked(False)
            # désactiver le QDoubleSpinBox min (inputMin) quand oui est sélectionné
            self.inputMin.setEnabled(False)
        elif self.sender() == self.non and self.non.isChecked():
            self.oui.setChecked(False)
            # activer le QDoubleSpinBox min (inputMin) quand non est sélectionné
            self.inputMin.setEnabled(True)

    # fonctions permettant de désactiver les listes déroulantes des couches si un chemin est renseigné pour l'import de données
    def maj_etat_inputRaster2(self, path):
        path = path.strip()
        if path != "":
            self.inputRaster_2.setEnabled(False)
        else:
            self.inputRaster_2.setEnabled(True)

    def maj_etat_inputVecteur2(self, path):
        path = path.strip()
        if path != "":
            self.inputVecteur_2.setEnabled(False)
        else:
            self.inputVecteur_2.setEnabled(True)

    # fonction qui va permettre l'affichage des informa ktions relatives à la zone d'étude
    def chargement_donnees_raster(self):

        # première étape de l'analyse : découpage du raster en fonction de la ZE

        selected_raster = self.inputRaster.filePath() # chargement du raster sélectionné par l'utilisateur
        # vérification de la sélection d'un fichier en fonction du choix de l'utilisateur...
        if not selected_raster or selected_raster.strip() == "": #...localement...
            layer = self.inputRaster_2.currentLayer() # ...ou récupération de la couche sélectionnée depuis le projet
            if layer is None or not isinstance(layer, QgsRasterLayer):
                QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier raster.")
                return
            selected_raster = layer

        selected_vecteur = self.inputVecteur.filePath() # chargement du vecteur sélectionné par l'utilisateur
        # vérification de la sélection d'un fichier en fonction du choix de l'utilisateur...
        if not selected_vecteur or selected_vecteur.strip() == "": # ...localement...
            layer = self.inputVecteur_2.currentLayer() # ...ou récupération de la couche sélectionnée depuis le projet
            if layer is None or not layer.isValid():
                QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier vecteur.")
                return
            selected_vecteur = layer

        # ajout de l'algo "Remplir les cellules sans données" pour harmoniser les valeurs NoData des rasters en entrée
        path_nodata = os.path.join(params.temp_path, "temp_layer_nodata.tif") # fichier temp pour sortie de l'algo
        processing.run("native:fillnodata", {
            'INPUT': selected_raster,
            'BAND': 1,
            'FILL_VALUE': -1,
            'CREATE_OPTIONS': None,
            'OUTPUT': path_nodata
        })
        path_clip = os.path.join(params.temp_path, "temp_layer_clip.tif") # création d'un fichier temporaire

        # ajout de l'algorithme gdal "Découper un raster selon une couche de masque"
        processing.run("gdal:cliprasterbymasklayer", {
            'INPUT': path_nodata,  # appel à la variable récupérant le raster dont les valeurs NoData ont été harmonisées
            'MASK': selected_vecteur,  # appel à la variable récupérant le vecteur sélectionné
            'SOURCE_CRS': None,
            'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:2154'), # pousser le SCR pour être sûr
            'TARGET_EXTENT': None,
            'NODATA': -9999,
            'ALPHA_BAND': False,  # indiquer 'True' si volonté de générer une bande de transparence
            'CROP_TO_CUTLINE': True,
            'KEEP_RESOLUTION': False,
            'SET_RESOLUTION': False,
            'X_RESOLUTION': None,
            'Y_RESOLUTION': None,
            'MULTITHREADING': False,
            'OPTIONS': None,
            'DATA_TYPE': 0,
            'EXTRA': '',  # peut recevoir une ligne de commande indiquant des paramètres additionnels
            'OUTPUT': path_clip # appel du fichier temporaire pour afficher le résultat dans l'interface graphique de QGIS
        })

        layer_clip = QgsRasterLayer(path_clip, f"parcelle_decoupee", "gdal") # chargement du raster découpé comme une nouvelle couche QGIS
        if not layer_clip.isValid(): # vérification de la validité de la couche
            QMessageBox.warning(self, "Erreur", "La couche raster n'est pas valide.")
            return

        # deuxième étape : affichage des informations relatives à la ZE dans l'interface du plugin

        # ajout de l'algorithme natif "statistiques de zone" permettant d'avoir accès aux stats principales
        stats = processing.run("native:zonalstatisticsfb", {
            'INPUT': selected_vecteur,
            'INPUT_RASTER': selected_raster,
            'RASTER_BAND':1,
            'COLUMN_PREFIX':'_',
            'STATISTICS':[3,2,5,6], # dans l'ordre : mediane, moyenne, min, max
            'OUTPUT':'TEMPORARY_OUTPUT'})
        output_layer = stats['OUTPUT'] # récupération de la couche de sortie

        # extraction des valeurs depuis les attributs de la couche
        feature = next(output_layer.getFeatures())
        self.valeur_min, self.valeur_max, self.valeur_moy, self.valeur_med = feature['_min'], feature['_max'], feature['_mean'], feature['_median']

        # affichage du résultat dans l'interface du Plugin pour que l'utilisateur connaisse la valeur
        self.minLabel.setText(f"{self.valeur_min:.2f}m")
        self.maxLabel.setText(f"{self.valeur_max:.2f}m")
        self.moyLabel.setText(f"{self.valeur_moy:.2f}m")

        # stockage des chemins sélectionnés comme attributs de classe pour les utiliser dans d'autres fonctions
        self.selected_raster_path = selected_raster
        self.selected_vecteur_path = selected_vecteur

    # fonction de génération des rasters : troisième étape de l'analyse
    def chargement_raster(self):

        # vérification que l'utilisateur a coché une des deux options
        # NB : si l'utilisateur n'a coché aucune des deux options, il n'y a pas de valeur minimum pour la génération
        if self.oui is None or self.non is None:
            QMessageBox.critical(self, "Erreur", "Il manque un paramètre obligatoire (valeur minimale).")
            return

        # récupération des autres valeurs obligatoires saisies par l'utilisateur
        pas = self.inputPas.value()
        max_level = self.inputMax.value()
        resolution = self.inputResol.value()

        # récupération des chemins des rasters et vecteurs
        if hasattr(self, 'inputRaster_2') and self.inputRaster_2.currentLayer():
            selected_raster = self.inputRaster_2.currentLayer().source()
        elif hasattr(self, 'inputRaster') and self.inputRaster.filePath():
            selected_raster = self.inputRaster.filePath()
        else:
            QMessageBox.critical(self, "Erreur", "Veuillez sélectionner un raster.")
            return

        if hasattr(self, 'inputVecteur_2') and self.inputVecteur_2.currentLayer():
            selected_vecteur = self.inputVecteur_2.currentLayer().source()
        elif hasattr(self, 'inputVecteur') and self.inputVecteur.filePath():
            selected_vecteur = self.inputVecteur.filePath()
        else:
            QMessageBox.critical(self, "Erreur", "Veuillez sélectionner un vecteur.")
            return

        if self.oui.isChecked(): # récupération de la valeur minimale en fonction des choix de l'utilisateur
            min_level = self.valeur_min
            if min_level is None:
                QMessageBox.warning(self, "Attention", "Récupérez d'abord la valeur minimale d'élévation.")
                return
        else:
            min_level = self.inputMin.value()

        nb_niveaux = math.ceil((max_level - min_level) / pas) # calcul du nombre total de rasters à générer
        couches_generees = [] # création d'une liste Python pour stocker les couches générées

        # création du GPKG une seule fois avant la boucle
        nom_ze = self.nomZE.text()
        output_gpkg_path = self.outputGpkg.filePath()
        gpkg_path = os.path.join(output_gpkg_path, f"{nom_ze}_topeau.gpkg")
        if os.path.exists(gpkg_path):
            os.remove(gpkg_path) # suppressin du GPKG s'il existe déjà pour éviter les conflits
        # création du GPKG vide et de la table SQLite dès le début
        self.creer_gpkg_initial(gpkg_path, self.valeur_min, self.valeur_max, self.valeur_moy, self.valeur_med)

        # mise en place de la boucle de génération des rasters
        self.current_level = max_level  # on commence au niveau max et on descend
        count = 0

        # initialisation des variables pour les graphs
        self.niveaueau_hauteur = []
        self.surface_hauteur = []

        progress_step = 100 / nb_niveaux if nb_niveaux > 0 else 0 # calcul du pas de progression pour la barre

        generation.decouper_raster(selected_raster, selected_vecteur) # découpage du MNT une seule fois avant la boucle

        while self.current_level >= min_level: # début de la génération des rasters compris entre le min et le max

            count += 1
            progress_value = int(count * progress_step)
            self.progressBar.setValue(progress_value) # màj de la barre de prorgession en fonction des rasters générés
            QApplication.processEvents()

            # création d'un fichier unique pour chaque niveau d'eau
            nom_ze = self.nomZE.text()  # récupération du nom renseigné par l'utilisateur
            niveau_cm = int(round(self.current_level * 100))  # conversion en centimètres pour le nom du fichier
            output_name = f"{nom_ze}_{niveau_cm}cm_topeau"  # création d'un nom de fichier unique pour chaque fichier

            niveau_eau = self.current_level  # définition de la variable utilisée dans generation.py
            raster_diff = generation.calcul_niveau_eau(niveau_eau) # calcul de la différence entre le niveau d'eau et le MNT

            # passage à l'étape suivante (ré-échantillonnage) si le calcul abien été effectué
            if raster_diff:

                input_path = raster_diff # définition de la variable utilisée dans generation.py
                resampled_raster = generation.resample_raster(input_path, output_name, resolution) # appel du raster ré-échantillonné

                # ajout du raster à la liste des rasters ré-échantillonnés et boucle sur les fonctions nécessaires au formatage GPKG
                if resampled_raster:

                    # conversion de chaque raster dans le GPKG unique
                    generation.ajouter_raster_au_gpkg(resampled_raster, gpkg_path, output_name)

                    # vectorisation de chaque raster pour que la géométrie soit récupérée lors de l'insertion des données dans les tables
                    raster_vectorise = generation.vectoriser_raster(resampled_raster, output_name)

                    # calcul des stats pour la table
                    (surface_totale, _, volume_total, classe_1_surf, classe_2_surf, classe_3_surf, classe_4_surf,
                     classe_5_surf, classe_6_surf, classe_7_surf) = generation.calculer_stats_raster(resampled_raster)

                    # protection contre l'écrasement des variables
                    if not hasattr(self, 'niveaueau_hauteur') or not isinstance(self.niveaueau_hauteur, list):
                        self.niveaueau_hauteur = []
                    if not hasattr(self, 'surface_hauteur') or not isinstance(self.surface_hauteur, list):
                        self.surface_hauteur = []

                    # collecte les données pour le graphique
                    self.niveaueau_hauteur.append(self.current_level)
                    self.surface_hauteur.append(surface_totale)

                    # alimentation de la table SQLite
                    generation.ajouter_donnees_table_gpkg(gpkg_path, surface_totale, volume_total,
                                                    classe_1_surf, classe_2_surf, classe_3_surf, classe_4_surf,
                                                    classe_5_surf, classe_6_surf, classe_7_surf, self.current_level, nom_ze, raster_vectorise)

                    couches_generees.append(f"{output_name} (dans {gpkg_path})")

            self.current_level -= pas # passage au niveau suivant (en suivant le pas)

        self.progressBar.setValue(100) # màj de la barre de progression à 100% à la fin de la génération des rasters
        self.charger_gpkg_dans_qgis(gpkg_path, couches_generees) # chargement automatique du GPKG dans QGIS

        # affichage du nombre de rasters générés
        QMessageBox.information(self,"Traitement terminé",f"{len(couches_generees)} rasters ont été générés avec succès.")

    # fonction permettant la création du GPKG et de sa table attributaire "hauteur_eau" : quatrième étape de l'analyse
    def creer_gpkg_initial(self, gpkg_path, valeur_min, valeur_max, valeur_moy, valeur_med):

        # import des librairies propres à cette fonction pour la récupération de la date de création
        import os
        from datetime import datetime

        self.deciles_calcules = {} # création dictionnaire pour contenir les déciles pour le graph
        self.surface_zoneetude = [] # création tuple pour contenir les infos de surface pour le graph

        try:

            date_creation = datetime.now().strftime('%Y-%m-%d') # récupération de la date de création du fichier

            if os.path.exists(gpkg_path): # vérification de l'unicité du GPKG pour éviter tout conflit
                os.remove(gpkg_path)

            path_clip = os.path.join(params.temp_path, "temp_layer_clip.tif") # récup du raster découpé pour calculer les déciles

            if not os.path.exists(path_clip): # vérification de l'existence du fichier
                QgsMessageLog.logMessage(f"Le fichier raster {path_clip} n'existe pas", "Top'Eau", Qgis.Warning)
                data_pixels = None # utilisation des valeurs par défaut pour les déciles
            else:
                dataset = gdal.Open(path_clip)
                if dataset is None:
                    QgsMessageLog.logMessage(f"Impossible d'ouvrir le raster {path_clip}", "Top'Eau", Qgis.Warning)
                    data_pixels = None
                else: # récupération des informations du raster
                    band = dataset.GetRasterBand(1)
                    data_pixels = band.ReadAsArray()
                    nodata_value = band.GetNoDataValue()
                    dataset = None

            # connexion SQLite au GPKG créé pour pouvoir effectuer des requêtes sur ses données (création, insertion...)
            conn = sqlite3.connect(gpkg_path)
            cursor = conn.cursor()
            # connexion SpatiaLite pour pouvoir créer et générer des géométries valides
            conn.enable_load_extension(True)
            spatialite_loaded = False

            try: # vérification du chargement de SpatiaLite si disponible
                conn.load_extension("mod_spatialite")
                cursor.execute("SELECT InitSpatialMetaData(1)")
                spatialite_loaded = True
                QgsMessageLog.logMessage("SpatiaLite activé", "Top'Eau", Qgis.Info)
            except:
                try: # essayer avec spatialite sur certains systèmes
                    conn.load_extension("spatialite")
                    cursor.execute("SELECT InitSpatialMetaData(1)")
                    spatialite_loaded = True
                    QgsMessageLog.logMessage("SpatiaLite activé (spatialite)", "Top'Eau", Qgis.Info)
                except:
                    # utilisation des fonctions GPKG natives si pas de connexion spatialite
                    spatialite_loaded = False
                    QgsMessageLog.logMessage("SpatiaLite non disponible, utilisation des fonctions GPKG natives",
                                             "Top'Eau", Qgis.Info)

            self.spatialite_loaded = spatialite_loaded # stockage de l'état de connexion pour les autres fonctions

            # création des tables système GeoPackage obligatoires
            cursor.execute(query.q_1) # création de la table pour les systèmes de référence : table gpkg_spatial_ref_sys
            cursor.execute(query.q_2, query.params_q2) # insertion du SCR Lambert 93 EPSG[2154]
            cursor.execute(query.q_3) # création de la table contenant le catalogue de contenus : table gpkg_contents
            cursor.execute(query.q_4) # création de la table contenant les info géométriques : table gpkg_geometry_columns
            cursor.execute(query.q_5) # création de la table contenant les info liées à l'extension : table gpkg_extensions
            cursor.execute(query.q_6) # création table pour les triggers de validation géométrique : table gpkg_data_columns

            # récupération d'informations nécessaires à l'insertion de données attributaires dans les tables
            # récupération de la date de création du fichier après sa création
            try:
                if os.path.exists(gpkg_path):
                    # utilisation la date de création (Windows) ou de modification (Linux)
                    if os.name == 'nt':
                        creation_timestamp = os.path.getctime(gpkg_path) # instauration d'une variable adaptée à Windows
                    else:
                        creation_timestamp = os.path.getmtime(gpkg_path) # instauration d'une variable adaptée à Linux

                    # conversion du timestamp en format de date
                    date_creation = datetime.fromtimestamp(creation_timestamp).strftime('%Y-%m-%d')
            except Exception :
                QgsMessageLog.logMessage(f"Impossible de récupérer la date de création du fichier","Top'Eau", Qgis.Warning)

            # calcul des déciles pour les ajouter à la table attributaire "zone_etude"
            deciles = {}
            try:
                if data_pixels is not None and data_pixels.size > 0:
                    # suppression des valeurs nulles/NaN /NoData
                    if 'nodata_value' in locals() and nodata_value is not None:
                        mask = (~np.isnan(data_pixels)) & (data_pixels != nodata_value) & (data_pixels > 0)
                    else:
                        mask = (~np.isnan(data_pixels)) & (data_pixels > 0)
                    pixels_valides = data_pixels[mask]

                    if len(pixels_valides) > 0:
                        percentiles = np.arange(10, 100, 10) # calcul des déciles avec numpy
                        valeurs_deciles = np.percentile(pixels_valides, percentiles)
                        for i, percentile in enumerate(percentiles):
                            deciles[f'decile_{int(percentile)}'] = round(valeurs_deciles[i], 2) # arrondir les valeurs récupérées

                        self.deciles_calcules = deciles
                        QgsMessageLog.logMessage(f"Déciles calculés avec succès", "Top'Eau", Qgis.Info)

                    else: QgsMessageLog.logMessage(f"Aucune valeur valide pour le calcul des déciles", "Top'Eau", Qgis.Warning)
                else: QgsMessageLog.logMessage(f"Aucune donnée de pixels fournie pour le calcul des déciles", "Top'Eau", Qgis.Warning)
            except Exception as decile_error:
                QgsMessageLog.logMessage(f"Erreur lors du calcul des déciles : {str(decile_error)}", "Top'Eau", Qgis.Warning)

            # récupération de la géométrie en WKT puis en WKB pour être reconnue commme colonne à géométrie valide pour le GPKG
            geometry_wkt = None
            geometry_wkb = None
            surface_ze = 0.0
            srid = 2154 # code EPSG du Lambert 93
            geometry_type = 'MULTIPOLYGON'
            min_x, min_y, max_x, max_y = None, None, None, None

            da = QgsDistanceArea() # configuration de QgsDistanceArea pour récupérer la surface du polygone d'entrée
            try:
                if hasattr(self, 'selected_vecteur_path') and self.selected_vecteur_path is not None:

                    if hasattr(self.selected_vecteur_path, 'crs'):
                        srid = self.selected_vecteur_path.crs().postgisSrid() # récupération du SRID de la couche source

                    features = self.selected_vecteur_path.getFeatures() # récupération des entités du vecteur sélectionné

                    for feature in features: # boucle sur chacune des entités polygonales détectées dans la couche vecteur
                        geom = feature.geometry() # récupération de la géométrie de la première entité
                        surface_cal = da.measureArea(geom) # calcul de la surface de l’entité
                        if geom and not geom.isEmpty():
                            # passage de la géométrie récupérée en WKT pour être retranscrite et lue en table
                            geometry_wkt = geom.asWkt()
                            geometry_wkb = geom.asWkb()
                            surface_ze += surface_cal
                            # calcul des extent pour gpkg_contents
                            bbox = geom.boundingBox()
                            min_x, min_y, max_x, max_y = bbox.xMinimum(), bbox.yMinimum(), bbox.xMaximum(), bbox.yMaximum()

                            QgsMessageLog.logMessage(f"Géométrie récupérée pour l'emprise", "Top'Eau", Qgis.Info)
                            break
                        else: QgsMessageLog.logMessage(f"Géométrie vide dans selected_vecteur", "Top'Eau", Qgis.Warning)
                    else: QgsMessageLog.logMessage(f"Aucune entité trouvée dans selected_vecteur", "Top'Eau", Qgis.Warning)
                else: QgsMessageLog.logMessage(f"Variable selected_vecteur non disponible", "Top'Eau", Qgis.Warning)
            except Exception as geom_error:
                QgsMessageLog.logMessage(f"Erreur lors de la récupération de la géométrie : {str(geom_error)}","Top'Eau", Qgis.Warning)

            # création des tables attributaires à l'intérieur du GPKG

            # création et insertion des données pour la table "zone_etude"
            table_creation_sql = query.q_22
            # ajout des colonnes pour les déciles
            for i in range(10, 100, 10):
                table_creation_sql += f',\n decile_{i} REAL'
            table_creation_sql += '\n )'
            cursor.execute(table_creation_sql)

            # enregistrement dans gpkg_contents AVANT gpkg_geometry_columns
            cursor.execute(query.q_7, ('zone_etude',
                'features',
                'zone_etude',
                'Zone d\'étude pour simulation Top\'Eau',
                datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                min_x, min_y, max_x, max_y,
                srid))

            # ajout de la colonne géométrique via la maj des métadonnées du GPKG
            cursor.execute(query.q_8, ('zone_etude', 'emprise', geometry_type, srid, 0, 0))

            # préparation de la requête d'insertion avec les déciles
            insert_columns = '''nom, emprise, surface_m2, min_parcelle, max_parcelle, moyenne_parcelle, mediane_parcelle'''
            insert_values = '''?, ?, ?, ?, ?, ?, ?'''

            for i in range(10, 100, 10): # ajout des colonnes et valeurs pour les déciles
                insert_columns += f', decile_{i}'
                insert_values += ', ?'

            if geometry_wkb: # création de la couche géométrique si le Wkb est récupéré
                # préparation des colonnes et valeurs pour les déciles
                colonnes_deciles = [f'decile_{i}' for i in range(10, 100, 10)]
                valeurs_deciles = [deciles.get(f'decile_{i}', None) for i in range(10, 100, 10)]

                # construction de la requête SQL
                colonnes_sql = ('emprise, nom, surface_m2, min_parcelle, max_parcelle, moyenne_parcelle, mediane_parcelle, '
                                + ', '.join(colonnes_deciles))
                placeholders_sql = '?, ?, ?, ?, ?, ?, ?, ' + ', '.join(['?' for _ in colonnes_deciles])

                # valeurs à insérer
                valeurs_insertion = [
                                        geometry_wkb, self.nomZE.text(), round(surface_ze, 2),
                                        round(self.valeur_min, 2), round(self.valeur_max, 2),
                                        round(self.valeur_moy, 2), round(self.valeur_med, 2)
                                    ] + valeurs_deciles

                # choix de la méthode d'insertion selon la disponibilité de SpatiaLite
                if self.spatialite_loaded:
                    # Avec SpatiaLite
                    cursor.execute(f'''INSERT INTO zone_etude({colonnes_sql}) 
                                VALUES (ST_GeomFromWKB(?, ?), ?, ?, ?, ?, ?, ?, {', '.join(['?' for _ in colonnes_deciles])})
                            ''', [
                        geometry_wkb, srid, self.nomZE.text(), round(surface_ze,2),
                        round(self.valeur_min, 2), round(self.valeur_max, 2),
                        round(self.valeur_moy, 2), round(self.valeur_med, 2)
                    ] + valeurs_deciles)
                else: # sans SpatiaLite : insertion directe du WKB
                    cursor.execute(f'''INSERT INTO zone_etude({colonnes_sql}) VALUES({placeholders_sql})''', valeurs_insertion)

            # création de la table "hauteur_eau"
            # NB : l'insertion des données se fait dans une fonction dédiée car ce sont des données récupérées en fonction
            # des rasters créés et non en fonction du GPKG créé
            cursor.execute(query.q_9)
            # enregistrement dans gpkg_contents pour hauteur_eau (sans extent pour l'instant)
            cursor.execute(query.q_10, (
                'hauteur_eau',
                'features',
                'hauteur_eau',
                'Surfaces inondées pour différents niveaux d\'eau',
                datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                srid ))
            # ajout de la colonne géométrique via la maj des métadonnées du GPKG
            cursor.execute(query.q_11, ('hauteur_eau', 'geom', 'MULTIPOLYGON', srid, 0, 0))

            # création de la table "mesure"
            cursor.execute(query.q_12) # NB : la table est vide car c'est celle qui sera utilisée après pour le requêtage SQL

            # création et insertion des données dans la table "metadata_md1"
            # NB : les noms de champ et leur complétion ont été définis en fonction des documents qualité d'Olivier Schmit
            nom_ze = self.nomZE.text()
            cursor.execute(query.q_13)
            cursor.execute(query.q_14, (
                    f'{nom_ze}_topeau.gpkg',
                    'Variables hydriques, mesure du niveau d\'eau, simulation inondation, parcelles, marais littoraux atlantiques, INRAE',
                    'Marion Bleuse',
                    'Julien Ancelin',
                    'Olivier Schmit',
                    'marion.bleuse8@gmail.com / julien.ancelin@inrae.fr / lilia.mzali@inrae.fr',
                    'Se référer à la fenêtre \'A propos\' du Plugin Top\'Eau',
                    date_creation,
                    'GeoPackage contenant des fichiers rasters, vecteurs et tabulaires',
                    'GeoPackage (.gpkg)',
                    'Français',
                    'Se référer à la documentation du Plugin disponible via la fenêtre \'Aide\' du Plugin Top\'Eau',
                    'Zone d\'étude située au sein d\'un des sites du Projet MAVI porté par l\'Unité Expérimentale INRAE de Saint-Laurent-de-la-Prée',
                    'Résultat de l\'automatisation de traîtements effectués par le Plugin Top\'Eau',
                    'CC-BY-NC-ND'
                ))

            # création et insertion des données dans la table "metadata_md2"
            # NB : les noms de champ et leur complétion ont été définis en fonction des documents qualité d'Olivier Schmit
            cursor.execute(query.q_15)
            cursor.execute(query.q_16, query.params_q16)

            self.surface_zoneetude = surface_ze

            conn.commit()
            conn.close()

            QgsMessageLog.logMessage(f"GPKG créé : {gpkg_path}", "Top'Eau", Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur création GPKG : {str(e)}", "Top'Eau", Qgis.Critical)
            raise e

    # fonction permettant de créer une couche vectorielle avec GDAL pour créer les entités polygonales des surfaces inondées
    def creer_couche_vecteur_gdal(self, gpkg_path, layer_name, geom_type, fields_dict):

        driver = ogr.GetDriverByName('GPKG')
        ds = driver.Open(gpkg_path, 1)  # 1 = mode de màj

        # création de la couche avec le bon SCR
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(2154)
        layer = ds.CreateLayer(layer_name, srs, geom_type)

        # ajout des champs
        for field_name, field_type in fields_dict.items():
            field_def = ogr.FieldDefn(field_name, field_type)
            layer.CreateField(field_def)
        ds = None
        return True

    # fonction pour charger automatiquement les tables et rasters du GPKG dans QGIS
    def charger_gpkg_dans_qgis(self, gpkg_path, couches_generees):

        try:
            from qgis.utils import iface # référence à l'interface QGIS

            # création d'un groupe pour organiser les couches
            nom_ze = self.nomZE.text()
            root = QgsProject.instance().layerTreeRoot()
            group = root.insertGroup(0, f"Top'Eau - {nom_ze}")

            # chargement des tables attributaires
            tables_attributaires = ['zone_etude', 'hauteur_eau', 'mesure', 'metadata_md1', 'metadata_md2']

            for table in tables_attributaires:
                try:
                    uri = f"{gpkg_path}|layername={table}" # création d'un URI pour les tables du GPKG
                    layer = QgsVectorLayer(uri, f"{table}", "ogr") # création de la couche

                    if layer.isValid():
                        # ajout de la couche au projet dans le groupe
                        QgsProject.instance().addMapLayer(layer, False)
                        group.addLayer(layer)
                        QgsMessageLog.logMessage(f"Table {table} chargée avec succès", "Top'Eau", Qgis.Info)
                    else: QgsMessageLog.logMessage(f"Impossible de charger la table {table}", "Top'Eau", Qgis.Warning)

                except Exception as e:
                    QgsMessageLog.logMessage(f"Erreur lors du chargement de la table {table}: {str(e)}", "Top'Eau", Qgis.Warning)

            # chargement des rasters
            rasters = self.lister_rasters_gpkg(gpkg_path) # récupération de la liste des rasters dans le GPKG
            for raster_name in rasters:
                try:
                    uri = f"GPKG:{gpkg_path}:{raster_name}" # création d'un URI pour les rasters du GPKG
                    layer = QgsRasterLayer(uri, raster_name, "gdal") # création de la couche raster
                    # ajout de la couche au projet dans le groupe
                    if layer.isValid():
                        QgsProject.instance().addMapLayer(layer, False)
                        group.addLayer(layer)

                        QgsMessageLog.logMessage(f"Raster {raster_name} chargé avec succès", "Top'Eau", Qgis.Info)
                    else: QgsMessageLog.logMessage(f"Impossible de charger le raster {raster_name}", "Top'Eau", Qgis.Warning)

                except Exception as e:
                    QgsMessageLog.logMessage(f"Erreur lors du chargement du raster {raster_name}: {str(e)}", "Top'Eau", Qgis.Warning)

            QMessageBox.information(self, "Chargement terminé", f"Le GPKG a été chargé avec succès dans QGIS.\n"
                                    f"Tables et rasters disponibles dans le groupe '{nom_ze}'.")

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors du chargement du GPKG: {str(e)}", "Top'Eau", Qgis.Critical)
            QMessageBox.warning(self, "Erreur", f"Erreur lors du chargement du GPKG:\n{str(e)}")

    # fonction nécessaire à la fonction précédente = permet de lister les rasters présents dans le GPKG
    def lister_rasters_gpkg(self, gpkg_path):

        rasters = []
        try:
            conn = sqlite3.connect(gpkg_path)
            cursor = conn.cursor()
            cursor.execute(query.q_21) # requête pour récupérer les tables raster

            results = cursor.fetchall()
            rasters = [row[0] for row in results]

            conn.close()

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la récupération des rasters: {str(e)}", "Top'Eau", Qgis.Warning)

        return rasters

    # fonction permettant l'affichage de la fenêtre liée à la datavisualisation
    def lance_fenetre_graph(self):
        self.graph_window = visu.VisuWindow(parent_widget=self)
        self.graph_window.exec_()
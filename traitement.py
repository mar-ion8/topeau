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

# import librairies nécessaires à la datavisualisation
import seaborn as sns
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# appel emplacement des fichiers de stockage des sorties temporaires -- style et temp
temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
qml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style")

# lien entre traitement.py et visu.ui
ui_path = os.path.dirname(os.path.abspath(__file__))
ui_path = os.path.join(ui_path, "ui")
form_traitement, _ = uic.loadUiType(os.path.join(ui_path, "traitement.ui"))
form_graph, _ = uic.loadUiType(os.path.join(ui_path, "visu.ui"))


# mise en place de la classe TraitementWidget
# va regrouper l'ensemble des fonctions relatives aux traitements à réaliser
class TraitementWidget(QDialog, form_traitement):
    def __init__(self, iface):
        QDialog.__init__(self)

        # création de l'interface de la fenêtre QGIS
        self.setupUi(self)
        # ajustement de la taille de la fenêtre pour qu'elle soit fixe
        #self.setFixedSize(600, 400)
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
        self.inputRaster_2.setFilters(
            QgsMapLayerProxyModel.RasterLayer |
            QgsMapLayerProxyModel.PluginLayer
        )
        self.inputVecteur_2.setFilters(
            QgsMapLayerProxyModel.VectorLayer |
            QgsMapLayerProxyModel.PolygonLayer
        )

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


    # première étape de l'analyse
    # fonction qui va permettre l'affichage des informations relatives à la zone d'étude
    def chargement_donnees_raster(self):

        # 1. découpage du raster en fonction de la ZE

        # 1.1. chargement du raster sélectionné par l'utilisateur dans une variable
        selected_raster = self.inputRaster.filePath()
        # vérification de la sélection d'un fichier en fonction du choix de l'utilisateur...
        #...localement...
        if not selected_raster or selected_raster.strip() == "":
            # ...ou récupération de la couche sélectionnée depuis le projet
            layer = self.inputRaster_2.currentLayer()
            if layer is None or not isinstance(layer, QgsRasterLayer):
                QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier raster.")
                return
            selected_raster = layer

        # 1.2. chargement du vecteur sélectionné par l'utilisateur dans une variable
        selected_vecteur = self.inputVecteur.filePath()
        # vérification de la sélection d'un fichier en fonction du choix de l'utilisateur...
        # ...localement...
        if not selected_vecteur or selected_vecteur.strip() == "":
            # ...ou récupération de la couche sélectionnée depuis le projet
            layer = self.inputVecteur_2.currentLayer()
            if layer is None or not layer.isValid():
                QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier vecteur.")
                return
            selected_vecteur = layer

        # 1.3. ajout de l'algorithme natif "Remplir les cellules sans données" pour harmoniser les valeurs NoData
        # de n'importe quelle donnée raster en entrée
        path_nodata = os.path.join(temp_path, "temp_layer_nodata.tif")

        processing.run("native:fillnodata", {
            'INPUT': selected_raster,
            'BAND': 1,
            'FILL_VALUE': -1,
            'CREATE_OPTIONS': None,
            'OUTPUT': path_nodata
        })

        # création d'un fichier temporaire
        path_clip = os.path.join(temp_path, "temp_layer_clip.tif")

        # 1.4. ajout de l'algorithme gdal "Découper un raster selon une couche de masque"
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
            'OUTPUT': path_clip
            # appel du fichier temporaire pour afficher le résultat dans l'interface graphique de QGIS
        })


        # 1.5. chargement du raster découpé comme une nouvelle couche QGIS
        layer_clip = QgsRasterLayer(path_clip, f"parcelle_decoupee", "gdal")
        # s'assurer qu'il n'y a pas d'erreur
        if not layer_clip.isValid():
            QMessageBox.warning(self, "Erreur", "La couche raster n'est pas valide.")
            return


        # 2. affichage des informations relatives à la ZE dans l'interface du plugin

        # 2.1. ajout de l'algorithme natif "statistiques de zone" permettant d'avoir accès aux stats principales
        stats = processing.run("native:zonalstatisticsfb", {
            'INPUT': selected_vecteur,
            'INPUT_RASTER': selected_raster,
            'RASTER_BAND':1,
            'COLUMN_PREFIX':'_',
            'STATISTICS':[3,2,5,6], #mediane, moyenne, min, max
            'OUTPUT':'TEMPORARY_OUTPUT'})

        # récupération de la couche de sortie
        output_layer = stats['OUTPUT']

        # extraction des valeurs depuis les attributs de la couche
        feature = next(output_layer.getFeatures())
        self.valeur_min = feature['_min']
        self.valeur_max = feature['_max']
        self.valeur_moy = feature['_mean']
        self.valeur_med = feature['_median']

        # 2.2. affichage du résultat dans l'interface du Plugin pour que l'utilisateur connaisse la valeur
        self.minLabel.setText(f"{self.valeur_min:.2f}m")
        self.maxLabel.setText(f"{self.valeur_max:.2f}m")
        self.moyLabel.setText(f"{self.valeur_moy:.2f}m")

        # Stocker les chemins sélectionnés comme attributs de classe pour les utiliser dans d'autres fonctions
        self.selected_raster_path = selected_raster
        self.selected_vecteur_path = selected_vecteur


    # deuxième étape de l'analyse
    # 3. générer les rasters
    def chargement_raster(self):

        # 3.1. vérification que l'utilisateur a coché une des deux options
        # NB : si l'utilisateur n'a coché aucune des deux options, il n'y a pas de valeur minimum pour la génération
        if self.oui is None or self.non is None:
            QMessageBox.critical(self, "Erreur", "Il manque un paramètre obligatoire (valeur minimale).")
            return

        # 3.2. récupération des autres valeurs obligatoires saisies par l'utilisateur
        pas = self.inputPas.value()
        max_level = self.inputMax.value()

        # 3.3. récupération de la valeur minimale en fonction des choix de l'utilisateur
        # si "oui" est coché...
        if self.oui.isChecked():
            # ...utilisation de la valeur minimale du MNT récupérée juste avant
            min_level = self.valeur_min
            if min_level is None:
                QMessageBox.warning(self, "Attention", "Récupérez d'abord la valeur minimale d'élévation.")
                return
        # si "non" est coché...
        else:
            # ... utilisation de la valeur spécifiée par l'utilisateur
            min_level = self.inputMin.value()

        # 3.4. calcul du nombre total de rasters à générer
        nb_niveaux = math.ceil((max_level - min_level) / pas)

        # 3.5. création d'une liste Python pour stocker les couches générées
        couches_generees = []

        # 3.6. création du GPKG une seule fois avant la boucle
        nom_ze = self.nomZE.text()
        output_gpkg_path = self.outputGpkg.filePath()
        gpkg_path = os.path.join(output_gpkg_path, f"{nom_ze}_topeau.gpkg")

        # suppressin du GPKG s'il existe déjà pour éviter les conflits
        if os.path.exists(gpkg_path):
            os.remove(gpkg_path)

        # création du GPKG vide et de la table SQLite dès le début
        self.creer_gpkg_initial(gpkg_path, self.valeur_min, self.valeur_max, self.valeur_moy, self.valeur_med)

        # 3.7. mise en place de la boucle de génération des rasters
        self.current_level = max_level  # on commence au niveau max et on descend
        count = 0

        # calcul du pas de progression pour la barre
        progress_step = 100 / nb_niveaux if nb_niveaux > 0 else 0

        # découpage du MNT une seule fois avant la boucle
        self.decouper_raster()

        # début de la boucle
        while self.current_level >= min_level:
            # mise à jour de la barre de progression en fonction du nombre de rasters générés
            count += 1
            progress_value = int(count * progress_step)
            self.progressBar.setValue(progress_value)
            QApplication.processEvents()

            # création d'un fichier unique pour chaque niveau d'eau
            nom_ze = self.nomZE.text() # récupération du nom renseigné par l'utilisateur
            niveau_cm = int(self.current_level * 100)  # conversion en centimètres pour le nom du fichier
            output_name = f"{nom_ze}_{niveau_cm}cm_topeau" # création d'un nom de fichier unique pour chaque fichier

            # calcul de la différence entre le niveau d'eau et le MNT
            raster_diff = self.calcul_niveau_eau(output_name)

            # passage à l'étape suivante (ré-échantillonnage) si le calcul abien été effectué
            if raster_diff:
                # appel du raster ré-échantillonné avec r.resamp.stats de GRASS (fonction resample_raster)
                resampled_raster = self.resample_raster(raster_diff, output_name)

                # ajout du raster à la liste des rasters s'il a bien été ré-échantillonné et boucle sur les fonctions nécessaires au formatage GPKG
                if resampled_raster:

                    # conversion de chaque raster dans le GPKG unique
                    self.ajouter_raster_au_gpkg(resampled_raster, gpkg_path, output_name)

                    # vectorisation de chaque raster pour que la géométrie soit récupérée lors de l'insertion des données dans les tables
                    raster_vectorise = self.vectoriser_raster(resampled_raster, output_name)

                    # calcul des stats pour la table
                    surface_totale, _, volume_total, classe_1_surf, classe_2_surf, classe_3_surf, classe_4_surf, classe_5_surf, classe_6_surf, classe_7_surf = self.calculer_stats_raster(
                        resampled_raster)

                    # alimentation de la table SQLite
                    self.ajouter_donnees_table_gpkg(gpkg_path, surface_totale, volume_total,
                                                    classe_1_surf, classe_2_surf, classe_3_surf, classe_4_surf,
                                                    classe_5_surf, classe_6_surf, classe_7_surf, raster_vectorise)

                    couches_generees.append(f"{output_name} (dans {gpkg_path})")

            # passage au niveau suivant (en suivant le pas)
            self.current_level -= pas

        # mise à jour de la barre de progression à 100% à la fin de la génération des rasters
        self.progressBar.setValue(100)

        # chargement automatique du GPKG dans QGIS
        self.charger_gpkg_dans_qgis(gpkg_path, couches_generees)

        # affichage du nombre de rasters générés
        QMessageBox.information(self, "Traitement terminé",
                                f"{len(couches_generees)} rasters ont été générés avec succès.")


    # étape interne à la génération des rasters
    # fonction permettant de découper le raster
    # la fonction est répétée automatiquement autant de fois qu'il y a de niveaux d'eau à traiter puisqu'elle est traitée par la boucle
    def decouper_raster(self):
        # utilisation des chemins stockés plutôt que de refaire la sélection
        # 3.7.1. chargement du raster sélectionné par l'utilisateur
        selected_raster = getattr(self, 'selected_raster_path', None)
        # 3.7.2. chargement du vecteur sélectionné par l'utilisateur
        selected_vecteur = getattr(self, 'selected_vecteur_path', None)

        # création d'un fichier temporaire
        path_clip = os.path.join(temp_path, "temp_layer_clip.tif")

        # 3.7.3. utilisation de l'algorithme GDAL "Découper un raster selon une couche de masque"
        processing.run("gdal:cliprasterbymasklayer", {
            'INPUT': selected_raster, #variable récupérant le raster sélectionné par l'utilisateur
            'MASK': selected_vecteur, #variable récupérant le vecteur sélectionné par l'utilisateur
            'SOURCE_CRS': None,
            'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:2154'), #permet de s'assurer que le raster découpé sera bien en 2154
            'TARGET_EXTENT': None,
            'NODATA': -9999, #permet aux pixels à valeur nulle de ne pas être comptés dans l'emprise du raster
            'ALPHA_BAND': False,
            'CROP_TO_CUTLINE': True,
            'KEEP_RESOLUTION': False,
            'SET_RESOLUTION': False,
            'X_RESOLUTION': None,
            'Y_RESOLUTION': None,
            'MULTITHREADING': False,
            'OPTIONS': None,
            'DATA_TYPE': 0,
            'EXTRA': '',
            'OUTPUT': path_clip #sortie permanente en temp pour que l'algorithme suivant puisse avoir une couche input
        })


    # étape interne à la génération des rasters
    # fonction permettant de calculer la différence entre le niveau d'eau à étudier et le raster relatif à l'élévation
    # la fonction est répétée automatiquement autant de fois qu'il y a de niveaux d'eau à traiter puisqu'elle est traitée par la boucle
    def calcul_niveau_eau(self, output_path):

        # 3.7.1. utilisation de self.current_level pour le niveau d'eau
        niveau_eau = self.current_level

        # 3.7.2. chargement du raster découpé précédemment
        path_clip = os.path.join(temp_path, "temp_layer_clip.tif")
        layer_clip = QgsRasterLayer(path_clip, f"parcelle_decoupee", "gdal")

        # vérification de la validité de la couche
        if not layer_clip.isValid():
            QMessageBox.warning(self, "Erreur", "La couche raster découpée n'est pas valide.")
            return None

        # création d'un fichier temporaire pour le résultat généré par la calculatrice raster
        path_diff = os.path.join(temp_path, f"diff_{int(niveau_eau * 100)}.tif")

        # création d'une expression raster unique avec le niveau d'eau à étudier
        expression = f"{niveau_eau} - \"parcelle_decoupee@1\""

        # 3.7.3. utilisation de la "Calculatrice raster"
        processing.run("native:rastercalc", {
            'LAYERS': [layer_clip],
            'EXPRESSION': expression,
            'EXTENT': layer_clip.extent(),
            'CELL_SIZE': layer_clip.rasterUnitsPerPixelX(),
            'CRS': layer_clip.crs(),
            'OUTPUT': path_diff
        })

        # création d'un fichier temporaire pour la reclassification
        path_reclass = os.path.join(temp_path, f"reclass_{int(niveau_eau * 100)}.tif")

        # 3.7.4. utilisation de l'outil natif "Reclassification" pour supprimer les valeurs négatives
        processing.run("native:reclassifybytable", {
            'INPUT_RASTER': path_diff,
            'RASTER_BAND': 1,
            'TABLE': ['-9999', '0', 'nan'],  # remplacer les valeurs négatives par NaN
            'NO_DATA': -9999,
            'RANGE_BOUNDARIES': 0,
            'NODATA_FOR_MISSING': False,
            'DATA_TYPE': 5,
            'CREATE_OPTIONS': None,
            'OUTPUT': path_reclass
        })
        return path_reclass


    # étape interne à la génération des rasters
    # fonction permettant de ré-échantillonné le raster pour alléger et la donnée
    # la fonction est répétée automatiquement autant de fois qu'il y a de niveaux d'eau à traiter puisqu'elle est traitée par la boucle
    def resample_raster(self, input_path, output_name):

        # vérification de la validité du chemin d'entrée
        layer_reclass = QgsRasterLayer(input_path, "reclass_layer")
        if not layer_reclass.isValid():
            QMessageBox.warning(self, "Erreur", f"La couche à rééchantillonner n'est pas valide: {input_path}")
            return None

        '''
        
        # A VOIR SI SUPPRESSION
        
        # ajustement : ajout découpage pour éviter la création d'un contour rectangulaire aberrant lors de la création du raster
        path_reclip = os.path.join(temp_path, f"{output_name}_reclip.tif")
        selected_vecteur = getattr(self, 'selected_vecteur_path', None)

        processing.run("gdal:cliprasterbymasklayer", {
            'INPUT': layer_reclass,
            'MASK': selected_vecteur,
            'SOURCE_CRS': QgsCoordinateReferenceSystem('EPSG:2154'),
            'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:2154'),
            'TARGET_EXTENT': None,
            'NODATA': -9999,
            'ALPHA_BAND': False,
            'CROP_TO_CUTLINE': True,
            'KEEP_RESOLUTION': False,
            'SET_RESOLUTION': False,
            'X_RESOLUTION': None,
            'Y_RESOLUTION': None,
            'MULTITHREADING': False,
            'OPTIONS': None,
            'DATA_TYPE': 0,
            'EXTRA': '',
            'OUTPUT': path_reclip})
            
        # NB : changer l'input de r.resamp.stats en "path_reclip" si conservation

        '''

        # création d'un fichier final pour le raster rééchantillonné
        path_resamp = os.path.join(temp_path, f"{output_name}_resamp.tif")

        # récupération de la valeur de résolution souhaitée par l'utilisateur
        # NB : la résolution dépend du raster en entrée avant de dépendre du raster en sortie
        # un raster ne peut pas être ré-échantillonné selon une valeur inférieure à celle de sa résolution de base
        resolution = self.inputResol.value()

        # 3.7.1. utilisation de l'algorithme GRASS "r.resamp.Stats" pour le ré-échantillonnage
        processing.run("grass:r.resamp.stats", {
            'input': layer_reclass,
            'method': 1,  # mediane
            'quantile': 0.5,
            '-n': True,
            '-w': False,
            'output': path_resamp,
            'GRASS_REGION_PARAMETER': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': resolution,  # résolution de 25cm
            'GRASS_RASTER_FORMAT_OPT': '',
            'GRASS_RASTER_FORMAT_META': ''
        })

        # 3.7.2. calcul automatique de la surface après création du raster
        if os.path.exists(path_resamp):
            (surface_totale, _, volume_total,
             classe_1_surf, classe_2_surf, classe_3_surf, classe_4_surf,
             classe_5_surf, classe_6_surf, classe_7_surf) = self.calculer_stats_raster(path_resamp)

        else:
            QgsMessageLog.logMessage(f"Le fichier raster {path_resamp} n'existe pas", "Top'Eau", Qgis.Warning)
            return None

        return path_resamp


    # étape interne à la génération des rasters
    # fonction permettant de vectoriser le raster généré afin d'en récupérer la géométrie
    # la fonction est répétée automatiquement autant de fois qu'il y a de niveaux d'eau à traiter puisqu'elle est traitée par la boucle
    def vectoriser_raster (self, path_resamp, output_name) :

        try:

            # récupération du raster ré-échantillonné
            if path_resamp is None:
                raise Exception(f"Impossible d'ouvrir le raster {path_resamp}")

            # création d'un chemin temporaire pour le vecteur créé
            raster_vectorise = os.path.join(temp_path, f"{output_name}_vecteur.gpkg")

            # utilisation de l'algorithme GDAL "Polygoniser" pour passer le raster généré en vecteur
            processing.run("gdal:polygonize", {
                'INPUT': path_resamp,
                'BAND': 1,
                'FIELD': 'DN',
                'EIGHT_CONNECTEDNESS': False,
                'EXTRA': '',
                'OUTPUT': raster_vectorise
            })

            return raster_vectorise

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur vectorisation du raster: {str(e)}", "Top'Eau", Qgis.Critical)
            return None


    # étape interne à la génération des rasters
    # fonction permettant d'assigner les calculs de surface et volume aux pixels non nuls du raster généré
    # la fonction est répétée automatiquement autant de fois qu'il y a de niveaux d'eau à traiter puisqu'elle est traitée par la boucle
    def calculer_stats_raster(self, path_resamp):

        try:
            # traitement du raster avec GDAL
            dataset = gdal.Open(path_resamp)
            if dataset is None:
                raise Exception(f"Impossible d'ouvrir le raster {path_resamp}")

            # 3.7.1. récupération des informations du raster
            band = dataset.GetRasterBand(1)
            geo_transform = dataset.GetGeoTransform()

            # 3.7.2 récupération de la résolution des pixels
            pixel_width = abs(geo_transform[1])  # largeur d'un pixel
            pixel_height = abs(geo_transform[5])  # hauteur d'un pixel
            surface_pixel = pixel_width * pixel_height  # surface d'un pixel en m²

            # 3.7.3. lecture des données du raster
            data = band.ReadAsArray()
            nodata_value = band.GetNoDataValue()

            # 3.7.4. comptage des pixels non-nuls
            if nodata_value is not None:
                pixels_valides = np.count_nonzero(~np.isnan(data) & (data != nodata_value))
            else:
                pixels_valides = np.count_nonzero(~np.isnan(data) & (data != 0))

            # 3.7.5. calcul de la surface totale
            surface_totale = pixels_valides * surface_pixel

            # 3.7.6. calcul du volume : somme des hauteurs d'eau valides × surface d'un pixel
            if nodata_value is not None:
                mask = (~np.isnan(data)) & (data != nodata_value)
            else:
                mask = (~np.isnan(data)) & (data != 0)

            # 3.7.7. calcul de la surface en fonction de classes prédéfinies
            pixels_cl1 = np.count_nonzero((data > 0) & (data <= 0.05))
            classe_1_surf = pixels_cl1 * surface_pixel

            pixels_cl2 = np.count_nonzero((data > 0.05) & (data <= 0.10))
            classe_2_surf = pixels_cl2 * surface_pixel

            pixels_cl3 = np.count_nonzero((data > 0.10) & (data <= 0.15))
            classe_3_surf = pixels_cl3 * surface_pixel

            pixels_cl4 = np.count_nonzero((data > 0.15) & (data <= 0.20))
            classe_4_surf = pixels_cl4 * surface_pixel

            pixels_cl5 = np.count_nonzero((data > 0.20) & (data <= 0.25))
            classe_5_surf = pixels_cl5 * surface_pixel

            pixels_cl6 = np.count_nonzero((data > 0.25) & (data <= 0.30))
            classe_6_surf = pixels_cl6 * surface_pixel

            pixels_cl7 = np.count_nonzero(data > 0.30)
            classe_7_surf = pixels_cl7 * surface_pixel

            pixels_valides = np.count_nonzero(mask)
            surface_totale = pixels_valides * surface_pixel
            volume_total = np.sum(data[mask]) * surface_pixel

            return surface_totale, pixels_valides, volume_total, classe_1_surf, classe_2_surf, classe_3_surf, classe_4_surf, classe_5_surf, classe_6_surf, classe_7_surf

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur calcul surface raster: {str(e)}", "Top'Eau", Qgis.Critical)
            return None, None, None
        finally:
            dataset = None


    # 4. création du GPKG et de sa table attributaire "hauteur_eau"
    def creer_gpkg_initial(self, gpkg_path, valeur_min, valeur_max, valeur_moy, valeur_med):

        # import des librairies propres à cette fonction pour la récupération de la date de création
        import os
        from datetime import datetime

        self.deciles_calcules = {}

        try:

            # instauration d'une variable permettant de récupérer la date de création du fichier
            date_creation = datetime.now().strftime('%Y-%m-%d')

            # 4.1. création d'un GPKG avec GDAL
            driver = gdal.GetDriverByName('GPKG')
            ds = driver.Create(gpkg_path, 1, 1, 1, gdal.GDT_Byte)
            if ds is None:
                raise Exception(f"Impossible de créer le GPKG {gpkg_path}")
            ds = None

            # récupération du raster découpé pour calculer les déciles
            path_clip = os.path.join(temp_path, "temp_layer_clip.tif")

            # vérification de l'existence du fichier
            if not os.path.exists(path_clip):
                QgsMessageLog.logMessage(f"Le fichier raster {path_clip} n'existe pas", "Top'Eau", Qgis.Warning)
                # utilisation des valeurs par défaut pour les déciles
                data_pixels = None
            else:
                # traitement du raster avec GDAL
                dataset = gdal.Open(path_clip)
                if dataset is None:
                    QgsMessageLog.logMessage(f"Impossible d'ouvrir le raster {path_clip}", "Top'Eau", Qgis.Warning)
                    data_pixels = None
                else:
                    # récupération des informations du raster
                    band = dataset.GetRasterBand(1)
                    # lecture des données du raster
                    data_pixels = band.ReadAsArray()
                    nodata_value = band.GetNoDataValue()
                    dataset = None

            # connexion SQLite au GPKG créé pour pouvoir effectuer des requêtes sur ses données (création, insertion...)
            conn = sqlite3.connect(gpkg_path)
            cursor = conn.cursor()

            # connexion SpatiaLite pour pouvoir créer et générer des géométries valides
            conn.enable_load_extension(True)
            spatialite_loaded = False

            try:
                # vérification du chargement de SpatiaLite si disponible
                conn.load_extension("mod_spatialite")
                cursor.execute("SELECT InitSpatialMetaData(1)")
                spatialite_loaded = True
                QgsMessageLog.logMessage("SpatiaLite activé", "Top'Eau", Qgis.Info)
            except:
                try:
                    # essayer avec spatialite sur certains systèmes
                    conn.load_extension("spatialite")
                    cursor.execute("SELECT InitSpatialMetaData(1)")
                    spatialite_loaded = True
                    QgsMessageLog.logMessage("SpatiaLite activé (spatialite)", "Top'Eau", Qgis.Info)
                except:
                    # utilisation des fonctions GPKG natives si pas de connexion spatialite
                    spatialite_loaded = False
                    QgsMessageLog.logMessage("SpatiaLite non disponible, utilisation des fonctions GPKG natives",
                                             "Top'Eau", Qgis.Info)

            # stockage de l'état de connexion pour les autres fonctions
            self.spatialite_loaded = spatialite_loaded

            # 4.1.1. Création des tables système GeoPackage obligatoires
            # création de la table pour les systèmes de référence : table gpkg_spatial_ref_sys
            cursor.execute('''
                        CREATE TABLE IF NOT EXISTS gpkg_spatial_ref_sys (
                            srs_name TEXT NOT NULL,
                            srs_id INTEGER NOT NULL PRIMARY KEY,
                            organization TEXT NOT NULL,
                            organization_coordsys_id INTEGER NOT NULL,
                            definition TEXT NOT NULL,
                            description TEXT
                        )
                    ''')

            # insertion du SCR Lambert 93 EPSG[2154]
            cursor.execute('''
                        INSERT OR REPLACE INTO gpkg_spatial_ref_sys 
                        (srs_name, srs_id, organization, organization_coordsys_id, definition, description)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                'RGF93 / Lambert-93',
                2154,
                'EPSG',
                2154,
                'PROJCS["RGF93 / Lambert-93",GEOGCS["RGF93",DATUM["Reseau_Geodesique_Francais_1993",SPHEROID["GRS 1980",6378137,298.257222101,AUTHORITY["EPSG","7019"]],AUTHORITY["EPSG","6171"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4171"]],PROJECTION["Lambert_Conformal_Conic_2SP"],PARAMETER["standard_parallel_1",49],PARAMETER["standard_parallel_2",44],PARAMETER["latitude_of_origin",46.5],PARAMETER["central_meridian",3],PARAMETER["false_easting",700000],PARAMETER["false_northing",6600000],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AUTHORITY["EPSG","2154"]]',
                'Lambert 93 France'
            ))

            # création de la table contenant le catalogue de contenus : table gpkg_contents
            cursor.execute('''
                        CREATE TABLE IF NOT EXISTS gpkg_contents (
                            table_name TEXT NOT NULL PRIMARY KEY,
                            data_type TEXT NOT NULL,
                            identifier TEXT UNIQUE,
                            description TEXT DEFAULT '',
                            last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                            min_x DOUBLE,
                            min_y DOUBLE,
                            max_x DOUBLE,
                            max_y DOUBLE,
                            srs_id INTEGER,
                            CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
                        )
                    ''')

            # création de la table contenant les informations géométriques : table gpkg_geometry_columns
            cursor.execute('''
                        CREATE TABLE IF NOT EXISTS gpkg_geometry_columns (
                            table_name TEXT NOT NULL,
                            column_name TEXT NOT NULL,
                            geometry_type_name TEXT NOT NULL,
                            srs_id INTEGER NOT NULL,
                            z TINYINT NOT NULL,
                            m TINYINT NOT NULL,
                            CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
                            CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
                            CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
                        )
                    ''')

            # création de la table contenant les informations liées à l'extension : table gpkg_extensions
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS gpkg_extensions (
                    table_name TEXT,
                    column_name TEXT,
                    extension_name TEXT NOT NULL,
                    definition TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    CONSTRAINT ge_tce UNIQUE (table_name, column_name, extension_name)
                )
            ''')

            # création de la table pour les triggers de validation géométrique : table gpkg_data_columns
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS gpkg_data_columns (
                    table_name TEXT NOT NULL,
                    column_name TEXT NOT NULL,
                    name TEXT,
                    title TEXT,
                    description TEXT,
                    mime_type TEXT,
                    constraint_name TEXT,
                    CONSTRAINT pk_gdc PRIMARY KEY (table_name, column_name)
                )
            ''')

            # 4.2. récupération d'informations nécessaires à l'insertion de données attributaires dans les tables

            # 4.2.1. récupération de la date de création du fichier après sa création
            try:
                if os.path.exists(gpkg_path):
                    # utilisation la date de création (Windows) ou de modification (Linux)
                    if os.name == 'nt':
                        # instauration d'une variable adaptée à Windows
                        creation_timestamp = os.path.getctime(gpkg_path)
                    else:  # instauration d'une variable adaptée à Linux
                        creation_timestamp = os.path.getmtime(gpkg_path)

                    # conversion du timestamp en format de date
                    date_creation = datetime.fromtimestamp(creation_timestamp).strftime('%Y-%m-%d')
            except Exception :
                QgsMessageLog.logMessage(f"Impossible de récupérer la date de création du fichier","Top'Eau", Qgis.Warning)

            # 4.2.2. calcul des déciles pour les ajouter à la table attributaire "zone_etude"
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
                        # calcul des déciles avec numpy
                        percentiles = np.arange(10, 100, 10)
                        valeurs_deciles = np.percentile(pixels_valides, percentiles)
                        # arrondir les valeurs récupérées
                        for i, percentile in enumerate(percentiles):
                            deciles[f'decile_{int(percentile)}'] = round(valeurs_deciles[i], 2)

                        self.deciles_calcules = deciles

                        QgsMessageLog.logMessage(f"Déciles calculés avec succès", "Top'Eau", Qgis.Info)
                    else:
                        QgsMessageLog.logMessage(f"Aucune valeur valide pour le calcul des déciles", "Top'Eau",
                                                     Qgis.Warning)
                else:
                    QgsMessageLog.logMessage(f"Aucune donnée de pixels fournie pour le calcul des déciles",
                                                 "Top'Eau", Qgis.Warning)
            except Exception as decile_error:
                QgsMessageLog.logMessage(f"Erreur lors du calcul des déciles : {str(decile_error)}", "Top'Eau",
                                             Qgis.Warning)


            # 4.2.3. récupération de la géométrie du polygone correspondant à la zone d'étude
            # instauration d'une variable qui servira pour la récupération de la géométrie en WKT
            # puis en WKB pour être reconnue commme colonne à géométrie valide pour le GPKG
            geometry_wkt = None
            geometry_wkb = None
            surface_ze = 0.0
            srid = 2154 # code EPSG du Lambert 93
            geometry_type = 'MULTIPOLYGON'
            min_x, min_y, max_x, max_y = None, None, None, None

            # configuration de QgsDistanceArea pour récupérer la surface du polygone d'entrée
            da = QgsDistanceArea()
            try:
                if hasattr(self, 'selected_vecteur_path') and self.selected_vecteur_path is not None:

                    # récupération du SRID de la couche source
                    if hasattr(self.selected_vecteur_path, 'crs'):
                        srid = self.selected_vecteur_path.crs().postgisSrid()

                    # récupération des entités du vecteur sélectionné
                    features = self.selected_vecteur_path.getFeatures()

                    # boucle sur chacune des entités polygonales détectées dans la couche vecteur
                    for feature in features:
                        # récupération de la géométrie de la première entité
                        geom = feature.geometry()
                        # calcul de la surface de l’entité
                        surface_cal = da.measureArea(geom)
                        if geom and not geom.isEmpty():
                            # passage de la géométrie récupérée en WKT pour être retranscrite et lue en table
                            geometry_wkt = geom.asWkt()
                            geometry_wkb = geom.asWkb()
                            surface_ze += surface_cal

                            # Calcul des extent pour gpkg_contents
                            bbox = geom.boundingBox()
                            min_x = bbox.xMinimum()
                            min_y = bbox.yMinimum()
                            max_x = bbox.xMaximum()
                            max_y = bbox.yMaximum()

                            QgsMessageLog.logMessage(f"Géométrie récupérée pour l'emprise", "Top'Eau", Qgis.Info)
                            break
                        else:
                            QgsMessageLog.logMessage(f"Géométrie vide dans selected_vecteur", "Top'Eau", Qgis.Warning)
                    else:
                        QgsMessageLog.logMessage(f"Aucune entité trouvée dans selected_vecteur", "Top'Eau", Qgis.Warning)
                else:
                    QgsMessageLog.logMessage(f"Variable selected_vecteur non disponible", "Top'Eau", Qgis.Warning)
            except Exception as geom_error:
                QgsMessageLog.logMessage(f"Erreur lors de la récupération de la géométrie : {str(geom_error)}","Top'Eau", Qgis.Warning)

            # 4.3. connexion au GPKG
            # conn = sqlite3.connect(gpkg_path)
            # cursor = conn.cursor()

            # 4.4. création des tables attributaires à l'intérieur du GPKG

            # 4.4.1. création et insertion des données pour la table "zone_etude"
            table_creation_sql = '''
                        CREATE TABLE zone_etude (
                            id INTEGER PRIMARY KEY AUTOINCREMENT, 
                            nom TEXT,
                            emprise GEOMETRY,
                            surface_m2 REAL,
                            min_parcelle REAL,
                            max_parcelle REAL,
                            moyenne_parcelle REAL,
                            mediane_parcelle REAL'''

            # Ajout des colonnes pour les déciles
            for i in range(10, 100, 10):
                table_creation_sql += f',\n decile_{i} REAL'

            table_creation_sql += '\n )'

            cursor.execute(table_creation_sql)

            # enregistrement dans gpkg_contents AVANT gpkg_geometry_columns
            cursor.execute('''
                        INSERT INTO gpkg_contents 
                        (table_name, data_type, identifier, description, last_change, min_x, min_y, max_x, max_y, srs_id) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                'zone_etude',
                'features',
                'zone_etude',
                'Zone d\'étude pour simulation Top\'Eau',
                datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                min_x, min_y, max_x, max_y,
                srid
            ))

            # ajout de la colonne géométrique via la maj des métadonnées du GPKG
            cursor.execute('''
                        INSERT INTO gpkg_geometry_columns 
                        (table_name, column_name, geometry_type_name, srs_id, z, m) 
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', ('zone_etude', 'emprise', geometry_type, srid, 0, 0))

            # préparation de la requête d'insertion avec les déciles
            insert_columns = '''nom, emprise, surface_m2, min_parcelle, max_parcelle, moyenne_parcelle, mediane_parcelle'''
            insert_values = '''?, ?, ?, ?, ?, ?, ?'''

            # ajout des colonnes et valeurs pour les déciles
            for i in range(10, 100, 10):
                insert_columns += f', decile_{i}'
                insert_values += ', ?'

            # création de la couche géométrique si le Wkb est récupéré
            if geometry_wkb:
                cursor.execute('''
                    INSERT INTO zone_etude(nom, emprise, surface_m2, min_parcelle, max_parcelle, moyenne_parcelle, mediane_parcelle, {}) 
                    VALUES (?, ST_GeomFromWKB(?, ?), ?, ?, ?, ?, ?, {})
                '''.format(
                    ', '.join([f'decile_{i}' for i in range(10, 100, 10)]),
                    ', '.join(['?' for i in range(10, 100, 10)])
                ), [
                       self.nomZE.text(),
                       geometry_wkb,
                       srid,
                       surface_ze,
                       round(self.valeur_min, 2),
                       round(self.valeur_max, 2),
                       round(self.valeur_moy, 2),
                       round(self.valeur_med, 2)
                   ] + [deciles.get(f'decile_{i}', None) for i in range(10, 100, 10)])

            # 4.4.2. création de la table "hauteur_eau"
            # NB : l'insertion des données se fait dans une fonction dédiée car ce sont des données récupérées en fonction
            # des rasters créés et non en fonction du GPKG créé
            cursor.execute('''
                CREATE TABLE hauteur_eau (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    niveau_eau REAL,
                    nom TEXT,
                    surface_eau_m2 REAL,
                    volume_eau_m3 REAL,
                    classe_1 REAL,
                    classe_2 REAL,
                    classe_3 REAL,
                    classe_4 REAL,
                    classe_5 REAL,
                    classe_6 REAL,
                    classe_7 REAL,
                    geom GEOMETRY,
                    nom_fichier TEXT
                )
            ''')
            # enregistrement dans gpkg_contents pour hauteur_eau (sans extent pour l'instant)
            cursor.execute('''
                        INSERT INTO gpkg_contents 
                        (table_name, data_type, identifier, description, last_change, srs_id) 
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                'hauteur_eau',
                'features',
                'hauteur_eau',
                'Surfaces inondées pour différents niveaux d\'eau',
                datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                srid
            ))

            # ajout de la colonne géométrique via la maj des métadonnées du GPKG
            cursor.execute('''
                        INSERT INTO gpkg_geometry_columns 
                        (table_name, column_name, geometry_type_name, srs_id, z, m) 
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', ('hauteur_eau', 'geom', 'MULTIPOLYGON', srid, 0, 0))

            # 4.4.3. création de la table "mesure"
            # NB : la table est vide car c'est celle qui sera utilsiée plus tard pour le requêtage SQL
            cursor.execute('''
                CREATE TABLE mesure (
                    id INTEGER PRIMARY KEY, 
                    date DATE,
                    niveau_eau REAL
                )
            ''')

            # 4.4.4. création et insertion des données dans la table "metadata_md1"
            # NB : les noms de champ et leur complétion ont été définis en fonction des documents qualité créés
            # par Olivier Schmit
            cursor.execute('''
                CREATE TABLE metadata_md1 (
                    id INTEGER PRIMARY KEY, 
                    nom_du_fichier TEXT,            
                    mots_clefs TEXT,
                    createur TEXT,
                    contributeur TEXT,
                    referent_metadonnees TEXT,
                    personnes_a_contacter TEXT,
                    description TEXT,
                    date_de_creation DATE,
                    type_de_donnees TEXT,
                    format TEXT,
                    langage TEXT,
                    relation TEXT,
                    extension_spatiale TEXT, 
                    provenance TEXT,
                    droits TEXT           
                    )
                ''')
            cursor.execute('''
                INSERT INTO metadata_md1(
                    nom_du_fichier,
                    mots_clefs,
                    createur,
                    contributeur,
                    referent_metadonnees,
                    personnes_a_contacter,
                    description,
                    date_de_creation,
                    type_de_donnees,
                    format,
                    langage,
                    relation,
                    extension_spatiale,
                    provenance,
                    droits
                ) 
                VALUES (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?
                )''', (
                    '_topeau.gpkg',
                    'Variables hydriques, mesure du niveau d\'eau, simulation inondation, parcelles, marais littoraux atlantiques, INRAE',
                    'Marion Bleuse',
                    'Julien Ancelin',
                    'Olivier Schmit',
                    'marion.bleuse8@gmail.com / julien.ancelin@inrae.fr / lilia.mzali@inrae.fr',
                    'Se référer à la fenêtre \'A propos\' du Plugin Top\'Eau',
                    date_creation,
                    'GeoPackage contenant des fichiers raster et attributaires',
                    'GeoPackage (.gpkg)',
                    'Français',
                    'Se référer à la notice d\'utilisation du Plugin disponible via la fenêtre \'Notice\' du Plugin Top\'Eau',
                    'Zone d\'étude située au sein d\'un des sites du Projet MAVI porté par l\'Unité Expérimentale INRAE de Saint-Laurent-de-la-Prée',
                    'Résultat de l\'automatisation de traîtements effectués par le Plugin Top\'Eau',
                    'CC-BY-NC-ND'
                )
            )

            # 4.4.5. création et insertion des données dans la table "metadata_md2"
            # NB : les noms de champ et leur complétion ont été définis en fonction des documents qualité créés
            # par Olivier Schmit
            cursor.execute('''
                CREATE TABLE metadata_md2 (
                    id INTEGER PRIMARY KEY, 
                    date___mesure TEXT,            
                    niveau_eau___mesure TEXT,
                    nom___zone_etude TEXT,
                    surface_m2___zone_etude TEXT,
                    min_parcelle___zone_etude TEXT,
                    max_parcelle___zone_etude TEXT,
                    moyenne_parcelle___zone_etude TEXT,
                    mediane_parcelle___zone_etude TEXT,
                    niveau_eau___hauteur_eau TEXT,
                    nom___hauteur_eau TEXT,
                    surface_eau_m2___hauteur_eau TEXT,
                    volume_eau_m3___hauteur_eau TEXT,
                    classe_1___hauteur_eau TEXT,
                    classe_2___hauteur_eau TEXT, 
                    classe_3___hauteur_eau TEXT, 
                    classe_4___hauteur_eau TEXT,
                    classe_5___hauteur_eau TEXT,
                    classe_6___hauteur_eau TEXT, 
                    classe_7___hauteur_eau TEXT,
                    nom_fichier___hauteur_eau TEXT         
                )
            ''')
            cursor.execute('''
                INSERT INTO metadata_md2(
                    date___mesure,            
                    niveau_eau___mesure,
                    nom___zone_etude,
                    surface_m2___zone_etude,
                    min_parcelle___zone_etude,
                    max_parcelle___zone_etude,
                    moyenne_parcelle___zone_etude,
                    mediane_parcelle___zone_etude,
                    niveau_eau___hauteur_eau,
                    nom___hauteur_eau,
                    surface_eau_m2___hauteur_eau,
                    volume_eau_m3___hauteur_eau,
                    classe_1___hauteur_eau,
                    classe_2___hauteur_eau, 
                    classe_3___hauteur_eau, 
                    classe_4___hauteur_eau,
                    classe_5___hauteur_eau,
                    classe_6___hauteur_eau, 
                    classe_7___hauteur_eau,
                    nom_fichier___hauteur_eau
                    ) 
                VALUES (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?
                )''', (
                    'Date relevée pour la mesure du niveau d\'eau dans la parcelle (bouée, piézomètre, relevé terrain)',
                    'Niveau relevé pour la mesure du niveau d\'eau dans la parcelle (bouée, piézomètre, relevé terrain)',
                    'Nom donné par l\'utilisateur pour la zone qu\'il étudie',
                    'Surface du polygone correspondant à la zone d\'étude (en m²)',
                    'Point le plus bas de la parcelle (en mètre)',
                    'Point le plus haut de la parcelle (en mètre)',
                    'Elévation moyenne dans la parcelle (en mètre)',
                    'Valeur médiane pour l\'élévation de la parcelle (en mètre)',
                    'Valeur simulée & étudiée pour l\'emprise hydrique dans la parcelle (en mètre)',
                    'Nom donné par l\'utilisateur pour la zone qu\'il étudie',
                    'Surface couverte par l\'eau selon le niveau simulé dans la parcelle (en m²)',
                    'Volume d\'eau dans la zone d\'étude selon le niveau simulé dans la parcelle (en m³)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 1 : 0 - 5 cm (en m²)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 2 : 5 - 10 cm (en m²)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 3 : 10 - 15 cm (en m²)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 4 : 15 - 20 cm (en m²)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 5 : 20 - 25 cm (en m²)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 6 : 25 - 30 cm (en m²)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 7 : > 30 cm (en m²)',
                    'Nom donné au raster lors de sa génération et son extension'
                )
            )

            conn.commit()
            conn.close()

            QgsMessageLog.logMessage(f"GPKG créé : {gpkg_path}", "Top'Eau", Qgis.Info)

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur création GPKG : {str(e)}", "Top'Eau", Qgis.Critical)
            raise e

    # étape interne à la génération des rasters
    # fonction permettant de formater les TIFF pour qu'ils passent en GeoPackage
    # la fonction est répétée automatiquement autant de fois qu'il y a de niveaux d'eau à traiter puisqu'elle est traitée par la boucle
    def ajouter_raster_au_gpkg(self, path_resamp, gpkg_path, table_name):

        try:
            # vérification de l'existence du GPKG
            if not os.path.exists(gpkg_path):
                QgsMessageLog.logMessage(f"GPKG inexistant: {gpkg_path}", Qgis.Warning)
                return False

            # 3.7.1. utilisation de l'API GDAL pour la conversion
            try:
                # ouverture du raster source avec GDAL
                src_ds = gdal.Open(path_resamp)
                if src_ds is None:
                    QMessageBox.warning(self, "Erreur", f"Impossible d'ouvrir le fichier source: {path_resamp}")
                    return None

                # lecture des métadonnées du raster source
                band = src_ds.GetRasterBand(1)
                data_type = band.DataType
                xsize = src_ds.RasterXSize
                ysize = src_ds.RasterYSize
                geo_transform = src_ds.GetGeoTransform()
                projection = src_ds.GetProjection()

                # conversion du raster via l'ajout d'un driver GDAL
                driver = gdal.GetDriverByName('GPKG')
                if driver is None:
                    QMessageBox.warning(self, "Erreur",
                                        "Le pilote GPKG n'est pas disponible dans cette installation GDAL")
                    return None

                # configuration des options de création du GPKG
                options = ['-of', 'GPKG','-co', f'RASTER_TABLE={table_name}','-co', 'APPEND_SUBDATASET=YES']

                # création du GeoPackage
                # modifier le type de données à Float32 qui est compatible avec GeoPackage
                dst_ds = driver.Create(gpkg_path, xsize, ysize, 1, gdal.GDT_Float32, options)

                # vérification de la validité du GPKG créé
                if dst_ds is None:
                    QMessageBox.warning(self, "Erreur", f"Impossible de créer le fichier GeoPackage")
                    return None

                # copie des métadonnées géospatiales
                dst_ds.SetGeoTransform(geo_transform)
                dst_ds.SetProjection(projection)
                # copie des données
                data = band.ReadAsArray(0, 0, xsize, ysize)
                dst_band = dst_ds.GetRasterBand(1)

                # définition de la valeur nodata puisqu'elle existe et qu'on veut s'en servir pour les calculs de stat
                nodata_value = band.GetNoDataValue()
                if nodata_value is not None:
                    dst_band.SetNoDataValue(nodata_value)

                # écriture des données
                dst_band.WriteArray(data)
                # traitement du cache
                dst_ds.FlushCache()
                dst_ds = None
                src_ds = None

                # vérification de la création du GPKG
                if os.path.exists(gpkg_path):
                    QgsMessageLog.logMessage(f"GeoPackage créé avec succès: {gpkg_path}", "Top'Eau", Qgis.Success)
    
                    # ajout d'un fichier de style
                    qml_file = os.path.join(os.path.dirname(__file__), 'style', 'style_topeau.qml')
                    try:
                        # 1. chargement de la couche raster depuis le GeoPackage
                        uri = f"GPKG:{gpkg_path}:{table_name}"
                        rlayer = QgsRasterLayer(uri, table_name, 'gdal')
                        if not rlayer.isValid():
                            raise ValueError(f"Impossible de charger {uri} comme QgsRasterLayer")
    
                        # 2. enregistrement temporairement dans le projet (nécessaire pour saveStyleToDatabase)
                        proj = QgsProject.instance()
                        proj.addMapLayer(rlayer, False)
    
                        # 3. liste des sous-couches GDAL
                        QgsMessageLog.logMessage(
                            f"Sous-couches détectées pour {table_name}: {rlayer.dataProvider().subLayers()}",
                            "Top'Eau", Qgis.Info
                        )
    
                        # 4. chargement du QML et application à la couche (pour être sûr que le style est valide)
                        rlayer.loadNamedStyle(qml_file)
                        rlayer.triggerRepaint()
    
                        # 5. sauvegarde dans la table layer_styles du GPKG
                        err = rlayer.saveStyleToDatabase(
                            'default',          # nom du style
                            'Style embarqué',   # description
                            True,               # use as default
                            None                # on passe None : QGIS reprendra le style en mémoire
                        )
                        if err:
                            QgsMessageLog.logMessage(f"Erreur saveStyleToDatabase pour {table_name} : {err}", "Top'Eau", Qgis.Warning)
                        else:
                            QgsMessageLog.logMessage(f"Symbologie embarquée dans {table_name}", "Top'Eau", Qgis.Info)
    
                        # 6. nettoyage : retirer la couche du projet (on n’en a plus besoin)
                        proj.removeMapLayer(rlayer.id())
    
                    except Exception as e:
                        QgsMessageLog.logMessage(f"Échec injection style QML : {e}", "Top'Eau", Qgis.Warning)
    
                    return gpkg_path
                else:
                    QMessageBox.warning(self, "Erreur", f"Le GeoPackage n'a pas été créé")
                    return None

            except Exception as e:
                QgsMessageLog.logMessage(f"Erreur lors de la conversion en GeoPackage: {str(e)}", "Top'Eau",
                                         Qgis.Critical)
                QMessageBox.warning(self, "Erreur GDAL", f"Erreur lors de la conversion en GeoPackage:\n{str(e)}")
                return None

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur ajout raster au GPKG : {str(e)}", "Top'Eau", Qgis.Critical)
            return False


    # étape interne à la génération des rasters
    # fonction permettant d'insérer les données dans la table attributaire du GPKG
    # la fonction est répétée automatiquement autant de fois qu'il y a de niveaux d'eau à traiter puisqu'elle est traitée par la boucle
    def ajouter_donnees_table_gpkg(self,
                                   gpkg_path, surface_totale, volume_total,
                                   classe_1_surf, classe_2_surf, classe_3_surf, classe_4_surf, classe_5_surf,
                                   classe_6_surf, classe_7_surf,
                                   raster_vectorise_path=None):

        from datetime import datetime

        try:
            # vérification de l'existence du GPKG
            if not os.path.exists(gpkg_path):
                QgsMessageLog.logMessage(f"GPKG inexistant pour ajout données: {gpkg_path}", "Top'Eau", Qgis.Warning)
                return False

            # génération du nom du raster pour la table
            nom_ze = self.nomZE.text()
            niveau_cm = int(self.current_level * 100)
            raster_name = f"{nom_ze}_{niveau_cm}cm_topeau.tif"

            # récupération de la géométrie du polygone correspondant à la surface inondée
            # instauration d'une variable qui servira pour la récupération de la géométrie en WKT
            geom_raster_wkb = None
            min_x, min_y, max_x, max_y = None, None, None, None

            try:
                if raster_vectorise_path and os.path.exists(raster_vectorise_path):
                    # chargement de la couche vecteur
                    vector_layer = QgsVectorLayer(raster_vectorise_path, "temp_vector", "ogr")

                    if vector_layer.isValid():
                        # récupération des entités du vecteur
                        features = vector_layer.getFeatures()

                        # création d'une géométrie unifiée de toutes les entités
                        all_geoms = []
                        for feature in features:
                            geom = feature.geometry()
                            if geom and not geom.isEmpty():
                                all_geoms.append(geom)

                        if all_geoms:
                            # fusion de toutes les géométries en une seule
                            if len(all_geoms) == 1:
                                unified_geom = all_geoms[0]
                            else:
                                unified_geom = QgsGeometry.unaryUnion(all_geoms)

                            if unified_geom and not unified_geom.isEmpty():
                                # conversion en MULTIPOLYGON si nécessaire
                                if unified_geom.wkbType() == QgsWkbTypes.Polygon:
                                    unified_geom.convertToMultiType()
                                geom_raster_wkb = unified_geom.asWkb()

                                # calcul des extent pour mise à jour de gpkg_contents
                                bbox = unified_geom.boundingBox()
                                min_x = bbox.xMinimum()
                                min_y = bbox.yMinimum()
                                max_x = bbox.xMaximum()
                                max_y = bbox.yMaximum()

                                QgsMessageLog.logMessage(f"Géométrie récupérée pour la surface inondée", "Top'Eau",
                                                         Qgis.Info)
                            else:
                                QgsMessageLog.logMessage(f"Échec de l'union des géométries", "Top'Eau", Qgis.Warning)
                        else:
                            QgsMessageLog.logMessage(f"Aucune géométrie valide trouvée", "Top'Eau", Qgis.Warning)
                    else:
                        QgsMessageLog.logMessage(f"Couche vecteur invalide: {raster_vectorise_path}", "Top'Eau",
                                                 Qgis.Warning)
                else:
                    QgsMessageLog.logMessage(f"Chemin du vecteur non fourni ou inexistant", "Top'Eau", Qgis.Warning)

            except Exception as geom_error:
                QgsMessageLog.logMessage(f"Erreur lors de la récupération de la géométrie : {str(geom_error)}",
                                         "Top'Eau", Qgis.Warning)

            # 3.7.1. connexion SQLite directe au GeoPackage
            conn = sqlite3.connect(gpkg_path)
            cursor = conn.cursor()

            # chargement de SpatiaLite pour cette connexion
            spatialite_loaded = False
            conn.enable_load_extension(True)

            try:
                conn.load_extension("mod_spatialite")
                spatialite_loaded = True
                QgsMessageLog.logMessage("SpatiaLite chargé pour cette connexion", "Top'Eau", Qgis.Info)
            except:
                try:
                    conn.load_extension("spatialite")
                    spatialite_loaded = True
                    QgsMessageLog.logMessage("SpatiaLite chargé (spatialite) pour cette connexion", "Top'Eau",
                                             Qgis.Info)
                except:
                    spatialite_loaded = False
                    QgsMessageLog.logMessage("SpatiaLite non disponible pour cette connexion", "Top'Eau", Qgis.Info)

            # 3.7.2. insertion du contenu dans la table
            if geom_raster_wkb:
                if spatialite_loaded:
                    # test de validité avec SpatiaLite
                    try:
                        cursor.execute("SELECT ST_IsValid(ST_GeomFromWKB(?, ?))", (geom_raster_wkb, 2154))
                        is_valid = cursor.fetchone()[0]

                        if not is_valid:
                            QgsMessageLog.logMessage("Géométrie invalide détectée, tentative de réparation", "Top'Eau",
                                                     Qgis.Warning)
                            # tentative de réparation de la géométrie si elle n'est pas valide
                            cursor.execute("SELECT ST_AsBinary(ST_MakeValid(ST_GeomFromWKB(?, ?)))",
                                           (geom_raster_wkb, 2154))
                            geom_result = cursor.fetchone()
                            if geom_result and geom_result[0]:
                                geom_raster_wkb = geom_result[0]
                    except Exception as e:
                        QgsMessageLog.logMessage(f"Erreur validation géométrie: {str(e)}", "Top'Eau", Qgis.Warning)

                    # insertion des données avec SpatiaLite
                    cursor.execute('''
                           INSERT INTO hauteur_eau 
                           (niveau_eau, nom, surface_eau_m2, volume_eau_m3,
                           classe_1, classe_2, classe_3, classe_4, classe_5, classe_6, classe_7,
                           geom, nom_fichier) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ST_GeomFromWKB(?, ?), ?)
                       ''', (
                        round(self.current_level, 2),
                        self.nomZE.text(),
                        round(surface_totale, 2),
                        round(volume_total, 2),
                        round(classe_1_surf, 2),
                        round(classe_2_surf, 2),
                        round(classe_3_surf, 2),
                        round(classe_4_surf, 2),
                        round(classe_5_surf, 2),
                        round(classe_6_surf, 2),
                        round(classe_7_surf, 2),
                        geom_raster_wkb,
                        2154,
                        raster_name
                    ))
                else:
                    # insertion directe avec les fonctions GPKG natives (géométrie en blob)
                    cursor.execute('''
                           INSERT INTO hauteur_eau 
                           (niveau_eau, nom, surface_eau_m2, volume_eau_m3,
                           classe_1, classe_2, classe_3, classe_4, classe_5, classe_6, classe_7,
                           geom, nom_fichier) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ''', (
                        round(self.current_level, 2),
                        self.nomZE.text(),
                        round(surface_totale, 2),
                        round(volume_total, 2),
                        round(classe_1_surf, 2),
                        round(classe_2_surf, 2),
                        round(classe_3_surf, 2),
                        round(classe_4_surf, 2),
                        round(classe_5_surf, 2),
                        round(classe_6_surf, 2),
                        round(classe_7_surf, 2),
                        geom_raster_wkb,
                        raster_name
                    ))

                # mise à jour des extent dans gpkg_contents
                if min_x is not None and min_y is not None and max_x is not None and max_y is not None:
                    cursor.execute('''
                                        SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) 
                                        FROM (
                                            SELECT ? as min_x, ? as min_y, ? as max_x, ? as max_y
                                            UNION 
                                            SELECT min_x, min_y, max_x, max_y FROM gpkg_contents WHERE table_name = 'hauteur_eau'
                                        )
                                    ''', (min_x, min_y, max_x, max_y))

                    result = cursor.fetchone()
                    if result and all(v is not None for v in result):
                        cursor.execute('''
                                            UPDATE gpkg_contents 
                                            SET min_x = ?, min_y = ?, max_x = ?, max_y = ?, 
                                                last_change = ?
                                            WHERE table_name = 'hauteur_eau'
                                        ''', (result[0], result[1], result[2], result[3],
                                              datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ')))

            else:
                # insertion sans géométrie si elle n'est pas disponible
                cursor.execute('''
                              INSERT INTO hauteur_eau 
                              (niveau_eau, nom, surface_eau_m2, volume_eau_m3,
                              classe_1, classe_2, classe_3, classe_4, classe_5, classe_6, classe_7,
                              nom_fichier) 
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                          ''', (
                    round(self.current_level, 2),
                    self.nomZE.text(),
                    round(surface_totale, 2),
                    round(volume_total, 2),
                    round(classe_1_surf, 2),
                    round(classe_2_surf, 2),
                    round(classe_3_surf, 2),
                    round(classe_4_surf, 2),
                    round(classe_5_surf, 2),
                    round(classe_6_surf, 2),
                    round(classe_7_surf, 2),
                    raster_name
                ))

            conn.commit()
            QgsMessageLog.logMessage(f"Données ajoutées avec succès à la table hauteur_eau", "Top'Eau", Qgis.Success)
            return True

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur ajout données table GPKG: {str(e)}", "Top'Eau", Qgis.Critical)
            raise e
        finally:
            if 'conn' in locals():
                conn.close()

    #fonction permettant de créer une couche vectorielle avec GDAL pour créer les entités polygonales des surfaces inondées
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


    # 5. fonction pour charger automatiquement les tables et rasters du GPKG dans QGIS
    def charger_gpkg_dans_qgis(self, gpkg_path, couches_generees):

        try:
            # référence à l'interface QGIS
            from qgis.utils import iface

            # 5.1. création d'un groupe pour organiser les couches
            nom_ze = self.nomZE.text()
            root = QgsProject.instance().layerTreeRoot()
            group = root.addGroup(f"Top'Eau - {nom_ze}")

            # 5.2. chargement des tables attributaires
            tables_attributaires = ['zone_etude', 'hauteur_eau', 'mesure', 'metadata_md1', 'metadata_md2']

            for table in tables_attributaires:
                try:
                    # 5.2.1. création d'un URI pour les tables du GPKG
                    uri = f"{gpkg_path}|layername={table}"

                    # 5.2.2. création de la couche
                    layer = QgsVectorLayer(uri, f"{table}", "ogr")

                    if layer.isValid():
                        # 5.2.3. ajout de la couche au projet dans le groupe
                        QgsProject.instance().addMapLayer(layer, False)
                        group.addLayer(layer)
                        QgsMessageLog.logMessage(f"Table {table} chargée avec succès", "Top'Eau", Qgis.Info)
                    else:
                        QgsMessageLog.logMessage(f"Impossible de charger la table {table}", "Top'Eau", Qgis.Warning)

                except Exception as e:
                    QgsMessageLog.logMessage(f"Erreur lors du chargement de la table {table}: {str(e)}", "Top'Eau",
                                             Qgis.Warning)

            # 5.3. chargement des rasters

            # 5.3.1. récupération de la liste des rasters dans le GPKG
            rasters = self.lister_rasters_gpkg(gpkg_path)

            for raster_name in rasters:
                try:
                    # 5.3.2. création d'un URI pour les rasters du GPKG
                    uri = f"GPKG:{gpkg_path}:{raster_name}"

                    # 5.3.3. création de la couche raster
                    layer = QgsRasterLayer(uri, raster_name, "gdal")

                    if layer.isValid():
                        # 5.3.4. ajout de la couche au projet dans le groupe
                        QgsProject.instance().addMapLayer(layer, False)
                        group.addLayer(layer)

                        QgsMessageLog.logMessage(f"Raster {raster_name} chargé avec succès", "Top'Eau", Qgis.Info)
                    else:
                        QgsMessageLog.logMessage(f"Impossible de charger le raster {raster_name}", "Top'Eau",
                                                 Qgis.Warning)

                except Exception as e:
                    QgsMessageLog.logMessage(f"Erreur lors du chargement du raster {raster_name}: {str(e)}", "Top'Eau",
                                             Qgis.Warning)

            QMessageBox.information(self, "Chargement terminé",
                                    f"Le GPKG a été chargé avec succès dans QGIS.\n"
                                    f"Tables et rasters disponibles dans le groupe '{nom_ze}'.")

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors du chargement du GPKG: {str(e)}", "Top'Eau", Qgis.Critical)
            QMessageBox.warning(self, "Erreur", f"Erreur lors du chargement du GPKG:\n{str(e)}")


    # fonction nécessaire à la fonction précédente
    # fonction permettant de lister les rasters présents dans le GPKG
    def lister_rasters_gpkg(self, gpkg_path):

        rasters = []
        try:
            # connexion au GPKG pour lister les rasters
            conn = sqlite3.connect(gpkg_path)
            cursor = conn.cursor()

            # requête pour récupérer les tables raster
            cursor.execute("""
                SELECT table_name 
                FROM gpkg_contents 
                WHERE data_type = 'tiles' OR data_type = '2d-gridded-coverage'
            """)

            results = cursor.fetchall()
            rasters = [row[0] for row in results]

            conn.close()

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la récupération des rasters: {str(e)}", "Top'Eau", Qgis.Warning)

        return rasters

    # fonction permettant l'affichage de la fenêtre liée à la datavisualisation
    def lance_fenetre_graph(self):
        self.graph_window = VisuWindow(parent_widget=self)
        self.graph_window.exec_()


class VisuWindow(QDialog, form_graph):
    def __init__(self, parent_widget=None):
        QDialog.__init__(self)

        # Stocker la référence au widget parent qui contient les déciles
        self.parent_widget = parent_widget

        # création de l'interface de la fenêtre QGIS
        self.setupUi(self)
        # ajustement de la taille de la fenêtre pour qu'elle soit fixe
        #self.setFixedSize(600, 400)

        # nom donné à la fenêtre
        self.setWindowTitle("Top'Eau - Visualisation des statistiques liées aux données eau")

        # Bouton "OK / Annuler"
        self.terminer.rejected.connect(self.reject)

        # connexion de la barre de progression
        self.progressBar.setValue(0)

        # Bouton "Visualiser les déciles" - passer l'instance qui contient les déciles
        self.visuDeciles.clicked.connect(self.creer_graphique_deciles)

        # instauration de variables relatives à la création de l'interface graphiques
        layout = self.findChild(QVBoxLayout, 'layoutGraph')
        self.canvas = FigureCanvas(Figure())
        layout.addWidget(self.canvas)

    def creer_graphique_deciles(self):

        # récupération des attributs parents
        if (self.parent_widget and
                hasattr(self.parent_widget, 'deciles_calcules') and
                self.parent_widget.deciles_calcules):

            deciles_dict = self.parent_widget.deciles_calcules

            # extraction des valeurs des déciles
            valeurs_deciles = []
            for i in range(10, 100, 10):
                key = f'decile_{i}'
                if key in deciles_dict:
                    valeurs_deciles.append(deciles_dict[key])

                    # connexion de la barre de progression
                    self.progressBar.setValue(50)

                else:
                    valeurs_deciles.append(0)

            # création du graphique avec matplotlib
            df = pd.DataFrame({
                'Décile': [f'D{i}' for i in range(1, 10)],
                'Valeur': valeurs_deciles
            })

            fig, ax = plt.subplots(figsize=(5, 3))
            sns.barplot(data=df, x='Décile', y='Valeur', ax=ax)
            ax.set_title('Distribution des déciles pour la zone d\'étude')
            ax.set_xlabel('Déciles')
            ax.set_ylabel('Valeur (m)')

            self.canvas.figure = fig
            self.canvas.draw()

            # connexion de la barre de progression
            self.progressBar.setValue(100)

            QgsMessageLog.logMessage("Graphique des déciles créé avec succès", "Top'Eau", Qgis.Info)
        else:
            QgsMessageLog.logMessage("Aucun décile calculé disponible", "Top'Eau", Qgis.Warning)


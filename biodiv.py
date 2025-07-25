# -*- coding: utf-8 -*-

# Import module PyQt et API PyQGIS
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5 import uic
from PyQt5.QtGui import *
from qgis.core import *
from qgis.core import Qgis, QgsMessageLog
from qgis.utils import iface
from qgis import processing
import os
#import librairie nécessaire au requêtage SQL
import sqlite3
# import librairie lecture CSV
import pandas as pd
# import librairie manipulation de valeurs de type date
from datetime import datetime, timedelta

# import de la fonction de conversion de date
from . import conversion_date
from .conversion_date import convert_to_iso_date

# appel emplacement des fichiers de stockage des sorties temporaires -- temp
temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")

# lien entre traitement.py et traitement.ui
ui_path = os.path.dirname(os.path.abspath(__file__))
ui_path = os.path.join(ui_path, "ui")
form_traitement, _ = uic.loadUiType(os.path.join(ui_path, "biodiv.ui"))

# mise en place de la classe BiodivWidget qui va regrouper l'ensemble des fonctions relatives aux traitements à réaliser
class BiodivWidget(QDialog, form_traitement):
    def __init__(self, iface):
        QDialog.__init__(self)
        # création de l'interface de la fenêtre QGIS
        self.setupUi(self)
        # nom donné à la fenêtre
        self.setWindowTitle("Top'Eau - Analyse des données eau : écoute biodiversité")

        # Bouton "OK / Annuler"
        self.terminer.rejected.connect(self.reject)
        # connexion de la barre de progression
        self.progressBar.setValue(0)
        # Bouton "Générer l'import'"
        self.generer.clicked.connect(self.recup_raster)

        # association de filtres à la sélection de couches dans le projet QGIS
        self.inputPoints_2.setFilters( QgsMapLayerProxyModel.PointLayer | QgsMapLayerProxyModel.PluginLayer)
        # association de l'import de fichiers aux fonctions de désactivation des listes déroulantes
        self.inputPoints.fileChanged.connect(self.maj_etat_inputPoints_2)

        # Connecter le changement d'état des boutons radio
        self.radioChoix.toggled.connect(self.on_radio_toggled)
        self.radioVecteur.toggled.connect(self.on_radio_toggled)

    def reject(self):
        QDialog.reject(self)
        return

    def on_radio_toggled(self):
        if self.radioChoix.isChecked() :
            print("Radio cochée")
        else:
            print("Radio décochée")
        if self.radioVecteur.isChecked() :
            print("Radio cochée")
        else:
            print("Radio décochée")

    # fonction permettant de désactiver les listes déroulantes des couches si un chemin est renseigné pour l'import de données
    def maj_etat_inputPoints_2(self, path):
        path = path.strip()
        if path != "":
            self.inputPoints_2.setEnabled(False)
        else:
            self.inputPoints_2.setEnabled(True)

    # 1. fonction permettant la récupération du raster depuis le GPKG à partir de la/des date/s fournie/s par l'utilisateur
    def recup_raster(self):

        # chargement de la date sélectionnée par l'utilisateur dans une variable
        # la date peut être contenue dans un fichier de point ou comprise dans une plage de dates sélectionnée par l'utilisateur
        if self.radioChoix.isChecked() : # si l'utilisateur coche "Ou plage étudiée"...
            # récupération des dates depuis les QDateEdit
            start_qdate = self.dateDebut.date()
            end_qdate = self.dateFin.date()
            # ...conversion des dates récupérées en dates réelles...
            start_date = datetime(start_qdate.year(), start_qdate.month(), start_qdate.day()).date()
            end_date = datetime(end_qdate.year(), end_qdate.month(), end_qdate.day()).date()

            # ...vérification de l'ordre chronologique (erreur si la date de fin est avant la date de début)...
            if start_date > end_date:
                start_date, end_date = end_date, start_date

            date_range = [] # ...construction de la liste complète des dates dans l'intervalle...
            current_date = start_date
            while current_date <= end_date:
                date_range.append(current_date)
                current_date += timedelta(days=1)

            # ...récupération des dates récupérées dans l'intervalle sous la variable values qui est convertie en ISO
            # avant d'être récupérée dans les requêtes SQL effectuées sur la table mesure
            values = date_range

        else : # si l'utilisateur coche "...la date des [...] biodiversité" ...
            selected_points = self.inputPoints.lineEdit().text()
            # vérification de la sélection d'un fichier en fonction du choix de l'utilisateur...
            if not selected_points or selected_points.strip() == "": # ...localement...
                layer = self.inputPoints_2.currentLayer() # récupération de la couche sélectionnée depuis le projet
                if layer is None or not isinstance(layer, QgsVectorLayer):
                    QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier de points ou une couche.")
                    return None
                selected_points = layer
                use_layer = True
            else:
                if not os.path.exists(selected_points): # vérification de l'existence du projet
                    QMessageBox.warning(self, "Erreur", f"Le fichier n'existe pas : {selected_points}")
                    return None
                use_layer = False

            field_name = self.nomChamp.text()# ...récupération du nom du champ contenant la date
            if not field_name or field_name.strip() == "": # & vérification de sa validité...
                QMessageBox.warning(self, "Erreur", "Veuillez renseigner le nom du champ.")
                return None

            try: # ...chargement de la couche selon la source (local ou projet)...
                if use_layer:
                    layer = selected_points
                else:
                    layer = QgsVectorLayer(selected_points, "temp_layer", "ogr")
                if not layer.isValid(): # ...vérification de la validité de la couche...
                    QgsMessageLog.logMessage("Erreur: La couche n'est pas valide", "Top'Eau", Qgis.Critical)
                    QMessageBox.critical(self, "Erreur", "La couche de points n'est pas valide")
                    return None
                # ...vérification de l'existence du champ...
                field_names = [field.name() for field in layer.fields()]
                if field_name not in field_names:
                    error_msg = f"Le champ '{field_name}' n'existe pas.\nChamps disponibles: {', '.join(field_names)}"
                    QgsMessageLog.logMessage(error_msg, "Top'Eau", Qgis.Critical)
                    QMessageBox.critical(self, "Erreur", error_msg)
                    return None
                # ...extraction des valeurs
                values = []
                valid_features = 0

                for feature in layer.getFeatures():
                    if feature.hasGeometry() and not feature.geometry().isEmpty(): # vérification de la validité de la géométrie
                        value = feature[field_name]
                        if value is not None:  # ignorer les valeurs nulles
                            values.append(value)
                            valid_features += 1
                if len(values) == 0: # erreur si le champ n'est pas valide (pas de donnée, pas de format valide de date...)
                    QgsMessageLog.logMessage(f"Aucune valeur valide trouvée dans le champ '{field_name}'", "Top'Eau",
                                             Qgis.Warning)
                    QMessageBox.warning(self, "Attention", f"Aucune valeur valide trouvée dans le champ '{field_name}'")
                    return None
                QgsMessageLog.logMessage(f"Succès", "Top\'Eau", Qgis.Success)
                QMessageBox.information(self, "Succès", f"Extraction terminée:\n- {len(values)} valeur(s) extraite(s)")

            except Exception as e:
                error_msg = f"Erreur lors de l'extraction: {str(e)}"
                QgsMessageLog.logMessage(error_msg, "Top'Eau", Qgis.Critical)
                QMessageBox.critical(self, "Erreur", error_msg)
                return None

        self.progressBar.setValue(25) # mise à jour de la barre de progression

        try :

            selected_GPKG = self.inputGPKG.filePath() # récupération du GPKG saisi par l'utilisateur
            if not selected_GPKG or not os.path.exists(selected_GPKG):
                QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier GPKG valide.")
                return None

            # connexion SQLite directe au GeoPackage
            conn = sqlite3.connect(selected_GPKG)
            cursor = conn.cursor()

            # lecture ligne par ligne des données de la table mesure et requêtage sur les valeurs concernées
            # instanciation de variables en tuple pour leur permettre de récupérer une lsite de plusieurs variables
            all_occurrences = []
            valeurs_corr = []
            raster_layers = []

            # ajout d'une variable pour stocker les informations de correspondance entre les valeurs et les rasters
            # pour faciliter le traitement des données après la récupération des rasters
            raster_date_mapping = []

            # boucle sur chacune des dates récupérées en amont depuis le fichier vecteur ou les calendriers pour savoir...
            # 1. si elles correspondent à des dates stockées dans la table "mesure" du GPKG et récupérer celles qui correspondent
            for value in values:

                date_str = convert_to_iso_date(value) # conversion des dates récupérées pour compatibilité avec le format GPKG

                queries = [
                    f"SELECT *, niveau_eau FROM mesure WHERE DATE(date) = '{date_str}'",
                    f"SELECT *, niveau_eau FROM mesure WHERE SUBSTR(date, 1, 10) = '{date_str}'",
                    f"SELECT *, niveau_eau FROM mesure WHERE date LIKE '{date_str}%'"
                ] # requêtes SQL tentées pour récupérer les valeurs similaires
                found = False

                for i, query in enumerate(queries): # boucle sur l'intégralité des valeurs correspondantes
                    try:
                        cursor.execute(query)
                        occurrences = cursor.fetchall()
                        if occurrences:
                            print(f"  -> Trouvé {len(occurrences)} résultats lors de la requête")
                            all_occurrences.extend(occurrences)

                            # 2. quel niveau d'eau relevé sur le terrain est associé à cette date
                            # initialisation d'une variable récupérant le niveau d'eau lié à la date correspondante
                            # en cm pour le requêtage sur les rasters
                            niveau_eau_cm = None

                            for occurrence in occurrences: # boucle sur les dates qui correspondent
                                niveau_eau = occurrence[-1]  # on récupère le résultat du dernier champ sélectionné en SQL (niveau_eau)
                                if niveau_eau is not None:
                                    valeurs_corr.append(niveau_eau)
                                    try: # tentative de conversion directe (lorsque le type de donnée est numérique)
                                        niveau_eau_float = float(niveau_eau)
                                        niveau_eau_cm = int(niveau_eau_float * 100)
                                        print("Conversion directe réussie - Niveau d'eau en cm :", niveau_eau_cm)
                                    except (ValueError, TypeError):
                                        try: # traitement si la donnée est en format chaîne de caractères
                                            niveau_eau_corrige = float(str(niveau_eau)[:-2].replace(",", "."))
                                            niveau_eau_cm = int(niveau_eau_corrige * 100)
                                            print("Niveau d'eau en cm :", niveau_eau_cm)
                                        except Exception as e:
                                            QMessageBox.warning(self, "Erreur",
                                                                f"Impossible de convertir la valeur : {niveau_eau}")
                                            continue
                                    else:
                                        QMessageBox.warning(self, "Erreur",
                                                            "Il n'y a pas de niveau d'eau pour la/les date/s sélectionnée/s")
                                    found = True

                            # requête pour récupérer les tables raster du GPKG
                            cursor.execute(f"""
                                           SELECT table_name FROM gpkg_contents 
                                           WHERE data_type = 'tiles' OR data_type = '2d-gridded-coverage'
                                       """)
                            results = cursor.fetchall()
                            rasters = [row[0] for row in results]

                            for raster_name in rasters:
                                # intégration de la valeur du niveau d'eau, passée en cm, en string pour requêter les noms de fichier
                                if str(int(niveau_eau_cm)) in raster_name:
                                    uri = f"GPKG:{selected_GPKG}:{raster_name}"
                                    try:
                                        # création de la couche raster
                                        layer_niveau_eau = QgsRasterLayer(uri, raster_name, "gdal")
                                        if layer_niveau_eau.isValid():
                                            raster_layers.append(layer_niveau_eau)
                                            print(f"Raster chargé avec succès: {raster_name}")
                                            raster_date_mapping.append({
                                                'raster': layer_niveau_eau,
                                                'date': value,  # date originale
                                                'date_iso': date_str,
                                                'niveau_eau': niveau_eau_cm,
                                                'raster_name': raster_name
                                            })
                                        else:
                                            print(f"Erreur: Le raster {raster_name} n'est pas valide")
                                    except Exception as e:
                                        QgsMessageLog.logMessage(
                                            f"Erreur lors du chargement du raster {raster_name}: {str(e)}", "Top'Eau",
                                            Qgis.Warning)
                            found = True
                            break
                    except Exception as e:
                        QgsMessageLog.logMessage(f"Erreur avec la requête {i + 1}: {e}", "Top'Eau",
                                               Qgis.Warning)
            conn.close()

            # appel de la fonction recup_lame_eau avec les rasters trouvés
            if raster_layers:
                mode_intervalle = self.radioChoix.isChecked()
                return self.recup_lame_eau(raster_layers, raster_date_mapping, mode_intervalle)
            else:
                QMessageBox.warning(self, "Erreur", "Aucun raster correspondant trouvé.")
                return None
        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la lecture du GPKG: {str(e)}",
                                     "Top'Eau", Qgis.Critical)
            return None


    # fonction permettant de récupérer le vecteur ponctuel fourni par l'utilisateur et de renvoyer à l'une ou l'autre
    # des fonctions qui suivent en fonction du choix renseigné pour la date (champ ou intervalle)
    def recup_lame_eau(self, raster_layers, raster_date_mapping, mode_intervalle):

        selected_points = self.inputPoints.lineEdit().text() # récupération du vecteur renseigné par l'utilisateur
        # vérification de la sélection d'un fichier en fonction du choix de l'utilisateur...
        if not selected_points or selected_points.strip() == "": # ...localement...
            layer_points = self.inputPoints_2.currentLayer() # récupération de la couche sélectionnée depuis le projet
            if layer_points is None or not isinstance(layer_points, QgsVectorLayer):
                QMessageBox.warning(self, "Erreur",
                                    "Veuillez sélectionner un fichier de points ou une couche.")
                return None
            selected_points = layer_points
            use_layer = True
        else:
            if not os.path.exists(selected_points): # vérification de l'existence du projet
                QMessageBox.warning(self, "Erreur", f"Le fichier n'existe pas : {selected_points}")
                return None
            use_layer = False
        self.progressBar.setValue(50) # mise à jour de la barre de progression

        # appel à l'une ou l'autre des fonctions de traitement selon la case cochée par l'utilisateur (date des relevés/intervalle précisée)
        try:
            if mode_intervalle: # appel au mode intervalle si l'utilisateur a coché "...intervalle que je précise"
                return self._process_interval_mode(layer_points, raster_date_mapping) # duplication des entités pour chaque date
            else: # appel au mode champ si l'utilisateur a coché "...la date des relevés [...]"
                # une seule colonne est ajoutée et les valeurs sont récupérées uniquement pour les dates sélectionnées
                return self._process_field_mode(layer_points, raster_date_mapping)

        except Exception as e:
            error_msg = f"Erreur lors du traitement des rasters : {str(e)}"
            QgsMessageLog.logMessage(error_msg, "Top'Eau", Qgis.Critical)
            QMessageBox.critical(self, "Erreur", error_msg)
            return None


    # fonction permettant de dupliquer chaque entité en fonction de chaque date comprise dans l'intervalle
    # et de relever un niveau d'eau unique et une lame d'eau unique pour chaque date
    def _process_interval_mode(self, layer_points, raster_date_mapping):

        nom_couche = self.nomCouche.text() # récupération du nom de la couche décidé par l'utilisateur

        # création d'une couche temporaire avec les champs originaux + nouveaux champs
        temp_layer = QgsVectorLayer(f"Point?crs={layer_points.crs().authid()}", nom_couche, "memory")
        temp_layer.startEditing() # copie des champs contenus dans la couche fournie par l'utilisateur
        for field in layer_points.fields():
            temp_layer.addAttribute(field)

        # ajout des nouveaux champs
        # ajout du champ contenant la date du relevé pris sur le terrain (date contenue dans la table mesure)
        temp_layer.addAttribute(QgsField("date_releve_terrain", QVariant.Date))
        # niveau d'eau relevé sur le terrain (niveau contenu dans la table mesure)
        temp_layer.addAttribute(QgsField("niveau_eau_cm", QVariant.Int))
        # valeur récupérée sur le raster contenu dans le GPKG et correspondant au niveau d'eau relevé
        field_round = QgsField("lame_eau", QVariant.Double)
        field_round.setPrecision(3)
        temp_layer.addAttribute(field_round)
        temp_layer.commitChanges()

        # création d'une variable permettant de récupérer les informations à ajouter aux champs créés
        features_to_add = []
        # pour chaque entité avec un id propre contenue dans le fichier vecteur ponctuel fourni par l'utilisateur...
        for original_feature in layer_points.getFeatures():
            feature_id = original_feature.id()

            for mapping in raster_date_mapping: # ... boucle sur chaque correspondance raster-date...
                # ...duplication de l'entité...
                new_feature = QgsFeature(temp_layer.fields())
                new_feature.setGeometry(original_feature.geometry())
                # ...copie des attributs originaux...
                for i, field in enumerate(layer_points.fields()):
                    new_feature.setAttribute(field.name(), original_feature.attribute(field.name()))
                # ...ajout des nouveaux attributs
                new_feature.setAttribute("date_releve_terrain", str(mapping['date']))
                new_feature.setAttribute("niveau_eau_cm", mapping['niveau_eau'])
                features_to_add.append((new_feature, mapping['raster']))
        temp_layer.startEditing() # application de l'extraction de valeurs du raster

        for i, (feature, raster) in enumerate(features_to_add): # boucle sur les informations à traiter (info vecteurs et rasters)

            # création d'une couche temporaire avec une seule entité
            single_feature_layer = QgsVectorLayer(f"Point?crs={layer_points.crs().authid()}","single_point","memory")
            single_feature_layer.startEditing()
            for field in temp_layer.fields():
                single_feature_layer.addAttribute(field)
            single_feature_layer.commitChanges()

            single_feature_layer.startEditing()
            single_feature_layer.addFeature(feature)
            single_feature_layer.commitChanges()

            # application de l'extraction de valeur (algorithme QGIS : "Prélèvement des valeurs rasters vers ponctuels")
            # pour récupérer l'information de la lame d'eau
            result = processing.run("native:rastersampling", {
                'INPUT': single_feature_layer,
                'RASTERCOPY': raster,
                'COLUMN_PREFIX': 'temp_',
                'OUTPUT': 'memory:'
            })
            # récupération de la valeur et mise à jour de la couche
            result_layer = result['OUTPUT']
            for result_feature in result_layer.getFeatures():
                # récupération de la valeur du raster
                raster_value = None
                for field in result_feature.fields():
                    if field.name().startswith('temp_'):
                        raster_value = result_feature.attribute(field.name())
                        break
                # ajout de l'entité avec la valeur
                feature.setAttribute("lame_eau", raster_value)
                temp_layer.addFeature(feature)

            progress = 50 + (25 * (i + 1) / len(features_to_add))
            self.progressBar.setValue(int(progress)) # mise à jour de la progression

        temp_layer.commitChanges()
        QgsProject.instance().addMapLayer(temp_layer) # ajout de la couche au projet QGIS
        self.progressBar.setValue(100)

        if hasattr(self, 'iface') and self.iface:
            self.iface.mapCanvas().refresh() # rafraîchissement de la vue
        return temp_layer


    # fonction permettant de conserver le nombre d'entités de base en ajoutant à la table attributaire de la couche en
    # entrée une seule colonne contenant la lame d'eau récupérée pour une entité en fonction de la date à laquelle
    # elle est associée dans le fichier vecteur
    def _process_field_mode(self, layer_points, raster_date_mapping):

        field_name = self.nomChamp.text() # récupération du nom du champ date
        nom_couche = self.nomCouche.text() # récupération du nom de la couche

        # création d'une couche temporaire avec les champs originaux + nouveaux champs
        temp_layer = QgsVectorLayer(f"Point?crs={layer_points.crs().authid()}", nom_couche,"memory")
        # copie des champs originaux + ajout des nouveaux champs
        temp_layer.startEditing()
        for field in layer_points.fields():
            temp_layer.addAttribute(field)
        field_round = QgsField("lame_eau", QVariant.Double)
        field_round.setPrecision(3)
        temp_layer.addAttribute(field_round)
        temp_layer.addAttribute(QgsField("niveau_eau_cm", QVariant.Int))
        temp_layer.commitChanges()

        # création d'un dictionnaire pour un accès rapide aux rasters par date
        date_to_raster = {}
        # création d'un dictionnaire pour un accès rapide aux niveaux d'eau relevés par date
        date_to_niveau_eau = {}
        for mapping in raster_date_mapping:
            # Utilisation de la date convertie comme clé
            date_key = convert_to_iso_date(mapping['date'])
            date_to_raster[date_key] = mapping['raster']
            date_to_niveau_eau[date_key] = mapping['niveau_eau']

            # ajout aussi de la date originale comme clé alternative
            date_to_raster[str(mapping['date'])] = mapping['raster']
            date_to_niveau_eau[str(mapping['date'])] = mapping['niveau_eau']

        features_to_add = []
        processed_count = 0

        # traitement de chaque point individuellement (un point créé = un point récupéré sur la couche de base)
        # le traitement traite toutes les entités du fichier vecteur donné par l'utilisateur une par une
        for feature in layer_points.getFeatures():
            try:

                point_date = feature[field_name] # récupération de la date du point
                if point_date is None:
                    print(f"Point ID {feature.id()} : date manquante")
                    continue
                point_date_iso = convert_to_iso_date(point_date) # conversion de la date pour la correspondance
                corresponding_raster = None # recherche du raster correspondant
                corresponding_niveau_eau = None # recherche du niveau d'eau correspondant

                # pour toutes les correspondances, récupération des informations désirées
                if point_date_iso in date_to_raster:
                    corresponding_raster = date_to_raster[point_date_iso]
                    corresponding_niveau_eau = date_to_niveau_eau[point_date_iso]
                elif str(point_date) in date_to_raster:
                    corresponding_raster = date_to_raster[str(point_date)]
                    corresponding_niveau_eau = date_to_niveau_eau[str(point_date)]

                if corresponding_raster is None:
                    print(f"Aucun raster trouvé pour la date {point_date_iso}")
                    # création de l'entité avec valeur nulle
                    new_feature = QgsFeature(temp_layer.fields())
                    new_feature.setGeometry(feature.geometry())
                    for field_orig in layer_points.fields():
                        new_feature.setAttribute(field_orig.name(), feature.attribute(field_orig.name()))
                    new_feature.setAttribute("lame_eau", None)
                    new_feature.setAttribute("niveau_eau_cm", None)
                    features_to_add.append(new_feature)
                    continue

                # création d'une couche temporaire
                single_point_layer = QgsVectorLayer(f"Point?crs={layer_points.crs().authid()}","single_point","memory")
                # ajout des champs (nouveaux + originaux) à la couche
                single_point_layer.startEditing()
                for field_orig in layer_points.fields():
                    single_point_layer.addAttribute(field_orig)
                single_point_layer.commitChanges()
                single_point_layer.startEditing()
                single_point_layer.addFeature(feature)
                single_point_layer.commitChanges()

                # récupération de la lame d'eau pour ce point spécifique
                result = processing.run("native:rastersampling", {
                    'INPUT': single_point_layer,
                    'RASTERCOPY': corresponding_raster,
                    'COLUMN_PREFIX': 'temp_lame_eau_',
                    'OUTPUT': f'memory:'
                })

                # récupération de la couche temporaire résultante dans une variable pour l'implémenter
                result_layer = result['OUTPUT']
                # création de la géométrie de la nouvelle entité
                for result_feature in result_layer.getFeatures():
                    new_feature = QgsFeature(temp_layer.fields())
                    new_feature.setGeometry(result_feature.geometry())
                    # copie des attributs originaux (contenu des champs originaux)
                    for field_orig in layer_points.fields():
                        new_feature.setAttribute(field_orig.name(), result_feature.attribute(field_orig.name()))
                    # récupération de la valeur du raster (contenu récupéré via le croisement des données)
                    lame_eau_value = None
                    for field_result in result_feature.fields():
                        if field_result.name().startswith('temp_lame_eau_'):
                            lame_eau_value = result_feature.attribute(field_result.name())
                            break
                    # association des nouveaux champs avec leur contenu
                    new_feature.setAttribute("lame_eau", lame_eau_value)
                    new_feature.setAttribute("niveau_eau_cm", corresponding_niveau_eau)
                    features_to_add.append(new_feature)
                    # arrêt de la boucle après l'implémentation pour que les traitements recommencent sur une autre entité
                    break

                processed_count += 1 # variable pour mettre à jour dynamiquement la barre de progression
                progress = 50 + (25 * processed_count / layer_points.featureCount())
                self.progressBar.setValue(int(progress)) # mise à jour de la barre de progression

            except Exception as e:
                QgsMessageLog.logMessage(f"Erreur lors du traitement du point ID {feature.id()} : {e}",
                                         "Top'Eau", Qgis.Critical)

                # ajout du point avec valeurs nulles en cas d'erreur
                new_feature = QgsFeature(temp_layer.fields())
                new_feature.setGeometry(feature.geometry())
                for field_orig in layer_points.fields():
                    new_feature.setAttribute(field_orig.name(), feature.attribute(field_orig.name()))
                new_feature.setAttribute("lame_eau", None)
                new_feature.setAttribute("niveau_eau_cm", None)
                features_to_add.append(new_feature)

        # ajout de toutes les entités à la couche temporaire
        temp_layer.startEditing()
        temp_layer.addFeatures(features_to_add)
        temp_layer.commitChanges()
        QgsProject.instance().addMapLayer(temp_layer) # ajout de la couche au projet QGIS
        self.progressBar.setValue(100) # màj de la barre de progression
        if hasattr(self, 'iface') and self.iface:
            self.iface.mapCanvas().refresh() # rafraîchissement de la vue
        return temp_layer
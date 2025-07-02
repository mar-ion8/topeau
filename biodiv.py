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

from datetime import datetime, timedelta

# appel emplacement des fichiers de stockage des sorties temporaires -- temp
temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")

# lien entre traitement.py et traitement.ui
ui_path = os.path.dirname(os.path.abspath(__file__))
ui_path = os.path.join(ui_path, "ui")
form_traitement, _ = uic.loadUiType(os.path.join(ui_path, "biodiv.ui"))


# mise en place de la classe TraitementWidget
# va regrouper l'ensemble des fonctions relatives aux traitements à réaliser
class BiodivWidget(QDialog, form_traitement):
    def __init__(self, iface):
        QDialog.__init__(self)

        # création de l'interface de la fenêtre QGIS
        self.setupUi(self)
        # ajustement de la taille de la fenêtre pour qu'elle soit fixe
        #self.setFixedSize(600, 400)
        # nom donné à la fenêtre
        self.setWindowTitle("Top'Eau - Analyse des données eau : écoute biodiversité")

        # Bouton "OK / Annuler"
        self.terminer.rejected.connect(self.reject)

        # connexion de la barre de progression
        self.progressBar.setValue(0)

        # Bouton "Générer l'import'"
        self.generer.clicked.connect(self.recup_raster)

        # association de filtres à la sélection de couches dans le projet QGIS
        self.inputPoints_2.setFilters(
            QgsMapLayerProxyModel.PointLayer |
            QgsMapLayerProxyModel.PluginLayer
        )

        # association de l'import de fichiers aux fonctions de désactivation des listes déroulantes
        self.inputPoints.fileChanged.connect(self.maj_etat_inputPoints_2)

        # Connecter le changement d'état des boutons radio
        self.radioChoix.toggled.connect(self.on_radio_toggled)
        self.radioVecteur.toggled.connect(self.on_radio_toggled)
        #self.radioChoix.toggled.connect(self.toggle_mode_date)
        #self.radioVecteur.toggled.connect(self.toggle_mode_date)

        # Appeler une première fois pour initialiser correctement
        #self.toggle_mode_date()

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

    # fonction permettant de désactiver les options non utilsiées par l'utilisateur
    '''
    
    A ADAPTER POUR QUE CA NE FONCTIONNE QU'AVEC LES OPTIONS DE DATE
    
    def toggle_mode_date(self):
        is_manual = self.radioChoix.isChecked()

        # activation des widgets de saisie de date uniquement si "Ou plage étudiée" est coché
        self.dateDebut.setEnabled(is_manual)
        self.dateFin.setEnabled(is_manual)

        # activation des widgets d'input de vecteur (local ou liste déroulante) uniquement si "FIchier vecteur [...] biodiversité" est coché
        self.inputPoints.setEnabled(not is_manual)
        self.inputPoints_2.setEnabled(not is_manual)
        self.nomChamp.setEnabled(not is_manual)
    '''

    # fonction permettant de désactiver les listes déroulantes des couches si un chemin est renseigné pour l'import de données
    def maj_etat_inputPoints_2(self, path):
        path = path.strip()
        if path != "":
            self.inputPoints_2.setEnabled(False)
        else:
            self.inputPoints_2.setEnabled(True)


    # 1. fonction permettant la récupération du raster depuis le GPKG à partir de la/des date/s fournie/s par l'utilisateur
    def recup_raster(self):

        # 1.1. chargement de la date sélectionnée par l'utilisateur dans une variable
        # la date peut être : contenue dans un fichier de point ou comprise dans une plage de dates sélectionnée par l'utilisateur

        # si l'utilisateur coche "Ou plage étudiée"...
        if self.radioChoix.isChecked() :

            # récupération des dates depuis les QDateEdit
            start_qdate = self.dateDebut.date()
            end_qdate = self.dateFin.date()

            # ...conversion des dates récupérées en dates réelles...
            start_date = datetime(start_qdate.year(), start_qdate.month(), start_qdate.day()).date()
            end_date = datetime(end_qdate.year(), end_qdate.month(), end_qdate.day()).date()

            # ...vérification de l'ordre chronologique (erreur si la date de fin est avant la date de début)...
            if start_date > end_date:
                start_date, end_date = end_date, start_date

            # ...construction de la liste complète des dates dans l'intervalle...
            date_range = []
            current_date = start_date
            while current_date <= end_date:
                date_range.append(current_date)
                current_date += timedelta(days=1)

            # ...récupération des dates récupérées dans l'intervalle sous la variable values qui est convertie en ISO
            # avant d'être récupérée dans les requêtes SQL effectuées sur la table mesure
            values = date_range

        # si l'utilisateur coche "...la date des [...] biodiversité" ...
        else :

            selected_points = self.inputPoints.lineEdit().text()
            # vérification de la sélection d'un fichier en fonction du choix de l'utilisateur...
            # ...localement...
            if not selected_points or selected_points.strip() == "":
                # récupération de la couche sélectionnée depuis le projet
                layer = self.inputPoints_2.currentLayer()
                if layer is None or not isinstance(layer, QgsVectorLayer):
                    QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier de points ou une couche.")
                    return None
                selected_points = layer
                use_layer = True
            else:
                # vérification de l'existence du projet
                if not os.path.exists(selected_points):
                    QMessageBox.warning(self, "Erreur", f"Le fichier n'existe pas : {selected_points}")
                    return None
                use_layer = False

            # ...récupération du nom du champ contenant la date & vérification de sa validité...
            field_name = self.nomChamp.text()
            if not field_name or field_name.strip() == "":
                QMessageBox.warning(self, "Erreur", "Veuillez renseigner le nom du champ.")
                return None

            try:
                # ...chargement de la couche selon la source (local ou projet)...
                if use_layer:
                    layer = selected_points
                else:
                    layer = QgsVectorLayer(selected_points, "temp_layer", "ogr")

                # ...vérification de la validité de la couche...
                if not layer.isValid():
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
                    # vérification de la validité de la géométrie
                    if feature.hasGeometry() and not feature.geometry().isEmpty():
                        value = feature[field_name]
                        if value is not None:  # ignorer les valeurs nulles
                            values.append(value)
                            valid_features += 1
                # message d'erreur si le champ n'est pas valide (pas de donnée, pas de format valide de date...)
                if len(values) == 0:
                    QgsMessageLog.logMessage(f"Aucune valeur valide trouvée dans le champ '{field_name}'", "Top'Eau",
                                             Qgis.Warning)
                    QMessageBox.warning(self, "Attention", f"Aucune valeur valide trouvée dans le champ '{field_name}'")
                    return None

                QgsMessageLog.logMessage(f"Succès", "Top\'Eau", Qgis.Success)
                QMessageBox.information(self, "Succès", f"Extraction terminée:\n- {len(values)} valeur(s) extraite(s)")

                # message indiquant les valeurs relevées pour vérification de l'extraction
                # QMessageBox.information(self, "Succès", f"Extraction terminée:\n- {values}")

            except Exception as e:
                error_msg = f"Erreur lors de l'extraction: {str(e)}"
                QgsMessageLog.logMessage(error_msg, "Top'Eau", Qgis.Critical)
                QMessageBox.critical(self, "Erreur", error_msg)
                return None

        # mise à jour de la barre de progression
        self.progressBar.setValue(25)

        try :

            # 1.2. récupération du GPKG saisi par l'utilisateur
            selected_GPKG = self.inputGPKG.filePath()

            if not selected_GPKG or not os.path.exists(selected_GPKG):
                QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier GPKG valide.")
                return None

            # 1.3. connexion SQLite directe au GeoPackage
            conn = sqlite3.connect(selected_GPKG)
            cursor = conn.cursor()

            """" 
            A SUPPRIMER UNE FOIS LE PLUGIN ACHEVE 

            cursor.execute('SELECT date FROM mesure LIMIT 5')
            sample_dates = cursor.fetchall()
            print(f"Exemples de dates dans le GPKG: {sample_dates}")
            
            """

            # 1.4. lecture ligne par ligne des données de la table mesure et requêtage sur les valeurs concernées

            # instanciation de variables en tuple pour leur permettre de récupérer une lsite de plusieurs variables
            all_occurrences = []
            valeurs_corr = []
            raster_layers = []

            # ajout d'une variable pour stocker les informations de correspondance entre les valeurs et les rasters
            # pour faciliter le traitement des données après la récupération des rasters
            raster_date_mapping = []

            # boucle sur chacune des dates récupérées en amont depuis le fichier vecteur ou les calendriers pour savoir...
            # 1. si elles correspondent à des dates stockées dans la table "mesure" du GPKG et récupérées celles qui correspondent
            for value in values:

                # conversion des dates récupérées en amont pour être sûr que le format soit compatible avec
                # le format de date du GPKG (yyyy-mm-dd hh:mm:ss)
                date_str = self.convert_to_iso_date(value)

                # print(f"Date convertie: {date_str}")

                # requêtes SQL tentées pour récupérer les valeurs similaires
                queries = [
                    f"SELECT *, niveau_eau FROM mesure WHERE DATE(date) = '{date_str}'",
                    f"SELECT *, niveau_eau FROM mesure WHERE SUBSTR(date, 1, 10) = '{date_str}'",
                    f"SELECT *, niveau_eau FROM mesure WHERE date LIKE '{date_str}%'"
                ]

                found = False

                # boucle sur l'intégralité des valeurs correspondantes
                for i, query in enumerate(queries):
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
                            # boucle sur les dates qui correspondent
                            for occurrence in occurrences:
                                niveau_eau = occurrence[-1]  # on récupère ici uniquement le résultat du dernier champ sélectionné en SQL (niveau_eau)
                                if niveau_eau is not None:
                                    valeurs_corr.append(niveau_eau)

                                    print("Valeur brute récupérée :", niveau_eau)
                                    print("Type de la valeur :", type(niveau_eau))

                                    try:
                                        # tentative de conversion directe (lorsque le type de donnée est numérique)
                                        niveau_eau_float = float(niveau_eau)
                                        niveau_eau_cm = int(niveau_eau_float * 100)
                                        print("Conversion directe réussie - Niveau d'eau en cm :", niveau_eau_cm)

                                    except (ValueError, TypeError):
                                        # traitement si la donnée est en format chaîne de caractères
                                        try:
                                            niveau_eau_corrige = float(str(niveau_eau)[:-2].replace(",", "."))
                                            print("Niveau d'eau récupéré depuis le GPKG :", niveau_eau_corrige)
                                            niveau_eau_cm = int(niveau_eau_corrige * 100)
                                            print("Niveau d'eau en cm :", niveau_eau_cm)
                                        except Exception as e:
                                            print(f"Erreur lors du traitement alternatif : {e}")
                                            QMessageBox.warning(self, "Erreur",
                                                                f"Impossible de convertir la valeur : {niveau_eau}")
                                            continue
                                    else:
                                        QMessageBox.warning(self, "Erreur",
                                                            "Il n'y a pas de niveau d'eau pour la/les date/s sélectionnée/s")

                                    found = True

                            # requête pour récupérer les tables raster du GPKG
                            cursor.execute(f"""
                                           SELECT table_name 
                                           FROM gpkg_contents 
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

        """
        A SUPPRIMER UNE FOIS LE PLUGIN ACHEVE

        print(f"Nombre de rasters reçus: {len(raster_layers)}")
        print(f"Mode intervalle: {mode_intervalle}")

        """

        # récupération du vecteur renseigné par l'utilisateur
        selected_points = self.inputPoints.lineEdit().text()
        # vérification de la sélection d'un fichier en fonction du choix de l'utilisateur...
        # ...localement...
        if not selected_points or selected_points.strip() == "":
            # récupération de la couche sélectionnée depuis le projet
            layer_points = self.inputPoints_2.currentLayer()
            if layer_points is None or not isinstance(layer_points, QgsVectorLayer):
                QMessageBox.warning(self, "Erreur",
                                    "Veuillez sélectionner un fichier de points ou une couche.")
                return None
            selected_points = layer_points
            use_layer = True
        else:
            # vérification de l'existence du projet
            if not os.path.exists(selected_points):
                QMessageBox.warning(self, "Erreur", f"Le fichier n'existe pas : {selected_points}")
                return None
            use_layer = False

        # mise à jour de la barre de progression
        self.progressBar.setValue(50)

        # appel à l'une ou l'autre des fonctions de traitement en fonction de la case cochée par l'utilisateur
        # (date des relevés ou intervalle précisée)
        try:
            if mode_intervalle:
                # appel au mode intervalle si l'utilisateur a coché "...intervalle que je précise"
                # duplication des entités pour chaque date
                return self._process_interval_mode(layer_points, raster_date_mapping)
            else:
                # appel au mode champ si l'utilisateur a coché "...la date des relevés [...]"
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

        # création d'une couche temporaire avec les champs originaux + nouveaux champs
        temp_layer = QgsVectorLayer(
            f"Point?crs={layer_points.crs().authid()}",
            "temp_points",
            "memory"
        )

        # copie des champs contenus dans la couche fournie par l'utilisateur
        temp_layer.startEditing()
        for field in layer_points.fields():
            temp_layer.addAttribute(field)

        # ajout des nouveaux champs
        # NB : les noms des champs sont trop longs pour un fichier ShapeFile
        temp_layer.addAttribute(QgsField("date_releve_terrain", QVariant.Date))
        temp_layer.addAttribute(QgsField("niveau_eau_cm", QVariant.Int))
        temp_layer.addAttribute(QgsField("lame_eau", QVariant.Double))
        temp_layer.commitChanges()

        # création d'une variable permettant de récupérer les informations à ajouter aux champs créés
        features_to_add = []

        # pour chaque entité avec un id propre contenue dans le fichier vecteur poncutel fourni par l'utilsiateur...
        for original_feature in layer_points.getFeatures():
            feature_id = original_feature.id()

            # ... boucle sur chaque correspondance raster-date...
            # = il y aura autant d'entités uniques dupliquées qu'il y aura de dates correspondantes entre l'intervalle
            # renseignée par l'utilisateur et celles comprises dans la table mesure du GPGK
            for mapping in raster_date_mapping:
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

        # application de l'extraction de valeurs du raster (donc la récupération de la lame d'eau) pour chaque groupe
        current_layer = temp_layer
        current_layer.startEditing()

        # boucle sur les informations à ajouter pour s'assurer qu'elles soient intégrées sous la forme d'un champ chacune
        # et non sous la forme d'un champ par lame d'eau récupérée
        for i, (feature, raster) in enumerate(features_to_add):

            " A MODIFIER EN FONCTION DES PREFERENCES UTILISATEURS "

            # création d'une couche temporaire avec une seule entité à laquelle on ajoute les informations récupérées précédemment
            single_feature_layer = QgsVectorLayer(
                f"Point?crs={layer_points.crs().authid()}",
                "single_point",
                "memory"
            )
            single_feature_layer.startEditing()
            for field in temp_layer.fields():
                single_feature_layer.addAttribute(field)
            single_feature_layer.commitChanges()

            single_feature_layer.startEditing()
            single_feature_layer.addFeature(feature)
            single_feature_layer.commitChanges()

            # application de l'extraction de valeur pour récupérer l'information de la lame d'eau
            result = processing.run("native:rastersampling", {
                'INPUT': single_feature_layer,
                'RASTERCOPY': raster,
                'COLUMN_PREFIX': 'temp_',
                'OUTPUT': 'memory:'
            })

            # récupération de la valeur et mise à jour de la couche pour chaque lame d'eau récupérée
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
                current_layer.addFeature(feature)

            # mise à jour de la progression
            progress = 50 + (25 * (i + 1) / len(features_to_add))
            self.progressBar.setValue(int(progress))

        current_layer.commitChanges()

        # appel à la fonction permettant de créer et sauvegarder la couche ponctuelle créée

        " PARAMETRAGE DANS L'APPEL ET LE STOCKAGE DE LA COUCHE A VOIR AVEC UTILISATEURS "

        return self._save_and_load_final_layer(current_layer, "points_lame_eau_intervalle")


    # fonction permettant de conserver le nombre d'entités de base en ajoutant à la table attributaire de la couche en
    # entrée une seule colonne contenant la lame d'eau récupérée pour une entité en fonction de la date à laquelle
    # elle est associée dans le fichier vecteur
    def _process_field_mode(self, layer_points, raster_date_mapping):

        # récupération du nom du champ date
        field_name = self.nomChamp.text()

        # création d'une couche temporaire avec les champs originaux + nouveau champ
        temp_layer = QgsVectorLayer(
            f"Point?crs={layer_points.crs().authid()}",
            "temp_points",
            "memory"
        )

        # copie des champs originaux + ajout du champ lame_eau
        temp_layer.startEditing()
        for field in layer_points.fields():
            temp_layer.addAttribute(field)
        temp_layer.addAttribute(QgsField("lame_eau", QVariant.Double))
        temp_layer.commitChanges()

        # création d'un dictionnaire pour un accès rapide aux rasters par date
        date_to_raster = {}
        for mapping in raster_date_mapping:
            # Utilisation de la date convertie comme clé
            date_key = self.convert_to_iso_date(mapping['date'])
            date_to_raster[date_key] = mapping['raster']
            # ajout aussi de la date originale comme clé alternative
            date_to_raster[str(mapping['date'])] = mapping['raster']

        # print(f"Dictionnaire date-raster créé avec {len(date_to_raster)} entrées")

        features_to_add = []
        processed_count = 0

        # Traitement de chaque point individuellement
        for feature in layer_points.getFeatures():
            try:
                # Récupération de la date du point
                point_date = feature[field_name]
                if point_date is None:
                    print(f"Point ID {feature.id()} : date manquante")
                    continue

                # Conversion de la date pour la correspondance
                point_date_iso = self.convert_to_iso_date(point_date)
                print(f"Point ID {feature.id()} : date = {point_date} -> {point_date_iso}")

                # Recherche du raster correspondant
                corresponding_raster = None
                if point_date_iso in date_to_raster:
                    corresponding_raster = date_to_raster[point_date_iso]
                elif str(point_date) in date_to_raster:
                    corresponding_raster = date_to_raster[str(point_date)]

                if corresponding_raster is None:
                    print(f"Aucun raster trouvé pour la date {point_date_iso}")
                    # création de l'entité avec valeur nulle
                    new_feature = QgsFeature(temp_layer.fields())
                    new_feature.setGeometry(feature.geometry())
                    for field_orig in layer_points.fields():
                        new_feature.setAttribute(field_orig.name(), feature.attribute(field_orig.name()))
                    new_feature.setAttribute("lame_eau", None)
                    features_to_add.append(new_feature)
                    continue

                # création d'une couche temporaire avec un seul point
                single_point_layer = QgsVectorLayer(
                    f"Point?crs={layer_points.crs().authid()}",
                    "single_point",
                    "memory"
                )
                single_point_layer.startEditing()
                for field_orig in layer_points.fields():
                    single_point_layer.addAttribute(field_orig)
                single_point_layer.commitChanges()

                single_point_layer.startEditing()
                single_point_layer.addFeature(feature)
                single_point_layer.commitChanges()

                # récupération de la lame d'eau pour ce point spécifique à l'aide de l'algorithme natif "Prélèvements de valeurs rasters avec points"
                result = processing.run("native:rastersampling", {
                    'INPUT': single_point_layer,
                    'RASTERCOPY': corresponding_raster,
                    'COLUMN_PREFIX': 'temp_lame_eau_',
                    'OUTPUT': 'memory:'
                })

                result_layer = result['OUTPUT']

                # récupération de la valeur et création de la nouvelle entité
                for result_feature in result_layer.getFeatures():
                    new_feature = QgsFeature(temp_layer.fields())
                    new_feature.setGeometry(result_feature.geometry())

                    # copie des attributs originaux
                    for field_orig in layer_points.fields():
                        new_feature.setAttribute(field_orig.name(), result_feature.attribute(field_orig.name()))

                    # récupération de la valeur du raster
                    lame_eau_value = None
                    for field_result in result_feature.fields():
                        if field_result.name().startswith('temp_lame_eau_'):
                            lame_eau_value = result_feature.attribute(field_result.name())
                            break

                    new_feature.setAttribute("lame_eau", lame_eau_value)
                    features_to_add.append(new_feature)

                    # print(f"Point ID {feature.id()} : lame_eau = {lame_eau_value}")

                    break

                processed_count += 1

                # mise à jour de la progression
                progress = 50 + (25 * processed_count / layer_points.featureCount())
                self.progressBar.setValue(int(progress))

            except Exception as e:
                print(f"Erreur lors du traitement du point ID {feature.id()} : {e}")
                # ajout du point avec valeur nulle en cas d'erreur
                new_feature = QgsFeature(temp_layer.fields())
                new_feature.setGeometry(feature.geometry())
                for field_orig in layer_points.fields():
                    new_feature.setAttribute(field_orig.name(), feature.attribute(field_orig.name()))
                new_feature.setAttribute("lame_eau", None)
                features_to_add.append(new_feature)

        # ajout de toutes les entités à la couche temporaire
        temp_layer.startEditing()
        temp_layer.addFeatures(features_to_add)
        temp_layer.commitChanges()

        # print(f"Traitement terminé : {len(features_to_add)} points traités")

        return self._save_and_load_final_layer(temp_layer, "points_lame_eau_champ")


    # fonction permettant de gérer la couche vecteur créée par l'une ou l'autre des méthodes précédentes
    # pour la sauvegarder et la charger dans le projet QGIS en cours
    def _save_and_load_final_layer(self, layer, layer_name):

        " A MODIFIER POUR : 1. CREER UN DUPLICAT AMELIORE DE LA COUCHE DE BASE, 2. GERER L'EXTENSION? "

        # création d'un chemin pour un enregistrement temporaire
        final_path = os.path.join(temp_path, f"{layer_name}.gpkg")

        # suppression des fichiers existants
        if os.path.exists(final_path):
            base_name = final_path[:-4]
            for ext in ['.gpkg']:
                file_path = base_name + ext
                if os.path.exists(file_path):
                    os.remove(file_path)

        # sauvegarde
        processing.run("native:savefeatures", {
            'INPUT': layer,
            'OUTPUT': final_path
        })

        self.progressBar.setValue(85)

        # chargement de la couche finale
        layer_finale = QgsVectorLayer(final_path, layer_name, "ogr")

        if not layer_finale.isValid():
            QMessageBox.critical(self, "Erreur", "La couche finale n'est pas valide.")
            return None

        # ajout au projet
        QgsProject.instance().addMapLayer(layer_finale)
        self.progressBar.setValue(100)

        # message de succès
        feature_count = layer_finale.featureCount()
        field_count = len(layer_finale.fields())
        QMessageBox.information(self, "Succès",
                                f"Couche '{layer_name}' ajoutée avec succès !\n"
                                f"- {feature_count} entités\n"
                                f"- {field_count} champs\n"
                                f"- Fichier sauvegardé : {final_path}")

        QgsMessageLog.logMessage(
            f"Couche '{layer_name}' créée avec succès : {feature_count} entités, {field_count} champs",
            "Top'Eau", Qgis.Success)


        return layer_finale


    # fonction permettant de convertir n'importe quel format de date vers le format de date "yyyy-mm-dd %" du GPKG
    def convert_to_iso_date(self, value):

        # import des librairies concernées
        from PyQt5.QtCore import QDate, QDateTime
        from datetime import datetime, date
        import re

        # 2.1. gestion des objets QDate et QDateTime de PyQt5
        if isinstance(value, QDate):
            return value.toString('yyyy-MM-dd')

        elif isinstance(value, QDateTime):
            return value.date().toString('yyyy-MM-dd')

        # 2.2. gestion des objets datetime
        if isinstance(value, datetime):
            return value.strftime('%Y-%m-%d')

        elif isinstance(value, date):
            return value.strftime('%Y-%m-%d')

        elif isinstance(value, str):
            # gestion des différents formats
            try:
                # gestion du format avec fuseau horaire : DD/MM/YYYY HH:MM:SS.mmm GMT+XX:XX
                if 'GMT' in value or 'UTC' in value:
                    # extraction de la partie date avant l'heure
                    # pattern pour capturer DD/MM/YYYY ou DD-MM-YYYY au début
                    date_match = re.match(r'^(\d{1,2}[/-]\d{1,2}[/-]\d{4})', value)
                    if date_match:
                        date_part = date_match.group(1)
                        # Convertir récursivement la partie date
                        return self.convert_to_iso_date(date_part)

                    # si pas de match avec le pattern ci-dessus, essayer d'extraire YYYY-MM-DD
                    iso_match = re.search(r'(\d{4}-\d{1,2}-\d{1,2})', value)
                    if iso_match:
                        return iso_match.group(1)

                # essayage format DD/MM/YYYY
                if '/' in value and not 'GMT' in value and not 'UTC' in value:
                    # Vérifier si c'est juste DD/MM/YYYY ou DD/MM/YYYY avec heure
                    date_part = value.split(' ')[0] if ' ' in value else value
                    if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', date_part):
                        dt = datetime.strptime(date_part, '%d/%m/%Y')
                        return dt.strftime('%Y-%m-%d')

                # essayage format DD-MM-YYYY
                elif '-' in value and len(value.split('-')) == 3:
                    # Extraire la partie date si il y a une heure
                    date_part = value.split(' ')[0] if ' ' in value else value
                    if re.match(r'^\d{1,2}-\d{1,2}-\d{4}$', date_part):
                        dt = datetime.strptime(date_part, '%d-%m-%Y')
                        return dt.strftime('%Y-%m-%d')

                # essayage format YYYY-MM-DD
                elif '-' in value and value.count('-') == 2:
                    # Pattern pour YYYY-MM-DD au début de la string
                    iso_match = re.match(r'^(\d{4}-\d{1,2}-\d{1,2})', value)
                    if iso_match:
                        return iso_match.group(1)

                    # si déjà au bon format, extraire seulement la partie date
                    if ' ' in value:
                        return value.split(' ')[0]
                    else:
                        return value

                # gestion des formats avec heures mais sans fuseau
                elif ' ' in value and not 'GMT' in value and not 'UTC' in value:
                    date_part = value.split(' ')[0]
                    return self.convert_to_iso_date(date_part)

                # gestion des formats ISO avec T (ex: 2024-02-05T11:49:08)
                elif 'T' in value:
                    date_part = value.split('T')[0]
                    return date_part

                else:
                    # essayer de parser comme datetime pour les autres formats
                    # nettoyer d'abord la string des fuseaux horaires
                    clean_value = re.sub(r'\s*(GMT|UTC)[+\-]\d{2}:\d{2}$', '', value)
                    clean_value = re.sub(r'\.\d{3}$', '', clean_value)  # Enlever les millisecondes

                    try:
                        dt = datetime.fromisoformat(clean_value.replace('T', ' '))
                        return dt.strftime('%Y-%m-%d')
                    except:
                        # dernier recours : essayer de trouver une date dans la string
                        date_patterns = [
                            r'(\d{4}-\d{1,2}-\d{1,2})',  # YYYY-MM-DD
                            r'(\d{1,2}/\d{1,2}/\d{4})',  # DD/MM/YYYY
                            r'(\d{1,2}-\d{1,2}-\d{4})'  # DD-MM-YYYY
                        ]

                        for pattern in date_patterns:
                            match = re.search(pattern, value)
                            if match:
                                found_date = match.group(1)
                                return self.convert_to_iso_date(found_date)

            except Exception as e:
                print(f"Erreur conversion date '{value}': {e}")
                return str(value)

        else:
            return str(value)
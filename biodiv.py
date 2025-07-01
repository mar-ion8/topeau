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

            cursor.execute('SELECT date FROM mesure LIMIT 5')
            sample_dates = cursor.fetchall()
            print(f"Exemples de dates dans le GPKG: {sample_dates}")

            # 1.4. lecture ligne par ligne des données de la table mesure et requêtage sur les valeurs concernées

            # instanciation de variables en tuple pour leur permettre de récupérer une lsite de plusieurs variables
            all_occurrences = []
            valeurs_corr = []

            # boucle sur chacune des dates récupérées en amont pour savoir...
            # 1. si elles correspondent à des dates stockées dans la table "mesure" du GPKG
            for value in values:
                date_str = self.convert_to_iso_date(value)
                #print(f"Date convertie: {date_str}")

                # requêtes SQL tentées pour récupérer les valeurs similaires
                queries = [
                    f"SELECT *, niveau_eau FROM mesure WHERE DATE(date) = '{date_str}'",
                    f"SELECT *, niveau_eau FROM mesure WHERE SUBSTR(date, 1, 10) = '{date_str}'",
                    f"SELECT *, niveau_eau FROM mesure WHERE date LIKE '{date_str}%'"
                ]

                found = False
                for i, query in enumerate(queries):
                    try:
                        cursor.execute(query)
                        occurrences = cursor.fetchall()
                        if occurrences:
                            print(f"  -> Trouvé {len(occurrences)} résultats lors de la requête")
                            all_occurrences.extend(occurrences)

                            # 2. quel niveau d'eau relevé sur le terrain est associé à cette date
                            niveau_eau_cm = None
                            for occurrence in occurrences: # boucle sur les dates qui correspondent
                                niveau_eau = occurrence[-1]  # on récupère ici uniquement le résultat du dernier champ sélectionné en SQL (niveau_eau)
                                if niveau_eau is not None:
                                    valeurs_corr.append(niveau_eau)
                                    print(niveau_eau)
                                    niveau_eau_cm = int(niveau_eau * 100) # passage en cm pour effectuer le requêtage sur les noms de rasters
                                    print(niveau_eau_cm)
                                else :
                                    QMessageBox.warning(self, "Erreur", "Il n'y a pas de niveau d'eau pour la/les date/s sélectionnée/s")

                            found = True

                            # requête pour récupérer les tables raster du GPKG
                            cursor.execute(f"""
                                           SELECT table_name 
                                           FROM gpkg_contents 
                                           WHERE data_type = 'tiles' OR data_type = '2d-gridded-coverage'
                                       """)

                            results = cursor.fetchall()
                            rasters = [row[0] for row in results]

                            raster_layers = []

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
                                        else:
                                            print(f"Erreur: Le raster {raster_name} n'est pas valide")

                                    except Exception as e:
                                        QgsMessageLog.logMessage(
                                            f"Erreur lors du chargement du raster {raster_name}: {str(e)}", "Top'Eau",
                                            Qgis.Warning)

                            found = True
                            break

                    except Exception as e:
                        QMessageBox.warning(self, "Erreur",
                                                f"Erreur avec la requête {i + 1}: {e}")



            conn.close()

            # appel de la fonction recup_lame_eau avec les rasters trouvés
            if raster_layers:
                return self.recup_lame_eau(raster_layers)
            else:
                QMessageBox.warning(self, "Erreur", "Aucun raster correspondant trouvé.")
                return None

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la lecture du GPKG: {str(e)}", "Top'Eau", Qgis.Critical)
            return None


    # fonction permettant de récupérer les valeurs comprises dans les rasters générés pour agrémenter le fichier ponctuel
    def recup_lame_eau(self, raster_layers):

        print(f"Nombre de rasters reçus: {len(raster_layers)}")

        # récupération du vecteur renseigné par l'utilisateur

        selected_points = self.inputPoints.lineEdit().text()
        # vérification de la sélection d'un fichier en fonction du choix de l'utilisateur...
        # ...localement...
        if not selected_points or selected_points.strip() == "":
            # récupération de la couche sélectionnée depuis le projet
            layer_points = self.inputPoints_2.currentLayer()
            if layer_points is None or not isinstance(layer_points, QgsVectorLayer):
                QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier de points ou une couche.")
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

        # définition d'un chemin pour la couche de points
        path_points = os.path.join(temp_path, "points_lame_eau.shp")

        try:

            # traitement de chaque raster
            current_layer = layer_points

            for i, raster_layer in enumerate(raster_layers):

                # ajout de l'algorithme natif de QGIS "Prélèvements des valeurs rasters vers points" pour récupérer les lames d'eau
                # comprises dans les rasters du GPKG
                result = processing.run("native:rastersampling", {
                    'INPUT': current_layer,
                    'RASTERCOPY': raster_layer,
                    'COLUMN_PREFIX': f'lame_eau_{i + 1}_',
                    'OUTPUT': 'memory:'
            })

                # création d'un résultat en mémoire
                current_layer = result['OUTPUT']

            # sauvegarde du résultat final
            final_path = os.path.join(temp_path, "points_lame_eau.shp")

            # s'assurer que le fichier n'existe pas
            if os.path.exists(final_path):
                base_name = final_path[:-4]
                for ext in ['.shp', '.shx', '.dbf', '.prj', '.cpg']:
                    file_path = base_name + ext
                    if os.path.exists(file_path):
                        os.remove(file_path)

            # sauvegarde de la couche finale
            save_result = processing.run("native:savefeatures", {
                'INPUT': current_layer,
                'OUTPUT': final_path
            })

            # mise à jour de la barre de progression
            self.progressBar.setValue(75)

            # chargement de la couche finale
            layer_name = "points_lame_eau"
            layer_finale = QgsVectorLayer(path_points, layer_name, "ogr")

            if not layer_finale.isValid():
                QMessageBox.critical(self, "Erreur", "La couche de points finale n'est pas valide.")
                return None

            # ajout de la couche au projet
            QgsProject.instance().addMapLayer(layer_finale)

            # mise à jour de la barre de progression
            self.progressBar.setValue(100)

            # message de succès & informant l'utilisateur des données créées
            feature_count = layer_finale.featureCount()
            field_count = len(layer_finale.fields())
            QMessageBox.information(self, "Succès",
                                    f"Couche '{layer_name}' ajoutée avec succès !\n"
                                    f"- {feature_count} entités\n"
                                    f"- {field_count} champs\n"
                                    f"- Fichier sauvegardé : {path_points}")

            # log QGIS
            QgsMessageLog.logMessage(
                f"Couche '{layer_name}' créée avec succès : {feature_count} entités, {field_count} champs",
                "Top'Eau", Qgis.Success)

            return layer_finale

        except Exception as e:
            error_msg = f"Erreur lors du traitement des rasters : {str(e)}"
            QgsMessageLog.logMessage(error_msg, "Top'Eau", Qgis.Critical)
            QMessageBox.critical(self, "Erreur", error_msg)
            return None

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
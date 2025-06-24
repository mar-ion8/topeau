# -*- coding: utf-8 -*-

# Import module PyQt et API PyQGIS
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5 import uic
from PyQt5.QtGui import *
from qgis.core import *
from qgis.core import Qgis, QgsMessageLog
from qgis import processing
import os

#import librairie nécessaire au requêtage SQL
import sqlite3

# import librairie lecture CSV
import pandas as pd

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

    def reject(self):
        QDialog.reject(self)
        return

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

        # 1.2. récupération du nom du champ contenant la date & vérification de sa validité
        field_name = self.nomChamp.text()
        if not field_name or field_name.strip() == "":
            QMessageBox.warning(self, "Erreur", "Veuillez renseigner le nom du champ.")
            return None

        try:
            # 1.3. chargement de la couche selon la source (local ou projet)
            if use_layer:
                layer = selected_points
            else:
                layer = QgsVectorLayer(selected_points, "temp_layer", "ogr")

            # vérification de la validité de la couche
            if not layer.isValid():
                QgsMessageLog.logMessage("Erreur: La couche n'est pas valide", "Top'Eau", Qgis.Critical)
                QMessageBox.critical(self, "Erreur", "La couche de points n'est pas valide")
                return None

            # vérification de l'existence du champ
            field_names = [field.name() for field in layer.fields()]
            if field_name not in field_names:
                error_msg = f"Le champ '{field_name}' n'existe pas.\nChamps disponibles: {', '.join(field_names)}"
                QgsMessageLog.logMessage(error_msg, "Top'Eau", Qgis.Critical)
                QMessageBox.critical(self, "Erreur", error_msg)
                return None

            # 1.4. extraction des valeurs
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

            #return values

        except Exception as e:
            error_msg = f"Erreur lors de l'extraction: {str(e)}"
            QgsMessageLog.logMessage(error_msg, "Top'Eau", Qgis.Critical)
            QMessageBox.critical(self, "Erreur", error_msg)
            return None

        # mise à jour de la barre de progression
        #self.progressBar.setValue(25)

        try :

            # 1.5. récupération du GPKG saisi par l'utilisateur
            selected_GPKG = self.inputGPKG.filePath()

            if not selected_GPKG or not os.path.exists(selected_GPKG):
                QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier GPKG valide.")
                return None

            # 1.6. connexion SQLite directe au GeoPackage
            conn = sqlite3.connect(selected_GPKG)
            cursor = conn.cursor()

            cursor.execute('SELECT date FROM mesure LIMIT 5')
            sample_dates = cursor.fetchall()
            print(f"Exemples de dates dans le GPKG: {sample_dates}")

            # 1.7. lecture ligne par ligne des données de la table mesure et requêtage sur les valeurs concernées
            all_occurrences = []
            for value in values:
                date_str = self.convert_to_iso_date(value)
                print(f"Date convertie: {date_str}")

                # requêtes SQL tentées pour récupérer les valeurs similaires
                queries = [
                    f"SELECT * FROM mesure WHERE DATE(date) = '{date_str}'",
                    f"SELECT * FROM mesure WHERE SUBSTR(date, 1, 10) = '{date_str}'",
                    f"SELECT * FROM mesure WHERE date LIKE '{date_str}%'"
                ]

                found = False
                for i, query in enumerate(queries):
                    try:
                        cursor.execute(query)
                        occurrences = cursor.fetchall()
                        if occurrences:
                            print(f"  -> Trouvé {len(occurrences)} résultats avec la requête {i + 1}")
                            all_occurrences.extend(occurrences)
                            found = True
                            break
                    except Exception as e:
                        print(f"  -> Erreur avec la requête {i + 1}: {e}")

                if not found:
                    print(f"  -> Aucun résultat trouvé pour '{date_str}'")

            conn.close()

            QgsMessageLog.logMessage(f"{len(all_occurrences)} date(s) récupérée(s) au sein de la table mesure", "Top'Eau", Qgis.Success)

        except Exception as e:
            if 'conn' in locals():
                conn.close()
            error_msg = f"Erreur lors de la lecture du GPKG: {str(e)}"
            QgsMessageLog.logMessage(error_msg, "Top'Eau", Qgis.Critical)
            QMessageBox.critical(self, "Erreur", error_msg)
            return None

        #date = self.dateDebut.date().toPyDate()

    # fonction permettant de convertir n'importe quel format de date vers le format de date "yyyy-mm-dd" du GPKG
    def convert_to_iso_date(self, value):

        # import des librairies concernées
        from PyQt5.QtCore import QDate, QDateTime
        from datetime import datetime, date

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
                # essayage format DD/MM/YYYY
                if '/' in value:
                    dt = datetime.strptime(value, '%d/%m/%Y')
                    return dt.strftime('%Y-%m-%d')

                # essayage format DD-MM-YYYY
                elif '-' in value and len(value) == 10:
                    dt = datetime.strptime(value, '%d-%m-%Y')
                    return dt.strftime('%Y-%m-%d')

                # essayage format YYYY-MM-DD
                elif '-' in value and value.count('-') == 2:
                    # Si déjà au bon format, extraire seulement la partie date
                    if ' ' in value:
                        return value.split(' ')[0]
                    else:
                        return value

                # si la string contient une heure, extraire seulement la date
                elif ' ' in value:
                    date_part = value.split(' ')[0]
                    return self.convert_to_iso_date(date_part)

                else:
                    # essayer de parser comme datetime
                    dt = datetime.fromisoformat(value.replace('T', ' '))
                    return dt.strftime('%Y-%m-%d')

            except Exception as e:
                print(f"Erreur conversion date '{value}': {e}")
                return str(value)

        else:
            return str(value)
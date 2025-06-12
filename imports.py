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

# appel emplacement des fichiers de stockage des sorties temporaires -- style et temp
temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")

# lien entre traitement.py et traitement.ui
ui_path = os.path.dirname(os.path.abspath(__file__))
ui_path = os.path.join(ui_path, "ui")
form_traitement, _ = uic.loadUiType(os.path.join(ui_path, "import.ui"))


# mise en place de la classe TraitementWidget
# va regrouper l'ensemble des fonctions relatives aux traitements à réaliser
class ImportWidget(QDialog, form_traitement):
    def __init__(self, iface):
        QDialog.__init__(self)

        # création de l'interface de la fenêtre QGIS
        self.setupUi(self)
        # ajustement de la taille de la fenêtre pour qu'elle soit fixe
        #self.setFixedSize(600, 400)
        # nom donné à la fenêtre
        self.setWindowTitle("Top'Eau - Import des données eau (relevés bouées, terrain et piézomètres")

        # Bouton "OK / Annuler"
        self.terminer.rejected.connect(self.reject)

        # connexion de la barre de progression
        self.progressBar.setValue(0)

        # Bouton "Générer l'import'"
        self.generer.clicked.connect(self.inserer_donnees)

    def reject(self):
        QDialog.reject(self)
        return

    # 1. fonction permettant de récupérer les données depuis le CSV et de les insérer dans le GPKG sélectionné
    def inserer_donnees(self):

        # 1.1. récupération des chemins au moment du clic
        selected_GPKG = self.inputGPKG.filePath()
        selected_CSV = self.inputReleves.filePath()

        # 1.2. vérification que les fichiers sont sélectionnés
        if not selected_GPKG or not selected_CSV:
            QgsMessageLog.logMessage("Veuillez sélectionner les fichiers GPKG et CSV", "Top'Eau", Qgis.Warning)
            return

        # mise à jour de la barre de progression
        self.progressBar.setValue(25)

        try:
            # 1.3. lecture du CSV avec Pandas
            df = pd.read_csv(selected_CSV)

            # 1.4. vérification de l'existence des colonnes
            if 'Time' not in df.columns:
                QgsMessageLog.logMessage("Colonne 'Time' non trouvée dans le CSV", "Top'Eau", Qgis.Critical)
                return False

            if 'median_height_24h Physalita2' not in df.columns:
                QgsMessageLog.logMessage("Colonne 'median_height_24h Physalita2' non trouvée dans le CSV", "Top'Eau",
                                         Qgis.Critical)
                return False

            # 1.5. récupération des données comprises dans le CSV via Pandas
            time_data = df['Time']
            niveau_data = df['median_height_24h Physalita2']

            # mise à jour de la barre de progression
            self.progressBar.setValue(50)

            # 1.6. connexion SQLite directe au GeoPackage
            conn = sqlite3.connect(selected_GPKG)
            cursor = conn.cursor()

            # mise à jour de la barre de progression
            self.progressBar.setValue(75)

            # 1.7. insertion ligne par ligne des données et conversion en string pour éviter les erreurs de type
            for i in range(len(df)):
                cursor.execute('''
                       INSERT INTO mesure 
                       (date, 
                       niveau_eau) 
                       VALUES (?, ?)
                   ''', (
                    str(time_data.iloc[i]),
                    str(niveau_data.iloc[i])
                    if pd.notna(niveau_data.iloc[i])
                    else None
                ))

            conn.commit()
            QgsMessageLog.logMessage(f"Table SQLite implémentée avec succès - {len(df)} lignes insérées", "Top'Eau",
                                     Qgis.Success)

            # mise à jour de la barre de progression
            self.progressBar.setValue(100)

            return True

        except FileNotFoundError as e:
            QgsMessageLog.logMessage(f"Fichier non trouvé: {str(e)}", "Top'Eau", Qgis.Critical)
            return False
        except pd.errors.EmptyDataError:
            QgsMessageLog.logMessage("Le fichier CSV est vide", "Top'Eau", Qgis.Critical)
            return False
        except sqlite3.Error as e:
            QgsMessageLog.logMessage(f"Erreur SQLite: {str(e)}", "Top'Eau", Qgis.Critical)
            return False
        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur inattendue: {str(e)}", "Top'Eau", Qgis.Critical)
            return False
        finally:
            if 'conn' in locals():
                conn.close()

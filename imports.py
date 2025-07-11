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
        self.setWindowTitle("Top'Eau - Import des données eau (relevés bouées, terrain et piézomètres)")

        # Bouton "OK / Annuler"
        self.terminer.rejected.connect(self.reject)

        # connexion de la barre de progression
        self.progressBar.setValue(0)

        # Bouton "Générer l'import des données eau"
        self.generer.clicked.connect(self.inserer_donnees)

        # Bouton "Effacer"
        self.erase.clicked.connect(self.effacer_donnees)

        # association de filtres à la sélection de couches dans le projet QGIS
        self.inputReleves_2.setFilters(
            QgsMapLayerProxyModel.NoGeometry |
            QgsMapLayerProxyModel.PluginLayer
        )

        # association de l'import de fichiers aux fonctions de désactivation des listes déroulantes
        self.inputReleves.fileChanged.connect(self.maj_etat_inputReleves2)

    def reject(self):
        QDialog.reject(self)
        return

    # fonctions permettant de désactiver les listes déroulantes des couches si un chemin est renseigné pour l'import de données

    def maj_etat_inputReleves2(self, path):
        path = path.strip()
        if path != "":
            self.inputReleves_2.setEnabled(False)
        else:
            self.inputReleves_2.setEnabled(True)

    # 1. fonction permettant de récupérer les données depuis le CSV et de les insérer dans le GPKG sélectionné
    def inserer_donnees(self):

        # 1.1. récupération des chemins et variables au moment du clic
        selected_GPKG = self.inputGPKG.filePath()
        nom_champ = self.nomChamp.text()
        nom_date = self.nomChamp_2.text()
        selected_CSV = self.inputReleves.filePath()

        # 1.2. vérification que les fichiers sont sélectionnés
        if not selected_GPKG or selected_GPKG.strip() == "":
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier GPKG.")
            return

        if not os.path.exists(selected_GPKG):
            QMessageBox.warning(self, "Erreur", f"Le fichier GPKG n'existe pas : {selected_GPKG}")
            return

        if not nom_champ or nom_champ.strip() == "":
            QMessageBox.warning(self, "Erreur", "Veuillez renseigner le nom du champ niveau d'eau.")
            return

        if not nom_date or nom_date.strip() == "":
            QMessageBox.warning(self, "Erreur", "Veuillez renseigner le nom du champ date.")
            return

        # 1.3. Déterminer la source des données...
        use_layer = False
        layer = None
        # ...localement...
        if not selected_CSV or selected_CSV.strip() == "":
            # ...ou récupération de la couche sélectionnée depuis le projet
            layer = self.inputReleves_2.currentLayer()
            if layer is None or not isinstance(layer, QgsMapLayer):
                QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier de relevés eau.")
                return
            use_layer = True

        else:
        # vérification que le fichier CSV existe
            if not os.path.exists(selected_CSV):
                QMessageBox.warning(self, "Erreur", f"Le fichier CSV n'existe pas : {selected_CSV}")
                return

                # Convertir la couche QGIS en DataFrame
        try:
            # 1.4. lecture des données selon la source
            if use_layer:
                features = []
                for feature in layer.getFeatures():
                    features.append(feature.attributes())

            # 1.5. création du DataFrame avec les noms des champs
                field_names = [field.name() for field in layer.fields()]
                df = pd.DataFrame(features, columns=field_names)

                QgsMessageLog.logMessage(f"Données lues depuis la couche : {layer.name()}", "Top'Eau", Qgis.Info)

            else:
                # OU : lecture depuis le fichier CSV
                df = pd.read_csv(selected_CSV)
                QgsMessageLog.logMessage(f"Données lues depuis le fichier : {selected_CSV}", "Top'Eau", Qgis.Info)

            # vérification que le DataFrame n'est pas vide
            if df.empty:
                QgsMessageLog.logMessage("Les données sont vides", "Top'Eau", Qgis.Critical)
                return False

            # 1.6. vérification de l'existence des colonnes/de la présence des variables dans les fichiers
            if nom_date not in df.columns:
                QgsMessageLog.logMessage(f"Colonne '{nom_date}' non trouvée. Colonnes disponibles : {list(df.columns)}", "Top'Eau", Qgis.Critical)
                return False

            if nom_champ not in df.columns:
                QgsMessageLog.logMessage(f"Colonne '{nom_champ}' non trouvée. Colonnes disponibles : {list(df.columns)}", "Top'Eau", Qgis.Critical)
                return False

            # 1.7. récupération des données comprises dans le DataFrame
            time_data = df[nom_date]
            niveau_data = df[nom_champ]

            # mise à jour de la barre de progression
            self.progressBar.setValue(25)

            # 1.8. connexion SQLite directe au GeoPackage
            conn = sqlite3.connect(selected_GPKG)
            cursor = conn.cursor()

            # mise à jour de la barre de progression
            self.progressBar.setValue(75)

            # 1.9. insertion ligne par ligne des données et conversion en string pour éviter les erreurs de type
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
                )
            )

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

    # 2. si l'utilisateur utilise un GPKG dont la table mesure est déjà complétée, la fonction permet de supprimer les données existantes
    def effacer_donnees(self):

        # 2.1. récupération des chemins au moment du clic
        selected_GPKG = self.inputGPKG.filePath()

        # 2.2. connexion SQLite directe au GeoPackage
        conn = sqlite3.connect(selected_GPKG)
        cursor = conn.cursor()

        # 2.3. suppression des données existantes de la table mesure
        cursor.execute('''
                        DELETE FROM mesure
                        '''
                       )

        conn.commit()
        conn.close()

        QgsMessageLog.logMessage(f"Eléments supprimés de la table mesure avec succès", "Top'Eau", Qgis.Info)





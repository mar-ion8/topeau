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
import sqlite3 #import librairie nécessaire au requêtage SQL
import pandas as pd # import librairie lecture CSV

# lien entre imports.py et import.ui
ui_path = os.path.dirname(os.path.abspath(__file__))
ui_path = os.path.join(ui_path, "ui")
form_traitement, _ = uic.loadUiType(os.path.join(ui_path, "import.ui"))

# mise en place de la classe ImportWidget qui va regrouper l'ensemble des fonctions relatives aux traitements à réaliser
class ImportWidget(QDialog, form_traitement):
    def __init__(self, iface):
        QDialog.__init__(self)

        self.setupUi(self) # création de l'interface de la fenêtre QGIS
        self.setWindowTitle("Top'Eau - Import des données eau (relevés bouées, terrain et piézomètres)") # nom donné à la fenêtre
        self.terminer.rejected.connect(self.reject) # Bouton "OK / Annuler"
        self.progressBar.setValue(0) # connexion de la barre de progression
        self.generer.clicked.connect(self.inserer_donnees) # Bouton "Générer l'import des données eau"
        self.erase.clicked.connect(self.effacer_donnees) # Bouton "Effacer"
        self.inputReleves_2.setFilters(QgsMapLayerProxyModel.NoGeometry)# filtres pour la sélection de couches dans le projet QGIS
        # association de l'import de fichiers aux fonctions de désactivation des listes déroulantes
        self.inputReleves.fileChanged.connect(self.maj_etat_inputReleves2)

    def reject(self):
        QDialog.reject(self)
        return

    # fonction permettant de désactiver les listes déroulantes des couches si un chemin est renseigné pour l'import de données
    def maj_etat_inputReleves2(self, path):
        path = path.strip()
        if path != "":
            self.inputReleves_2.setEnabled(False)
        else:
            self.inputReleves_2.setEnabled(True)

    # fonction permettant de récupérer les données depuis le CSV et de les insérer dans le GPKG sélectionné
    def inserer_donnees(self):

        # récupération des chemins et variables
        selected_GPKG = self.inputGPKG.filePath()
        nom_champ = self.nomChamp.text()
        nom_date = self.nomChamp_2.text()
        selected_CSV = self.inputReleves.filePath()

        # vérification que les fichiers sont sélectionnés
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

        # déterminer la source des données depuis le local ou depuis le projet
        use_layer = False
        layer = None
        if not selected_CSV or selected_CSV.strip() == "":
            layer = self.inputReleves_2.currentLayer()
            if layer is None or not isinstance(layer, QgsMapLayer):
                QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier de relevés eau.")
                return
            use_layer = True
        else:
            if not os.path.exists(selected_CSV): # vérification que le fichier CSV existe
                QMessageBox.warning(self, "Erreur", f"Le fichier CSV n'existe pas : {selected_CSV}")
                return

        try: # conversion de la couche QGIS en DataFrame
            if use_layer:
                features = []
                for feature in layer.getFeatures():
                    features.append(feature.attributes())
                field_names = [field.name() for field in layer.fields()] # création du DataFrame avec les noms des champs
                df = pd.DataFrame(features, columns=field_names)

                QgsMessageLog.logMessage(f"Données lues depuis la couche : {layer.name()}", "Top'Eau", Qgis.Info)

            else: # OU : lecture depuis le fichier CSV
                df = pd.read_csv(selected_CSV)
                QgsMessageLog.logMessage(f"Données lues depuis le fichier : {selected_CSV}", "Top'Eau", Qgis.Info)

            if df.empty: # vérification que le DataFrame n'est pas vide
                QgsMessageLog.logMessage("Les données sont vides", "Top'Eau", Qgis.Critical)
                return False

            if nom_date not in df.columns: # vérification de l'existence des colonnesdans les fichiers
                QgsMessageLog.logMessage(f"Colonne '{nom_date}' non trouvée. Colonnes disponibles : {list(df.columns)}", "Top'Eau", Qgis.Critical)
                return False
            if nom_champ not in df.columns: # vérification de l'existence des champs dans les fichiers
                QgsMessageLog.logMessage(f"Champ '{nom_champ}' non trouvée. Colonnes disponibles : {list(df.columns)}", "Top'Eau", Qgis.Critical)
                return False

            # récupération des données comprises dans le DataFrame
            time_data = df[nom_date]
            niveau_data = df[nom_champ]

            self.progressBar.setValue(25) # mise à jour de la barre de progression

            # connexion SQLite directe au GeoPackage
            conn = sqlite3.connect(selected_GPKG)
            cursor = conn.cursor()

            self.progressBar.setValue(75) # mise à jour de la barre de progression

            # nettoyage des données pour que les valeurs nulles soient gérées en No Data
            niveau_data_clean = niveau_data.apply(lambda x:
                                                  None if str(x).strip() == ''
                                                  else float(str(x).replace('m', '').strip()) if str(x).strip() != ''
                                                  else None
                                                  )

            for i in range(len(df)): # insertion ligne par ligne des données et conversion en string pour éviter les erreurs de type
                cursor.execute('''
                       INSERT INTO mesure 
                       (date, 
                       niveau_eau) 
                       VALUES (?, ?)
                   ''', (
                    str(time_data.iloc[i]),
                    niveau_data_clean.iloc[i]
                )
            )

            conn.commit()
            QgsMessageLog.logMessage(f"Table SQLite implémentée avec succès - {len(df)} lignes insérées", "Top'Eau",
                                     Qgis.Success)
            self.progressBar.setValue(100) # mise à jour de la barre de progression

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

    # si l'utilisateur utilise un GPKG dont la table mesure est déjà complétée, la fonction permet de supprimer les données existantes
    def effacer_donnees(self):

        selected_GPKG = self.inputGPKG.filePath() # récupération des chemins au moment du clic
        # connexion SQLite directe au GeoPackage
        conn = sqlite3.connect(selected_GPKG)
        cursor = conn.cursor()

        cursor.execute('''DELETE FROM mesure''') # suppression des données existantes de la table mesure
        conn.commit()
        conn.close()

        QgsMessageLog.logMessage(f"Eléments supprimés de la table mesure avec succès", "Top'Eau", Qgis.Info)
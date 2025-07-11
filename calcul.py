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

# lien entre traitement.py et traitement.ui
ui_path = os.path.dirname(os.path.abspath(__file__))
ui_path = os.path.join(ui_path, "ui")
form_traitement, _ = uic.loadUiType(os.path.join(ui_path, "calcul.ui"))


# mise en place de la classe CalculWidget
# va regrouper l'ensemble des fonctions relatives aux traitements à réaliser
class CalculWidget(QDialog, form_traitement):
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

        # Bouton "Calculer mes données journalières"
        self.calcJour.clicked.connect(self.calculs_journaliers)

        # Bouton "Calculer mes données mensuelles"
        #self.calcMois.clicked.connect(self.calculs_mensuels)

        # Bouton "Calculer mes données périodiques"
        # self.calcPeriode.clicked.connect(self.calculs_periodiques)

        # connexion de la barre de progression
        self.progressBar.setValue(0)

    def reject(self):
        QDialog.reject(self)
        return

    def calculs_journaliers(self):

        # récupération du GPKG sélectionné par l'utilisateur
        selected_GPKG = self.inputGPKG.filePath()
        if not selected_GPKG or not os.path.exists(selected_GPKG):
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier GPKG valide.")
            return None

        # 1. connexion SQLite au GPKG

        conn = sqlite3.connect(selected_GPKG)
        cursor = conn.cursor()


        # 2.1. suppression de la table donnees_journalieres si elle existe
        try:
            cursor.execute("DROP TABLE IF EXISTS donnees_journalieres")
            QgsMessageLog.logMessage("Table donnees_journalieres supprimée si elle existait", "Top'Eau", Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la suppression de la table : {e}", "Top'Eau", Qgis.Warning)

        # 2.2. création de la nouvelle table "donnees_journalieres"
        try :
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS donnees_journalieres(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE,
                    niveau_eau REAL,
                    point_bas REAL,
                    surface_en_eau REAL,
                    surface_sup_10cm REAL,
                    stress_hydrique REAL,
                    stress_inondation REAL
                )
            ''')

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la création de la table : {e}", "Top'Eau", Qgis.Warning)


        # 3. récupération des données dans les tables créées et implémentées en amont

        # 3.1. récupération du premier décile depuis la table zone_etude
        point_bas = None
        try:
            cursor.execute('''SELECT decile_10 FROM zone_etude''')
            point_bas_result = cursor.fetchone()
            if point_bas_result:
                point_bas = point_bas_result[0]
                #print(f"point_bas extrait: {point_bas} (type: {type(point_bas)})")
            else:
                QgsMessageLog.logMessage(f"'point_bas' ne retourne aucune valeur", "Top'Eau",
                                         Qgis.Warning)

            self.progressBar.setValue(25)

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la requête sur la table zone_etude: {e}", "Top'Eau",
                                         Qgis.Warning)

        # 3.2. requête effectuant la jointure entre mesure & hauteur_eau pour récupérer les dates, niveaux d'eau et surfaces
        try:
            # jointure basée sur le niveau d'eau
            cursor.execute('''
                   SELECT
                        m.date, m.niveau_eau, h.surface_eau_m2 AS surface_en_eau,
                        (h.classe_3 + h.classe_4 + h.classe_5 + h.classe_6 + h.classe_7) AS surface_sup_10cm
                   FROM
                        mesure m
                   JOIN
                        hauteur_eau h ON REPLACE(m.niveau_eau, ' m', '') = h.niveau_eau
                   ORDER BY
                        m.date;
               ''')

            donnees_jointes = cursor.fetchall()

            if not donnees_jointes:
                QgsMessageLog.logMessage("Aucune donnée trouvée avec la jointure", "Top'Eau", Qgis.Warning)
                QMessageBox.warning(self, "Attention", "Aucune donnée trouvée avec la jointure.")
                conn.close()
                return

            self.progressBar.setValue(75)

        except Exception as e:
            print(f"Erreur lors de la requête avec jointure : {e}")
            QgsMessageLog.logMessage(f"Erreur lors de la requête avec jointure : {e}", "Top'Eau", Qgis.Warning)
            conn.close()
            return


        # 4. insertion des données au sein de la table de données journalières

        try:
            compteur_insertions = 0
            # insertion des données sous forme de boucle pour permettre l'insertion de toutes les dates et des valeurs associées
            for donnee in donnees_jointes:
                niveau_str = donnee[1].replace(" m", "").strip() # suppr de l'unité de mesure
                date_mesure = donnee[0]
                niveau_mesure = float(niveau_str)  # conversion du niveau en float pour avoir un nombre
                surface_eau = float(donnee[2])  # conversion du niveau en float pour être sûr d'avoir un nombre
                surface_sup_10cm = float(donnee[3])  # idem

                # création de variables effectuant les calculs pour insérer les données dans la table
                stress_hydrique = (point_bas - 0.42) - niveau_mesure #valeur '0.42' définie par Olivier Gore (EPMP, Suivi de la biodiversité)
                stress_inondation = niveau_mesure - point_bas

                cursor.execute('''
                            INSERT INTO donnees_journalieres(
                                date, niveau_eau, point_bas, surface_en_eau, surface_sup_10cm, stress_hydrique, stress_inondation)
                            VALUES(?, ?, ?, ?, ?, ?, ?)''', (
                    date_mesure,
                    niveau_mesure,
                    point_bas,
                    surface_eau,
                    round(surface_sup_10cm, 2),
                    round(stress_hydrique, 2),
                    round(stress_inondation, 2)
                    )
                )
                compteur_insertions += 1

            conn.commit()

            # vérification du fonctionnement de l'insertion
            cursor.execute("SELECT COUNT(*) FROM donnees_journalieres")
            count = cursor.fetchone()[0]
            print(f"Nombre de lignes insérées: {count}")

            conn.close()

            self.progressBar.setValue(100)

            QgsMessageLog.logMessage(f"Table créée", "Top'Eau", Qgis.Info)

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de l'insertion des données : {e}", "Top'Eau",
                                     Qgis.Warning)
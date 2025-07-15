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
        self.calcMois.clicked.connect(self.calculs_mensuels)

        # Bouton "Calculer mes données périodiques"
        self.calcPeriode.clicked.connect(self.calculs_periodiques)

        # connexion de la barre de progression
        self.progressBar.setValue(0)

    def reject(self):
        QDialog.reject(self)
        return

    # fonction permettant de créer une table récupérant/calculant des valeurs journalières selon les données insérées en 2.
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
                    stress_inondation REAL,
                    pourcentage_inondation REAL,
                    pourcentage_inondation_sup_10cm REAL
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
                QgsMessageLog.logMessage(f"'point_bas' ne retourne aucune valeur", "Top'Eau", Qgis.Warning)

            self.progressBar.setValue(25)

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la requête sur la table zone_etude: {e}", "Top'Eau",
                                         Qgis.Warning)

        # 3.2. récupération de la surface totale depuis la table zone_etude pour calculer les pourcentages
        surface_ze = None
        try:
            cursor.execute('''SELECT surface_m2 FROM zone_etude''')
            surface_ze_result = cursor.fetchone()
            if surface_ze_result:
                surface_ze = surface_ze_result[0]
            else:
                QgsMessageLog.logMessage(f"'surface_m2' ne retourne aucune valeur", "Top'Eau",
                                             Qgis.Warning)

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la requête surface sur la table zone_etude: {e}", "Top'Eau",
                                         Qgis.Warning)

        # 3.3. requête effectuant la jointure entre mesure & hauteur_eau pour récupérer les dates, niveaux d'eau et surfaces
        try:
            # jointure basée sur le niveau d'eau
            cursor.execute(f'''
                   SELECT
                        m.date, m.niveau_eau, h.surface_eau_m2 AS surface_en_eau,
                        (h.classe_3 + h.classe_4 + h.classe_5 + h.classe_6 + h.classe_7) AS surface_sup_10cm,
                        ROUND((h.surface_eau_m2 / '{surface_ze}') * 100 , 2) AS pourcentage_inondation,
                        ROUND(((h.classe_3 + h.classe_4 + h.classe_5 + h.classe_6 + h.classe_7) / '{surface_ze}') * 100 , 2) 
                                        AS pourcentage_inondation_sup_10cm
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
                pourcentage_inondation = float(donnee[4])
                pourcentage_inondation_sup_10cm = float(donnee[5])

                # création de variables effectuant les calculs pour insérer les données dans la table
                stress_hydrique = (point_bas - 0.42) - niveau_mesure #valeur '0.42' définie par Olivier Gore (EPMP, Suivi de la biodiversité)
                stress_inondation = niveau_mesure - point_bas

                cursor.execute('''
                            INSERT INTO donnees_journalieres(
                                date, niveau_eau, point_bas, surface_en_eau, surface_sup_10cm, stress_hydrique, 
                                stress_inondation, pourcentage_inondation, pourcentage_inondation_sup_10cm)
                            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                    date_mesure,
                    niveau_mesure,
                    point_bas,
                    surface_eau,
                    round(surface_sup_10cm, 2),
                    round(stress_hydrique, 2),
                    round(stress_inondation, 2),
                    pourcentage_inondation,
                    pourcentage_inondation_sup_10cm
                    )
                )
                compteur_insertions += 1

            conn.commit()
            conn.close()

            self.progressBar.setValue(100)
            QgsMessageLog.logMessage(f"Table créée", "Top'Eau", Qgis.Info)

            # chargement de la table donnees_journalieres
            layer = self.charger_tables_dans_qgis('donnees_journalieres')
            if layer:
                QgsMessageLog.logMessage(f"Table donnees_journalieres chargée dans QGIS", "Top'Eau", Qgis.Info)
                return layer
            else:
                QgsMessageLog.logMessage(f"Erreur lors du chargement de la table dans QGIS", "Top'Eau", Qgis.Warning)
                return None

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de l'insertion des données : {e}", "Top'Eau",
                                     Qgis.Warning)

    # fonction permettant de créer une table récupérant/calculant des valeurs mensuelles selon les données insérées en 2.
    def calculs_mensuels(self):

        # récupération du GPKG sélectionné par l'utilisateur
        selected_GPKG = self.inputGPKG.filePath()
        if not selected_GPKG or not os.path.exists(selected_GPKG):
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier GPKG valide.")
            return None

        # 1. connexion SQLite au GPKG
        conn = sqlite3.connect(selected_GPKG)
        cursor = conn.cursor()

        # 2.1. suppression de la table donnees_mensuelles si elle existe
        try:
            cursor.execute("DROP TABLE IF EXISTS donnees_mensuelles")
            QgsMessageLog.logMessage("Table donnees_mensuelles supprimée si elle existait", "Top'Eau", Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la suppression de la table : {e}", "Top'Eau", Qgis.Warning)

        # 2.2. création de la nouvelle table "donnees_mensuelles"
        try:
            cursor.execute('''
                        CREATE TABLE IF NOT EXISTS donnees_mensuelles(
                            mois STRING,
                            moyenne_surface_eau_m2 REAL,
                            moyenne_surface_eau_sup_10cm REAL,
                            stress_inondation REAL,
                            stress_hydrique REAL,
                            pourcentage_inondation REAL,
                            pourcentage_inondation_sup_10cm REAL,
                            nbr_jours_sup_point_bas INTEGER,
                            nbr_jours_sup_point_bas_sup10cm INTEGER
                        )
                    ''')

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la création de la table : {e}", "Top'Eau", Qgis.Warning)

        # 3.1. récupération du premier décile depuis la table zone_etude
        point_bas = None
        try:
            cursor.execute('''SELECT decile_10 FROM zone_etude''')
            point_bas_result = cursor.fetchone()
            if point_bas_result:
                point_bas = point_bas_result[0]
            else:
                QgsMessageLog.logMessage(f"'point_bas' ne retourne aucune valeur", "Top'Eau",
                                             Qgis.Warning)

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la requête decile sur la table zone_etude: {e}", "Top'Eau",
                                         Qgis.Warning)

        # 3.2. récupération de la surface totale depuis la table zone_etude pour calculer les pourcentages
        surface_ze = None
        try:
            cursor.execute('''SELECT surface_m2 FROM zone_etude''')
            surface_ze_result = cursor.fetchone()
            if surface_ze_result:
                surface_ze = surface_ze_result[0]
            else:
                QgsMessageLog.logMessage(f"'surface_m2' ne retourne aucune valeur", "Top'Eau",
                                             Qgis.Warning)

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la requête surface sur la table zone_etude: {e}", "Top'Eau",
                                         Qgis.Warning)

        # 3.3. requêtage pour obtenir les valeurs à implémenter/calculer depuis hauteur_eau et zone_etude dans la table
        try:
            cursor.execute(f'''
                            INSERT INTO donnees_mensuelles
                            SELECT 
                                    CASE 
                                        WHEN SUBSTRING(m.date, 6, 2) = '01' THEN 'janvier'
                                        WHEN SUBSTRING(m.date, 6, 2) = '02' THEN 'fevrier'
                                        WHEN SUBSTRING(m.date, 6, 2) = '03' THEN 'mars'
                                        WHEN SUBSTRING(m.date, 6, 2) = '04' THEN 'avril'
                                        WHEN SUBSTRING(m.date, 6, 2) = '05' THEN 'mai'
                                        WHEN SUBSTRING(m.date, 6, 2) = '06' THEN 'juin'
                                        WHEN SUBSTRING(m.date, 6, 2) = '07' THEN 'juillet'
                                        WHEN SUBSTRING(m.date, 6, 2) = '08' THEN 'aout'
                                        WHEN SUBSTRING(m.date, 6, 2) = '09' THEN 'septembre'
                                        WHEN SUBSTRING(m.date, 6, 2) = '10' THEN 'octobre'
                                        WHEN SUBSTRING(m.date, 6, 2) = '11' THEN 'novembre'
                                        WHEN SUBSTRING(m.date, 6, 2) = '12' THEN 'decembre'
                                    END AS mois,
                                    ROUND(AVG(h.surface_eau_m2), 2) AS moyenne_surface_eau_m2,
                                    ROUND(AVG(h.classe_3 + h.classe_4 + h.classe_5 + h.classe_6 + h.classe_7), 2) 
                                        AS moyenne_surface_eau_sup_10cm,
                                    ROUND(AVG(m.niveau_eau) - '{point_bas}', 2) AS stress_inondation,
                                    ROUND(('{point_bas}' - 0.42) - AVG(m.niveau_eau), 2) AS stress_hydrique,
                                    ROUND((AVG(h.surface_eau_m2) / '{surface_ze}' * 100), 2) AS pourcentage_inondation,
                                    ROUND((AVG(h.classe_3 + h.classe_4 + h.classe_5 + h.classe_6 + h.classe_7) / '{surface_ze}') * 100 , 2) 
                                                AS pourcentage_inondation_sup_10cm,
                                    COUNT(CASE WHEN m.niveau_eau > '{point_bas}' THEN 1 END) AS nbr_jours_sup_point_bas,
                                    COUNT(CASE WHEN m.niveau_eau > ('{point_bas}'+0.10) THEN 1 END) AS nbr_jours_sup_point_bas_sup10cm
                                FROM mesure m
                                LEFT JOIN hauteur_eau h ON REPLACE(m.niveau_eau, ' m', '') = h.niveau_eau
                                WHERE m.niveau_eau IS NOT NULL
                                GROUP BY mois
                                ORDER BY m.date''')

            conn.commit()
            conn.close()

            self.progressBar.setValue(100)
            QgsMessageLog.logMessage(f"Table créée", "Top'Eau", Qgis.Info)

            # chargement de la table donnees_mensuelles
            layer = self.charger_tables_dans_qgis('donnees_mensuelles')
            if layer:
                QgsMessageLog.logMessage(f"Table donnees_mensuelles chargée dans QGIS", "Top'Eau", Qgis.Info)
                return layer
            else:
                QgsMessageLog.logMessage(f"Erreur lors du chargement de la table dans QGIS", "Top'Eau", Qgis.Warning)
                return None

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de l'insertion des données : {e}", "Top'Eau", Qgis.Warning)


    # fonction permettant de créer une table récupérant/calculant des valeurs journalières selon les données insérées en 2.
    def calculs_periodiques(self):

        # récupération du GPKG sélectionné par l'utilisateur
        selected_GPKG = self.inputGPKG.filePath()
        if not selected_GPKG or not os.path.exists(selected_GPKG):
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier GPKG valide.")
            return None

        # 1. connexion SQLite au GPKG
        conn = sqlite3.connect(selected_GPKG)
        cursor = conn.cursor()

        # 2.1. suppression de la table donnees_periodiques si elle existe
        try:
            cursor.execute("DROP TABLE IF EXISTS donnees_periodiques")
            QgsMessageLog.logMessage("Table donnees_periodiques supprimée si elle existait", "Top'Eau", Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la suppression de la table : {e}", "Top'Eau", Qgis.Warning)

        # 2.2. création de la nouvelle table "donnees_periodiques"
        try:
            cursor.execute('''
                                CREATE TABLE IF NOT EXISTS donnees_periodiques(
                                    periode STRING,
                                    moyenne_surface_eau_m2 REAL,
                                    moyenne_surface_eau_sup_10cm REAL,
                                    stress_inondation REAL,
                                    stress_hydrique REAL,
                                    pourcentage_inondation REAL,
                                    pourcentage_inondation_sup_10cm REAL,
                                    nbr_jours_sup_point_bas INTEGER,
                                    nbr_jours_sup_point_bas_sup10cm INTEGER
                                )
                            ''')

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la création de la table : {e}", "Top'Eau", Qgis.Warning)

        # 3.1. récupération du premier décile depuis la table zone_etude
        point_bas = None
        try:
            cursor.execute('''SELECT decile_10 FROM zone_etude''')
            point_bas_result = cursor.fetchone()
            if point_bas_result:
                point_bas = point_bas_result[0]
            else:
                QgsMessageLog.logMessage(f"'point_bas' ne retourne aucune valeur", "Top'Eau", Qgis.Warning)

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la requête decile sur la table zone_etude: {e}", "Top'Eau",
                                     Qgis.Warning)

        # 3.2. récupération de la surface totale depuis la table zone_etude pour calculer les pourcentages
        surface_ze = None
        try:
            cursor.execute('''SELECT surface_m2 FROM zone_etude''')
            surface_ze_result = cursor.fetchone()
            if surface_ze_result:
                surface_ze = surface_ze_result[0]
            else:
                QgsMessageLog.logMessage(f"'surface_m2' ne retourne aucune valeur", "Top'Eau",
                                         Qgis.Warning)

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la requête surface sur la table zone_etude: {e}", "Top'Eau",
                                     Qgis.Warning)

        # 3.3. requêtage pour obtenir les valeurs à implémenter/calculer depuis hauteur_eau et zone_etude dans la table
        # NB : les dates délimitant les périodes ont été définies par Olivier Gore
        try:
            cursor.execute(f'''
                            INSERT INTO donnees_periodiques
                                    SELECT 
                                            CASE 
                                                WHEN (SUBSTRING(m.date, 6, 2) = '12' AND CAST(SUBSTRING(m.date, 9, 2) AS INTEGER) >= 16) 
                                                     OR SUBSTRING(m.date, 6, 2) IN ('01', '02') 
                                                     OR (SUBSTRING(m.date, 6, 2) = '03' AND CAST(SUBSTRING(m.date, 9, 2) AS INTEGER) <= 15) 
                                                     THEN 'Hiver'
                                                WHEN (SUBSTRING(m.date, 6, 2) = '03' AND CAST(SUBSTRING(m.date, 9, 2) AS INTEGER) >= 16) 
                                                     OR SUBSTRING(m.date, 6, 2) IN ('04', '05') 
                                                     THEN 'Printemps'
                                                WHEN SUBSTRING(m.date, 6, 2) IN ('06', '07', '08', '09') 
                                                     THEN 'Eté'
                                                WHEN SUBSTRING(m.date, 6, 2) IN ('10', '11') 
                                                     OR (SUBSTRING(m.date, 6, 2) = '12' AND CAST(SUBSTRING(m.date, 9, 2) AS INTEGER) <= 15) 
                                                     THEN 'Automne'
                                            END AS periode,
                                            ROUND(AVG(h.surface_eau_m2), 2) AS moyenne_surface_eau_m2,
                                            ROUND(AVG(h.classe_3 + h.classe_4 + h.classe_5 + h.classe_6 + h.classe_7), 2) 
                                                AS moyenne_surface_eau_sup_10cm,
                                            ROUND(AVG(m.niveau_eau) - '{point_bas}', 2) AS stress_inondation,
                                            ROUND(('{point_bas}' - 0.42) - AVG(m.niveau_eau), 2) AS stress_hydrique,
                                            ROUND((AVG(h.surface_eau_m2) / '{surface_ze}' * 100), 2) AS pourcentage_inondation,
                                        ROUND((AVG(h.classe_3 + h.classe_4 + h.classe_5 + h.classe_6 + h.classe_7) / '{surface_ze}') * 100 , 2) 
                                                AS pourcentage_inondation_sup_10cm,
                                            COUNT(CASE WHEN m.niveau_eau > '{point_bas}' THEN 1 END) AS nbr_jours_sup_point_bas,
                                            COUNT(CASE WHEN m.niveau_eau > ('{point_bas}'+0.10) THEN 1 END) AS nbr_jours_sup_point_bas_sup10cm
                                        FROM mesure m
                                        LEFT JOIN hauteur_eau h ON REPLACE(m.niveau_eau, ' m', '') = h.niveau_eau
                                        WHERE m.niveau_eau IS NOT NULL
                                        GROUP BY periode
                                        ORDER BY m.date''')

            conn.commit()
            conn.close()

            self.progressBar.setValue(100)

            QgsMessageLog.logMessage(f"Table créée", "Top'Eau", Qgis.Info)

            # chargement de la table donnees_periodiques
            layer = self.charger_tables_dans_qgis('donnees_periodiques')
            if layer:
                QgsMessageLog.logMessage(f"Table donnees_periodiques chargée dans QGIS", "Top'Eau", Qgis.Info)
                return layer
            else:
                QgsMessageLog.logMessage(f"Erreur lors du chargement de la table dans QGIS", "Top'Eau", Qgis.Warning)
                return None

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de l'insertion des données : {e}", "Top'Eau", Qgis.Warning)


    # fonction permettant de charger la table dans QGIS une fois qu'elle a été calculée
    def charger_tables_dans_qgis(self, table_name = None):

        try:
            # référence à l'interface QGIS
            from qgis.utils import iface

            # récupération du GPKG
            selected_GPKG = self.inputGPKG.filePath()

            # création d'un seul groupe pour organiser les couches dans le projet QGIS
            root = QgsProject.instance().layerTreeRoot()
            group_name =  f"Top'Eau - Indicateurs calculés"
            group = root.findGroup(group_name)
            if not group:
                # création du groupe en position 0 (au début) seulement s'il n'existe pas
                group = root.insertGroup(0, group_name)
                QgsMessageLog.logMessage(f"Groupe '{group_name}' créé", "Top'Eau", Qgis.Info)
            else:
                QgsMessageLog.logMessage(f"Groupe '{group_name}' trouvé, ajout des couches", "Top'Eau", Qgis.Info)

            # définition de la table à charger
            if table_name:
                # chargement de la table qui vient d'être créée
                tables_attributaires = [table_name]
            else:
                # si erreur : chargement toutes les tables par défaut
                tables_attributaires = ['donnees_mensuelles', 'donnees_periodiques', 'donnees_journalieres']

            loaded_layer = None  # stockage de la couche chargée

            for table in tables_attributaires:
                try:
                    # création d'un URI pour les tables du GPKG
                    uri = f"{selected_GPKG}|layername={table}"

                    # création de la couche
                    layer = QgsVectorLayer(uri, f"{table}", "ogr")

                    if layer.isValid():
                        # ajout de la couche au projet dans le groupe si elle est valide
                        QgsProject.instance().addMapLayer(layer, False)
                        group.addLayer(layer)
                        loaded_layer = layer
                        QgsMessageLog.logMessage(f"Table {table} chargée avec succès", "Top'Eau", Qgis.Info)
                    else:
                        QgsMessageLog.logMessage(f"Impossible de charger la table {table}", "Top'Eau", Qgis.Warning)

                except Exception as e:
                    QgsMessageLog.logMessage(f"Erreur lors du chargement de la table {table}: {str(e)}", "Top'Eau",
                                             Qgis.Warning)

            return loaded_layer

        except Exception as e:
                    QgsMessageLog.logMessage(f"Erreur lors du chargement des tables dans QGIS : {str(e)}", "Top'Eau",
                                             Qgis.Warning)
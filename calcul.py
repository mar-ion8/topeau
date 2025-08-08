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
import sqlite3 # import librairie nécessaire au requêtage SQL

# lien entre calcul.py et calcul.ui
ui_path = os.path.dirname(os.path.abspath(__file__))
ui_path = os.path.join(ui_path, "ui")
form_traitement, _ = uic.loadUiType(os.path.join(ui_path, "calcul.ui"))

# mise en place de la classe CalculWidget qui va regrouper l'ensemble des fonctions relatives aux traitements à réaliser
class CalculWidget(QDialog, form_traitement):
    def __init__(self, iface):
        QDialog.__init__(self)

        self.setupUi(self) # création de l'interface de la fenêtre QGIS
        self.setWindowTitle("Top'Eau - Analyse des données eau : écoute biodiversité") # nom donné à la fenêtre
        self.terminer.rejected.connect(self.reject) # Bouton "OK / Annuler"
        self.calcJour.clicked.connect(self.calculs_journaliers) # Bouton "Calculer mes données journalières"
        self.calcMois.clicked.connect(self.calculs_mensuels)  # Bouton "Calculer mes données mensuelles"
        self.calcPeriode.clicked.connect(self.calculs_periodiques)  # Bouton "Calculer mes données périodiques"
        self.progressBar.setValue(0)  # connexion de la barre de progression

    def reject(self):
        QDialog.reject(self)
        return

    # fonction permettant de créer une table récupérant/calculant des valeurs journalières
    def calculs_journaliers(self):

        selected_GPKG = self.inputGPKG.filePath() # récupération du GPKG sélectionné par l'utilisateur
        if not selected_GPKG or not os.path.exists(selected_GPKG):
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier GPKG valide.")
            return None

        # connexion SQLite au GPKG
        conn = sqlite3.connect(selected_GPKG)
        cursor = conn.cursor()

        try: # suppression de la table donnees_journalieres si elle existe
            cursor.execute("DROP TABLE IF EXISTS donnees_journalieres")
            QgsMessageLog.logMessage("Table donnees_journalieres supprimée si elle existait", "Top'Eau", Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la suppression de la table : {e}", "Top'Eau", Qgis.Warning)

        try : # création de la nouvelle table "donnees_journalieres"
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


        # récupération des données dans les tables créées et implémentées en amont

        point_bas = None
        try: # récupération du premier décile depuis la table zone_etude
            cursor.execute('''SELECT decile_10 FROM zone_etude''')
            point_bas_result = cursor.fetchone()
            if point_bas_result:
                point_bas = point_bas_result[0]
            else:
                QgsMessageLog.logMessage(f"'point_bas' ne retourne aucune valeur", "Top'Eau", Qgis.Warning)

            self.progressBar.setValue(25)

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la requête sur la table zone_etude: {e}", "Top'Eau",
                                         Qgis.Warning)

        surface_ze = None
        try: # récupération de la surface totale depuis la table zone_etude pour calculer les pourcentages
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

        try: # jointure entre mesure & hauteur_eau pour récupérer les dates, niveaux d'eau et surfaces
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

        try: # insertion des données au sein de la table de données journalières
            compteur_insertions = 0
            # insertion des données sous forme de boucle pour permettre l'insertion de toutes les dates et des valeurs associées
            for donnee in donnees_jointes:
                niveau_str = donnee[1]
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
            QgsMessageLog.logMessage(f"Table donnees_journalieres créée", "Top'Eau", Qgis.Info)

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

    # fonction permettant de créer une table récupérant/calculant des valeurs mensuelles
    def calculs_mensuels(self):

        selected_GPKG = self.inputGPKG.filePath() # récupération du GPKG sélectionné par l'utilisateur
        if not selected_GPKG or not os.path.exists(selected_GPKG):
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier GPKG valide.")
            return None

        # connexion SQLite au GPKG
        conn = sqlite3.connect(selected_GPKG)
        cursor = conn.cursor()

        try: # suppression de la table donnees_mensuelles si elle existe
            cursor.execute("DROP TABLE IF EXISTS donnees_mensuelles")
            QgsMessageLog.logMessage("Table donnees_mensuelles supprimée si elle existait", "Top'Eau", Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la suppression de la table : {e}", "Top'Eau", Qgis.Warning)

        try: # création de la table "donnees_mensuelles"
            cursor.execute('''
                        CREATE TABLE IF NOT EXISTS donnees_mensuelles(
                            annee INTEGER,
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

        point_bas = None
        try: # récupération du premier décile depuis la table zone_etude
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


        surface_ze = None
        try: # récupération de la surface totale depuis la table zone_etude pour calculer les pourcentages
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

        try: # requêtage pour obtenir les valeurs à implémenter/calculer depuis hauteur_eau et zone_etude dans la table
            cursor.execute(f'''
                            INSERT INTO donnees_mensuelles
                            SELECT 
                                CAST(substr(m.date, 1, 4) AS INTEGER) AS annee,
                                CASE 
                                    WHEN substr(m.date, 6, 2) = '01' THEN 'janvier'
                                    WHEN substr(m.date, 6, 2) = '02' THEN 'fevrier'
                                    WHEN substr(m.date, 6, 2) = '03' THEN 'mars'
                                    WHEN substr(m.date, 6, 2) = '04' THEN 'avril'
                                    WHEN substr(m.date, 6, 2) = '05' THEN 'mai'
                                    WHEN substr(m.date, 6, 2) = '06' THEN 'juin'
                                    WHEN substr(m.date, 6, 2) = '07' THEN 'juillet'
                                    WHEN substr(m.date, 6, 2) = '08' THEN 'aout'
                                    WHEN substr(m.date, 6, 2) = '09' THEN 'septembre'
                                    WHEN substr(m.date, 6, 2) = '10' THEN 'octobre'
                                    WHEN substr(m.date, 6, 2) = '11' THEN 'novembre'
                                    WHEN substr(m.date, 6, 2) = '12' THEN 'decembre'
                                END AS mois,
                                ROUND(AVG(h.surface_eau_m2), 2) AS moyenne_surface_eau_m2,
                                ROUND(AVG(h.classe_3 + h.classe_4 + h.classe_5 + h.classe_6 + h.classe_7), 2) 
                                    AS moyenne_surface_eau_sup_10cm,
                                ROUND(AVG(CAST(REPLACE(m.niveau_eau, ' m', '') AS REAL)) - {point_bas}, 2) AS stress_inondation,
                                ROUND(({point_bas} - 0.42) - AVG(CAST(REPLACE(m.niveau_eau, ' m', '') AS REAL)), 2) AS stress_hydrique,
                                ROUND((AVG(h.surface_eau_m2) / {surface_ze} * 100), 2) AS pourcentage_inondation,
                                ROUND((AVG(h.classe_3 + h.classe_4 + h.classe_5 + h.classe_6 + h.classe_7) / {surface_ze}) * 100, 2) 
                                    AS pourcentage_inondation_sup_10cm,
                                COUNT(CASE WHEN CAST(REPLACE(m.niveau_eau, ' m', '') AS REAL) > {point_bas} THEN 1 END) AS nbr_jours_sup_point_bas,
                                COUNT(CASE WHEN CAST(REPLACE(m.niveau_eau, ' m', '') AS REAL) > ({point_bas}+0.10) THEN 1 END) AS nbr_jours_sup_point_bas_sup10cm
                            FROM mesure m
                            LEFT JOIN hauteur_eau h ON REPLACE(m.niveau_eau, ' m', '') = h.niveau_eau
                            WHERE m.niveau_eau IS NOT NULL
                            GROUP BY substr(m.date, 1, 4), substr(m.date, 6, 2)
                            ORDER BY substr(m.date, 6, 2), substr(m.date, 1, 4);''')

            conn.commit()
            conn.close()

            self.progressBar.setValue(100)
            QgsMessageLog.logMessage(f"Table donnees_mensuelles créée", "Top'Eau", Qgis.Info)

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


    # fonction permettant de créer une table récupérant/calculant des valeurs périodiques
    def calculs_periodiques(self):

        selected_GPKG = self.inputGPKG.filePath() # récupération du GPKG sélectionné par l'utilisateur
        if not selected_GPKG or not os.path.exists(selected_GPKG):
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier GPKG valide.")
            return None

        # connexion SQLite au GPKG
        conn = sqlite3.connect(selected_GPKG)
        cursor = conn.cursor()

        try: # suppression de la table donnees_periodiques si elle existe
            cursor.execute("DROP TABLE IF EXISTS donnees_periodiques")
            QgsMessageLog.logMessage("Table donnees_periodiques supprimée si elle existait", "Top'Eau", Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la suppression de la table : {e}", "Top'Eau", Qgis.Warning)

        try:  # création de la nouvelle table "donnees_periodiques"
            cursor.execute('''
                                CREATE TABLE IF NOT EXISTS donnees_periodiques(
                                    annee INTEGER,
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

        point_bas = None
        try:  # récupération du premier décile depuis la table zone_etude
            cursor.execute('''SELECT decile_10 FROM zone_etude''')
            point_bas_result = cursor.fetchone()
            if point_bas_result:
                point_bas = point_bas_result[0]
            else:
                QgsMessageLog.logMessage(f"'point_bas' ne retourne aucune valeur", "Top'Eau", Qgis.Warning)
        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la requête decile sur la table zone_etude: {e}", "Top'Eau",
                                     Qgis.Warning)

        surface_ze = None
        try: # récupération de la surface totale depuis la table zone_etude pour calculer les pourcentages
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

        try:  # requêtage pour obtenir les valeurs à implémenter/calculer depuis hauteur_eau et zone_etude dans la table
            cursor.execute(f'''
                            INSERT INTO donnees_periodiques
                                    SELECT 
                                        CAST(substr(m.date, 1, 4) AS INTEGER) AS annee,
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
                                        GROUP BY substr(m.date, 1, 4), periode
                                        ORDER BY annee, periode;''')
            # NB : les dates délimitant les périodes ont été définies par Olivier Gore
            conn.commit()
            conn.close()

            self.progressBar.setValue(100)
            QgsMessageLog.logMessage(f"Table donnes_periodiques créée", "Top'Eau", Qgis.Info)

            layer = self.charger_tables_dans_qgis('donnees_periodiques') # chargement de la table donnees_periodiques
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
            from qgis.utils import iface # référence à l'interface QGIS
            selected_GPKG = self.inputGPKG.filePath() # récupération du GPKG

            # création d'un seul groupe pour organiser les couches dans le projet QGIS
            root = QgsProject.instance().layerTreeRoot()
            group_name =  f"Top'Eau - Indicateurs calculés"
            group = root.findGroup(group_name)
            if not group:
                group = root.insertGroup(0, group_name) # création du groupe en position 0 (au début) s'il n'existe pas
                QgsMessageLog.logMessage(f"Groupe '{group_name}' créé", "Top'Eau", Qgis.Info)
            else:
                QgsMessageLog.logMessage(f"Groupe '{group_name}' trouvé, ajout des couches", "Top'Eau", Qgis.Info)

            if table_name: # chargement de la table qui vient d'être créée
                tables_attributaires = [table_name]
            else: # si erreur : chargement toutes les tables par défaut
                tables_attributaires = ['donnees_mensuelles', 'donnees_periodiques', 'donnees_journalieres']

            loaded_layer = None  # stockage de la couche chargée

            for table in tables_attributaires:
                try:
                    uri = f"{selected_GPKG}|layername={table}" # création d'un URI pour les tables du GPKG
                    layer = QgsVectorLayer(uri, f"{table}", "ogr") # création de la couche

                    if layer.isValid(): # ajout de la couche au projet dans le groupe si elle est valide
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
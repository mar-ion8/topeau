# -*- coding: utf-8 -*-

# fichier contenant les fonctions liées à la boucle de génération des rasters

# Import module PyQt et API PyQGIS
from qgis import core, gui
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5 import uic
from PyQt5.QtGui import *
from qgis.core import *
from qgis.core import Qgis, QgsMessageLog
from qgis import processing
from qgis.core import QgsRasterLayer
import os
# import des librairies nécessaires à la lecture de données géospatiales
import json
# import librairie nécessaire à certains calculs
import math
import statistics
# import librairie manipulation raster et gpkg
import rasterio
from rasterio.transform import from_origin
import numpy as np
import subprocess
from osgeo import gdal, ogr, osr
import sqlite3
from datetime import datetime
# import fichiers de code supplémentaires contenant fonctions/variables
from . import query
from . import visu
from . import params
from . import traitement

# fonction permettant de découper le raster en entrée
def decouper_raster(selected_raster, selected_vecteur):

    path_clip = os.path.join(params.temp_path, "temp_layer_clip.tif")  # création d'un fichier temporaire
    # utilisation de l'algorithme GDAL "Découper un raster selon une couche de masque"
    processing.run("gdal:cliprasterbymasklayer", {
        'INPUT': selected_raster,  # variable récupérant le raster sélectionné par l'utilisateur
        'MASK': selected_vecteur,  # variable récupérant le vecteur sélectionné par l'utilisateur
        'SOURCE_CRS': None,
        'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:2154'),
        # permet de s'assurer que le raster découpé sera bien en 2154
        'TARGET_EXTENT': None,
        'NODATA': -9999,  # permet aux pixels à valeur nulle de ne pas être comptés dans l'emprise du raster
        'ALPHA_BAND': False,
        'CROP_TO_CUTLINE': True,
        'KEEP_RESOLUTION': False,
        'SET_RESOLUTION': False,
        'X_RESOLUTION': None,
        'Y_RESOLUTION': None,
        'MULTITHREADING': False,
        'OPTIONS': None,
        'DATA_TYPE': 0,
        'EXTRA': '',
        'OUTPUT': path_clip  # sortie permanente en temp pour que l'algorithme suivant puisse avoir une couche input
    })

# fonction permettant de calculer la différence entre le niveau d'eau à étudier et le raster relatif à l'élévation
def calcul_niveau_eau(niveau_eau):

    # chargement du raster découpé précédemment
    path_clip = os.path.join(params.temp_path, "temp_layer_clip.tif")
    layer_clip = QgsRasterLayer(path_clip, f"parcelle_decoupee", "gdal")

    if not layer_clip.isValid(): # vérification de la validité de la couche
        # QMessageBox.warning(self, "Erreur", "La couche raster découpée n'est pas valide.")
        return None

    path_diff = os.path.join(params.temp_path, f"diff_{int(niveau_eau * 100)}.tif") # fichier temp résultat généré par la calculatrice
    expression = f"{niveau_eau} - \"parcelle_decoupee@1\""  # création d'une expression raster unique avec le niveau d'eau à étudier

    # utilisation de l'outil natif "Calculatrice raster"
    processing.run("native:rastercalc", {
        'LAYERS': [layer_clip],
        'EXPRESSION': expression,
        'EXTENT': layer_clip.extent(),
        'CELL_SIZE': layer_clip.rasterUnitsPerPixelX(),
        'CRS': layer_clip.crs(),
        'OUTPUT': path_diff
    })

    path_reclass = os.path.join(params.temp_path,f"reclass_{int(niveau_eau * 100)}.tif")  # fichier temporaire pour la reclassif
    # utilisation de l'outil natif "Reclassification" pour supprimer les valeurs négatives
    processing.run("native:reclassifybytable", {
        'INPUT_RASTER': path_diff,
        'RASTER_BAND': 1,
        'TABLE': ['-9999', '0', 'nan'],  # remplacer les valeurs négatives par NaN
        'NO_DATA': -9999,
        'RANGE_BOUNDARIES': 0,
        'NODATA_FOR_MISSING': False,
        'DATA_TYPE': 5,
        'CREATE_OPTIONS': None,
        'OUTPUT': path_reclass
    })
    return path_reclass

# fonction permettant de ré-échantillonné le raster pour alléger et la donnée
def resample_raster(input_path, output_name, resolution):

    layer_reclass = QgsRasterLayer(input_path, "reclass_layer")
    if not layer_reclass.isValid(): # vérification de la validité du chemin d'entrée
        QgsMessageLog.logMessage(f"La couche à rééchantillonner n'est pas valide: {input_path}", "Top'Eau",
                                 Qgis.Warning)
        return None

    '''
    # A VOIR SI SUPPRESSION

    # ajustement : ajout découpage pour éviter la création d'un contour rectangulaire aberrant lors de la création du raster
    path_reclip = os.path.join(params.temp_path, f"{output_name}_reclip.tif")
    selected_vecteur = getattr(self, 'selected_vecteur_path', None)

    processing.run("gdal:cliprasterbymasklayer", {
        'INPUT': layer_reclass,
        'MASK': selected_vecteur,
        'SOURCE_CRS': QgsCoordinateReferenceSystem('EPSG:2154'),
        'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:2154'),
        'TARGET_EXTENT': None,
        'NODATA': -9999,
        'ALPHA_BAND': False,
        'CROP_TO_CUTLINE': True,
        'KEEP_RESOLUTION': False,
        'SET_RESOLUTION': False,
        'X_RESOLUTION': None,
        'Y_RESOLUTION': None,
        'MULTITHREADING': False,
        'OPTIONS': None,
        'DATA_TYPE': 0,
        'EXTRA': '',
        'OUTPUT': path_reclip})

    # NB : changer l'input de r.resamp.stats en "path_reclip" si conservation
    '''

    path_resamp = os.path.join(params.temp_path, f"{output_name}_resamp.tif")  # fichier final du raster rééchantillonné
    # utilisation de l'algorithme GRASS "r.resamp.Stats" pour le ré-échantillonnage
    processing.run("grass:r.resamp.stats", {
        'input': layer_reclass,
        'method': 1,  # mediane
        'quantile': 0.5,
        '-n': True,
        '-w': False,
        'output': path_resamp,
        'GRASS_REGION_PARAMETER': None,
        'GRASS_REGION_CELLSIZE_PARAMETER': resolution,
        'GRASS_RASTER_FORMAT_OPT': '',
        'GRASS_RASTER_FORMAT_META': ''
    })
    return path_resamp if os.path.exists(path_resamp) else None # calcul automatique de la surface après création du raster

# fonction permettant de vectoriser le raster généré afin d'en récupérer la géométrie
def vectoriser_raster(path_resamp, output_name):
    try:

        if path_resamp is None: # vérification de la récupération du raster ré-échantillonné
            raise Exception(f"Impossible d'ouvrir le raster {path_resamp}")

        raster_vectorise = os.path.join(params.temp_path, f"{output_name}_vecteur.gpkg")  # chemin temp pour le vecteur
        # utilisation de l'algorithme GDAL "Polygoniser" pour passer le raster généré en vecteur
        processing.run("gdal:polygonize", {
            'INPUT': path_resamp,
            'BAND': 1,
            'FIELD': 'DN',
            'EIGHT_CONNECTEDNESS': False,
            'EXTRA': '',
            'OUTPUT': raster_vectorise
        })
        return raster_vectorise

    except Exception as e:
        QgsMessageLog.logMessage(f"Erreur vectorisation du raster: {str(e)}", "Top'Eau", Qgis.Critical)
        return None

# fonction permettant d'assigner les calculs de surface et volume aux pixels non nuls du raster généré
def calculer_stats_raster(path_resamp):
    try:
        dataset = gdal.Open(path_resamp)  # traitement du raster avec GDAL
        if dataset is None:
            raise Exception(f"Impossible d'ouvrir le raster {path_resamp}")

        # récupération des informations du raster
        band = dataset.GetRasterBand(1)
        geo_transform = dataset.GetGeoTransform()
        # récupération de la résolution des pixels
        pixel_width = abs(geo_transform[1])  # largeur d'un pixel
        pixel_height = abs(geo_transform[5])  # hauteur d'un pixel
        surface_pixel = pixel_width * pixel_height  # surface d'un pixel en m²
        # lecture des données du raster
        data = band.ReadAsArray()
        nodata_value = band.GetNoDataValue()

        # comptage des pixels non-nuls
        if nodata_value is not None:
            pixels_valides = np.count_nonzero(~np.isnan(data) & (data != nodata_value))
        else:
            pixels_valides = np.count_nonzero(~np.isnan(data) & (data != 0))

        surface_totale = pixels_valides * surface_pixel # calcul de la surface totale
        # calcul du volume : somme des hauteurs d'eau valides × surface d'un pixel
        if nodata_value is not None:
            mask = (~np.isnan(data)) & (data != nodata_value)
        else:
            mask = (~np.isnan(data)) & (data != 0)

        # calcul de la surface en fonction de classes prédéfinies
        pixels_cl1 = np.count_nonzero((data > 0) & (data <= 0.05))
        classe_1_surf = pixels_cl1 * surface_pixel

        pixels_cl2 = np.count_nonzero((data > 0.05) & (data <= 0.10))
        classe_2_surf = pixels_cl2 * surface_pixel

        pixels_cl3 = np.count_nonzero((data > 0.10) & (data <= 0.15))
        classe_3_surf = pixels_cl3 * surface_pixel

        pixels_cl4 = np.count_nonzero((data > 0.15) & (data <= 0.20))
        classe_4_surf = pixels_cl4 * surface_pixel

        pixels_cl5 = np.count_nonzero((data > 0.20) & (data <= 0.25))
        classe_5_surf = pixels_cl5 * surface_pixel

        pixels_cl6 = np.count_nonzero((data > 0.25) & (data <= 0.30))
        classe_6_surf = pixels_cl6 * surface_pixel

        pixels_cl7 = np.count_nonzero(data > 0.30)
        classe_7_surf = pixels_cl7 * surface_pixel

        pixels_valides = np.count_nonzero(mask)
        surface_totale = pixels_valides * surface_pixel
        volume_total = np.sum(data[mask]) * surface_pixel

        return surface_totale, pixels_valides, volume_total, classe_1_surf, classe_2_surf, classe_3_surf, classe_4_surf, classe_5_surf, classe_6_surf, classe_7_surf

    except Exception as e:
        QgsMessageLog.logMessage(f"Erreur calcul surface raster: {str(e)}", "Top'Eau", Qgis.Critical)
        return None, None, None
    finally:
        dataset = None

# fonction permettant d'ajouter les données dans la table hauteur_eau
def ajouter_donnees_table_gpkg(gpkg_path, surface_totale, volume_total,
                               classe_1_surf, classe_2_surf, classe_3_surf, classe_4_surf, classe_5_surf,
                               classe_6_surf, classe_7_surf, current_level, nom_ze, raster_vectorise_path=None):

    try:

        if not os.path.exists(gpkg_path): # vérification de l'existence du GPKG
            QgsMessageLog.logMessage(f"GPKG inexistant pour ajout données: {gpkg_path}", "Top'Eau", Qgis.Warning)
            return False

        # génération du nom du raster pour la table
        niveau_cm = int(current_level * 100)
        raster_name = f"{nom_ze}_{niveau_cm}cm_topeau.tif"

        # récupération de la géométrie du polygone correspondant à la surface inondée
        geom_raster_wkb = None  # instauration d'une variable qui servira pour la récupération de la géométrie en WKT
        min_x, min_y, max_x, max_y = None, None, None, None

        try:
            if raster_vectorise_path and os.path.exists(raster_vectorise_path):
                # chargement de la couche vecteur
                vector_layer = QgsVectorLayer(raster_vectorise_path, "temp_vector", "ogr")
                if vector_layer.isValid():
                    features = vector_layer.getFeatures()  # récupération des entités du vecteur
                    all_geoms = []  # création d'une géométrie unifiée de toutes les entités
                    for feature in features:
                        geom = feature.geometry()
                        if geom and not geom.isEmpty():
                            all_geoms.append(geom)

                    if all_geoms:
                        if len(all_geoms) == 1:  # fusion de toutes les géométries en une seule
                            unified_geom = all_geoms[0]
                        else:
                            unified_geom = QgsGeometry.unaryUnion(all_geoms)

                        if unified_geom and not unified_geom.isEmpty():
                            if unified_geom.wkbType() == QgsWkbTypes.Polygon:  # conversion en multiploygon si nécessaire
                                unified_geom.convertToMultiType()
                            geom_raster_wkb = unified_geom.asWkb()
                            # calcul des extent pour mise à jour de gpkg_contents
                            bbox = unified_geom.boundingBox()
                            min_x = bbox.xMinimum()
                            min_y = bbox.yMinimum()
                            max_x = bbox.xMaximum()
                            max_y = bbox.yMaximum()

                            QgsMessageLog.logMessage(f"Géométrie récupérée pour la surface inondée", "Top'Eau",
                                                     Qgis.Info)
                        else: QgsMessageLog.logMessage(f"Échec de l'union des géométries", "Top'Eau", Qgis.Warning)
                    else: QgsMessageLog.logMessage(f"Aucune géométrie valide trouvée", "Top'Eau", Qgis.Warning)
                else: QgsMessageLog.logMessage(f"Couche vecteur invalide: {raster_vectorise_path}", "Top'Eau", Qgis.Warning)
            else: QgsMessageLog.logMessage(f"Chemin du vecteur non fourni ou inexistant", "Top'Eau", Qgis.Warning)
        except Exception as geom_error:
            QgsMessageLog.logMessage(f"Erreur lors de la récupération de la géométrie : {str(geom_error)}",
                                     "Top'Eau", Qgis.Warning)

        # connexion SQLite directe au GeoPackage
        conn = sqlite3.connect(gpkg_path)
        cursor = conn.cursor()
        # chargement de SpatiaLite pour cette connexion
        spatialite_loaded = False
        conn.enable_load_extension(True)

        try:
            conn.load_extension("mod_spatialite")
            spatialite_loaded = True
            QgsMessageLog.logMessage("SpatiaLite chargé pour cette connexion", "Top'Eau", Qgis.Info)
        except:
            try:
                conn.load_extension("spatialite")
                spatialite_loaded = True
                QgsMessageLog.logMessage("SpatiaLite chargé (spatialite) pour cette connexion", "Top'Eau",
                                         Qgis.Info)
            except:
                spatialite_loaded = False
                QgsMessageLog.logMessage("SpatiaLite non disponible pour cette connexion", "Top'Eau", Qgis.Info)

        if geom_raster_wkb: # insertion du contenu dans la table si on récupère la geom en WKB
            if spatialite_loaded:  # test de validité avec SpatiaLite
                try:
                    cursor.execute("SELECT ST_IsValid(ST_GeomFromWKB(?, ?))", (geom_raster_wkb, 2154))
                    is_valid = cursor.fetchone()[0]
                    if not is_valid:
                        QgsMessageLog.logMessage("Géométrie invalide détectée, tentative de réparation", "Top'Eau",
                                                 Qgis.Warning)
                        # tentative de réparation de la géométrie si elle n'est pas valide
                        cursor.execute("SELECT ST_AsBinary(ST_MakeValid(ST_GeomFromWKB(?, ?)))",(geom_raster_wkb, 2154))
                        geom_result = cursor.fetchone()
                        if geom_result and geom_result[0]:
                            geom_raster_wkb = geom_result[0]
                except Exception as e:
                    QgsMessageLog.logMessage(f"Erreur validation géométrie: {str(e)}", "Top'Eau", Qgis.Warning)

                # insertion des données avec SpatiaLite
                cursor.execute(query.q_17, (
                    geom_raster_wkb,
                    2154,
                    round(current_level, 2),
                    nom_ze,
                    round(surface_totale, 2),
                    round(volume_total, 2),
                    round(classe_1_surf, 2),
                    round(classe_2_surf, 2),
                    round(classe_3_surf, 2),
                    round(classe_4_surf, 2),
                    round(classe_5_surf, 2),
                    round(classe_6_surf, 2),
                    round(classe_7_surf, 2),
                    raster_name
                ))
            else:  # insertion directe avec les fonctions GPKG natives (géométrie en blob)
                cursor.execute(query.q_18, (
                    geom_raster_wkb,
                    round(current_level, 2),
                    nom_ze,
                    round(surface_totale, 2),
                    round(volume_total, 2),
                    round(classe_1_surf, 2),
                    round(classe_2_surf, 2),
                    round(classe_3_surf, 2),
                    round(classe_4_surf, 2),
                    round(classe_5_surf, 2),
                    round(classe_6_surf, 2),
                    round(classe_7_surf, 2),
                    raster_name
                ))

            # mise à jour des extent dans gpkg_contents
            if min_x is not None and min_y is not None and max_x is not None and max_y is not None:
                cursor.execute(query.q_19, (min_x, min_y, max_x, max_y))
                result = cursor.fetchone()
                if result and all(v is not None for v in result):
                    cursor.execute('''
                                        UPDATE gpkg_contents 
                                        SET min_x = ?, min_y = ?, max_x = ?, max_y = ?, last_change = ?
                                        WHERE table_name = 'hauteur_eau'
                                        ''', (result[0], result[1], result[2], result[3],
                                              datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ')))

        else:  # insertion sans géométrie si elle n'est pas disponible
            cursor.execute(query.q_20, (
                round(current_level, 2),
                nom_ze,
                round(surface_totale, 2),
                round(volume_total, 2),
                round(classe_1_surf, 2),
                round(classe_2_surf, 2),
                round(classe_3_surf, 2),
                round(classe_4_surf, 2),
                round(classe_5_surf, 2),
                round(classe_6_surf, 2),
                round(classe_7_surf, 2),
                raster_name
            ))

        conn.commit()
        QgsMessageLog.logMessage(f"Données ajoutées avec succès à la table hauteur_eau", "Top'Eau", Qgis.Success)
        return True

    except Exception as e:
        QgsMessageLog.logMessage(f"Erreur ajout données table GPKG: {str(e)}", "Top'Eau", Qgis.Critical)
        raise e
    finally:
        if 'conn' in locals():
            conn.close()

# fonction permettant de formater les TIFF pour qu'ils passent en GeoPackage
def ajouter_raster_au_gpkg(path_resamp, gpkg_path, table_name):

    try:

        if not os.path.exists(gpkg_path): # vérification de l'existence du GPKG
            QgsMessageLog.logMessage(f"GPKG inexistant: {gpkg_path}", Qgis.Warning)
            return False

        # utilisation de l'API GDAL pour la conversion
        try:
            src_ds = gdal.Open(path_resamp)  # ouverture du raster source avec GDAL
            if src_ds is None:
                QMessageBox.warning(self, "Erreur", f"Impossible d'ouvrir le fichier source: {path_resamp}")
                return None
            # lecture des métadonnées du raster source
            band = src_ds.GetRasterBand(1)
            data_type = band.DataType
            xsize = src_ds.RasterXSize
            ysize = src_ds.RasterYSize
            geo_transform = src_ds.GetGeoTransform()
            projection = src_ds.GetProjection()
            # conversion du raster via l'ajout d'un driver GDAL
            driver = gdal.GetDriverByName('GPKG')
            if driver is None:
                QMessageBox.warning(self, "Erreur",
                                    "Le pilote GPKG n'est pas disponible dans cette installation GDAL")
                return None

            # configuration des options de création du GPKG
            options = ['-of', 'GPKG', '-co', f'RASTER_TABLE={table_name}', '-co', 'APPEND_SUBDATASET=YES']

            # création du GeoPackage & modification du type de données à Float32 qui est compatible avec GeoPackage
            dst_ds = driver.Create(gpkg_path, xsize, ysize, 1, gdal.GDT_Float32, options)

            if dst_ds is None:  # vérification de la validité du GPKG créé
                QMessageBox.warning(self, "Erreur", f"Impossible de créer le fichier GeoPackage")
                return None

            # copie des métadonnées géospatiales
            dst_ds.SetGeoTransform(geo_transform)
            dst_ds.SetProjection(projection)
            # copie des données
            data = band.ReadAsArray(0, 0, xsize, ysize)
            dst_band = dst_ds.GetRasterBand(1)
            # définition de la valeur nodata puisqu'elle existe et qu'on veut s'en servir pour les calculs de stat
            nodata_value = band.GetNoDataValue()
            if nodata_value is not None:
                dst_band.SetNoDataValue(nodata_value)

            dst_band.WriteArray(data)  # écriture des données
            dst_ds.FlushCache()  # traitement du cache
            dst_ds = None
            src_ds = None

            if os.path.exists(gpkg_path):  # vérification de la création du GPKG
                QgsMessageLog.logMessage(f"GeoPackage créé avec succès: {gpkg_path}", "Top'Eau", Qgis.Success)

                qml_file = os.path.join(params.qml_path, 'style_topeau.qml') # ajout d'un fichier de style pour les rasters
                try:
                    # chargement de la couche raster depuis le GeoPackage
                    uri = f"GPKG:{gpkg_path}:{table_name}"
                    rlayer = QgsRasterLayer(uri, table_name, 'gdal')
                    if not rlayer.isValid():
                        raise ValueError(f"Impossible de charger {uri} comme QgsRasterLayer")

                    # enregistrement temporaire dans le projet (nécessaire pour saveStyleToDatabase)
                    proj = QgsProject.instance()
                    proj.addMapLayer(rlayer, False)

                    # chargement du QML et application à la couche
                    rlayer.loadNamedStyle(qml_file)
                    rlayer.triggerRepaint()

                    # sauvegarde dans la table layer_styles du GPKG
                    err = rlayer.saveStyleToDatabase(
                        'default',  # nom du style
                        'Style embarqué',  # description
                        True,  # use as default
                        None  # on passe None : QGIS reprendra le style en mémoire
                    )
                    if err:
                        QgsMessageLog.logMessage(f"Erreur saveStyleToDatabase pour {table_name} : {err}", "Top'Eau",
                                                 Qgis.Warning)
                    else:
                        QgsMessageLog.logMessage(f"Symbologie embarquée dans {table_name}", "Top'Eau", Qgis.Info)

                    # nettoyage : retirer la couche du projet (on n’en a plus besoin)
                    proj.removeMapLayer(rlayer.id())

                except Exception as e:
                    QgsMessageLog.logMessage(f"Échec injection style QML : {e}", "Top'Eau", Qgis.Warning)

                qml_ze = os.path.join(params.qml_path, 'style_ze.qml') # ajout du fichier de style pour zone_etude
                try:
                    # chargement de la couche zone_etude depuis le GeoPackage
                    uri = f"{gpkg_path}|layername=zone_etude"
                    rZE = QgsVectorLayer(uri, 'zone_etude', 'ogr')
                    if not rZE.isValid():
                        raise ValueError(f"Impossible de charger {uri} comme QgsVectorLayer")

                    # enregistrement temporairement dans le projet (nécessaire pour saveStyleToDatabase)
                    proj = QgsProject.instance()
                    proj.addMapLayer(rZE, False)

                    # chargement du QML et application à la couche
                    rZE.loadNamedStyle(qml_ze)
                    rZE.triggerRepaint()

                    # sauvegarde dans la table layer_styles du GPKG
                    err = rZE.saveStyleToDatabase(
                        'default',  # nom du style
                        'Style embarqué',  # description
                        True,  # use as default
                        None  # on passe None : QGIS reprendra le style en mémoire
                    )
                    if err:
                        QgsMessageLog.logMessage(f"Erreur saveStyleToDatabase pour zone_etude : {err}", "Top'Eau",
                                                 Qgis.Warning)
                    else:
                        QgsMessageLog.logMessage(f"Symbologie embarquée dans zone_etude", "Top'Eau", Qgis.Info)

                    # nettoyage : retirer la couche du projet (on n’en a plus besoin)
                    proj.removeMapLayer(rZE.id())

                except Exception as e:
                    QgsMessageLog.logMessage(f"Échec injection style QML : {e}", "Top'Eau", Qgis.Warning)

                qml_hauteur = os.path.join(params.qml_path, 'style_hauteureau.qml') # ajout d'un fichier de style pour hauteur_eau
                try:
                    # chargement de la couche hauteur_eau depuis le GeoPackage
                    uri = f"{gpkg_path}|layername=hauteur_eau"
                    rHauteur = QgsVectorLayer(uri, 'hauteur_eau', 'ogr')
                    if not rHauteur.isValid():
                        raise ValueError(f"Impossible de charger {uri} comme QgsVectorLayer")

                    # enregistrement temporairement dans le projet (nécessaire pour saveStyleToDatabase)
                    proj = QgsProject.instance()
                    proj.addMapLayer(rHauteur, False)

                    # chargement du QML et application à la couche (pour être sûr que le style est valide)
                    rHauteur.loadNamedStyle(qml_hauteur)
                    rHauteur.triggerRepaint()

                    # sauvegarde dans la table layer_styles du GPKG
                    err = rHauteur.saveStyleToDatabase(
                        'default',  # nom du style
                        'Style embarqué',  # description
                        True,  # use as default
                        None  # on passe None : QGIS reprendra le style en mémoire
                    )
                    if err:
                        QgsMessageLog.logMessage(f"Erreur saveStyleToDatabase pour hauteur_eau : {err}", "Top'Eau",
                                                 Qgis.Warning)
                    else:
                        QgsMessageLog.logMessage(f"Symbologie embarquée dans hauteur_eau", "Top'Eau", Qgis.Info)

                    # nettoyage : retirer la couche du projet (on n’en a plus besoin)
                    proj.removeMapLayer(rHauteur.id())

                except Exception as e:
                    QgsMessageLog.logMessage(f"Échec injection style QML : {e}", "Top'Eau", Qgis.Warning)

                return gpkg_path
            else:
                QMessageBox.warning(self, "Erreur", f"Le GeoPackage n'a pas été créé")
                return None

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de la conversion en GeoPackage: {str(e)}", "Top'Eau",
                                     Qgis.Critical)
            QMessageBox.warning(self, "Erreur GDAL", f"Erreur lors de la conversion en GeoPackage:\n{str(e)}")
            return None

    except Exception as e:
        QgsMessageLog.logMessage(f"Erreur ajout raster au GPKG : {str(e)}", "Top'Eau", Qgis.Critical)
        return False
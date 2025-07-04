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

# import librairies nécessaires à la datavisualisation
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# appel emplacement des fichiers de stockage des sorties temporaires -- temp
temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")

# lien entre traitement.py et traitement.ui
ui_path = os.path.dirname(os.path.abspath(__file__))
ui_path = os.path.join(ui_path, "ui")
form_traitement, _ = uic.loadUiType(os.path.join(ui_path, "visu.ui"))


# mise en place de la classe VisuWidget
# va regrouper l'ensemble des fonctions relatives aux traitements à réaliser
class VisuWidget(QDialog, form_traitement):
    def __init__(self, iface):
        QDialog.__init__(self)

        # création de l'interface de la fenêtre QGIS
        self.setupUi(self)
        # ajustement de la taille de la fenêtre pour qu'elle soit fixe
        #self.setFixedSize(600, 400)
        # nom donné à la fenêtre
        self.setWindowTitle("Top'Eau - Visualisation des statistiques liées aux données eau")

        # Bouton "OK / Annuler"
        self.terminer.rejected.connect(self.reject)

        # Bouton "Visualiser les déciles"
        #self.visuDeciles.clicked.connect(self)

        layout = self.findChild(QVBoxLayout, 'layoutGraph')
        self.canvas = FigureCanvas(Figure())
        layout.addWidget(self.canvas)

    def reject(self):
        QDialog.reject(self)
        return

    def creer_graphique(self):

        donnees_input = self.inputGPKG.filePath()
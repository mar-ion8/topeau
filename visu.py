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

# import librairies nécessaires à la datavisualisation
import seaborn as sns
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from . import params
from . import query
from . import traitement

class VisuWindow(QDialog, params.form_graph):
    def __init__(self, parent_widget=None):
        QDialog.__init__(self)

        # Stocker la référence au widget parent qui contient les déciles
        self.parent_widget = parent_widget

        # création de l'interface de la fenêtre QGIS
        self.setupUi(self)
        # ajustement de la taille de la fenêtre pour qu'elle soit fixe
        #self.setFixedSize(600, 400)

        # nom donné à la fenêtre
        self.setWindowTitle("Top'Eau - Visualisation des statistiques liées aux données eau")

        # Bouton "OK / Annuler"
        self.terminer.rejected.connect(self.reject)

        # connexion de la barre de progression
        self.progressBar.setValue(0)

        # Bouton "Visualiser les déciles" - passer l'instance qui contient les déciles
        self.visuDeciles.clicked.connect(self.creer_graphique_deciles)

        # Bouton "Visualiser les déciles" - passer l'instance qui contient les déciles
        self.visuSurface.clicked.connect(self.creer_graphique_surface)

        # instauration de variables relatives à la création de l'interface graphiques
        layout = self.findChild(QVBoxLayout, 'layoutGraph')
        self.canvas = FigureCanvas(Figure())
        layout.addWidget(self.canvas)

    def creer_graphique_deciles(self):

        # récupération des attributs parents
        if (self.parent_widget and
                hasattr(self.parent_widget, 'deciles_calcules') and
                self.parent_widget.deciles_calcules):

            deciles_dict = self.parent_widget.deciles_calcules

            # extraction des valeurs des déciles
            valeurs_deciles = []
            for i in range(10, 100, 10):
                key = f'decile_{i}'
                if key in deciles_dict:
                    valeurs_deciles.append(deciles_dict[key])

                    # connexion de la barre de progression
                    self.progressBar.setValue(50)

                else:
                    valeurs_deciles.append(0)

            # création du graphique avec matplotlib
            df = pd.DataFrame({
                'Décile': [f'D{i}' for i in range(1, 10)],
                'Valeur': valeurs_deciles
            })

            fig, ax = plt.subplots(figsize=(5, 3))
            sns.barplot(data=df, x='Décile', y='Valeur', ax=ax)
            ax.set_title('Distribution des déciles pour la zone d\'étude')
            ax.set_xlabel('Déciles')
            ax.set_ylabel('Valeur (m)')

            self.canvas.figure = fig
            self.canvas.draw()

            # connexion de la barre de progression
            self.progressBar.setValue(100)

            QgsMessageLog.logMessage("Graphique des déciles créé avec succès", "Top'Eau", Qgis.Info)
        else:
            QgsMessageLog.logMessage("Aucun décile calculé disponible", "Top'Eau", Qgis.Warning)

    def creer_graphique_surface(self):

        # récupération des attributs parents
        if (self.parent_widget and
                hasattr(self.parent_widget, 'surface_hauteur') and
                self.parent_widget.surface_hauteur)  :

            if (self.parent_widget and
                    hasattr(self.parent_widget, 'niveaueau_hauteur') and
                    self.parent_widget.niveaueau_hauteur) :

                if (self.parent_widget and
                        hasattr(self.parent_widget, 'surface_zoneetude') and
                        self.parent_widget.surface_zoneetude):

                    surface = self.parent_widget.surface_hauteur
                    niveau_eau = self.parent_widget.niveaueau_hauteur
                    surfaceze = self.parent_widget.surface_zoneetude

                    # création du graphique avec matplotlib
                    df = pd.DataFrame({
                        'Niveau d\'eau' : niveau_eau,
                        'Surface': surface,
                        'Surface de la zone d\'étude' : surfaceze
                    })

                    fig, ax1 = plt.subplots(figsize=(4, 2))

                    # attribution valeurs ordonnées gauche
                    ax1.set_xlabel('Niveau d\'eau (m)')
                    ax1.set_ylabel('Surface (m²)')
                    sns.lineplot(data=df, x='Niveau d\'eau', y='Surface', ax=ax1)
                    ax1.tick_params(axis='y')

                    # attribution valuers ordonnées droite
                    ax2 = ax1.twinx()
                    ax2.set_ylabel('Surface de la zone d\'étude (m²)')
                    sns.lineplot(data=df, x='Niveau d\'eau', y='Surface de la zone d\'étude', ax=ax2)
                    ax2.tick_params(axis='y')

                    # titre
                    fig.suptitle('Répartition des surfaces pour la zone d\'étude')
                    # ajustement de la mise en page
                    fig.tight_layout()

                    self.canvas.figure = fig
                    self.canvas.draw()

                    # connexion de la barre de progression
                    self.progressBar.setValue(100)

                    QgsMessageLog.logMessage("Graphique des surfaces créé avec succès", "Top'Eau", Qgis.Info)
        else:
            QgsMessageLog.logMessage("Aucune donnée récupérée depuis le GPKG disponible", "Top'Eau", Qgis.Warning)
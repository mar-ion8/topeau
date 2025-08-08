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

        self.setupUi(self) # création de l'interface de la fenêtre QGIS
        self.setWindowTitle("Top'Eau - Visualisation des statistiques liées aux données eau") # nom donné à la fenêtre
        self.terminer.rejected.connect(self.reject) # bouton "OK / Annuler"
        self.progressBar.setValue(0) # connexion de la barre de progression

        # boutons de visualisation
        self.visuDeciles.clicked.connect(self.creer_graphique_deciles)
        self.visuSurface.clicked.connect(self.creer_graphique_surface)
        self.visuSurface_2.clicked.connect(self.creer_graphique_sommesurface)
        # bouton d'export
        self.exportGraph.clicked.connect(self.export_current_graph)

        # instauration de variables relatives à la création de l'interface graphique
        layout = self.findChild(QVBoxLayout, 'layoutGraph')
        self.canvas = FigureCanvas(Figure())
        layout.addWidget(self.canvas)

        self.current_figure = None # variable pour stocker la figure courante

    # fonction permettant la création du graphique des déciles
    def creer_graphique_deciles(self):
        # récupération des attributs parents
        if (self.parent_widget and
                hasattr(self.parent_widget, 'deciles_calcules') and
                self.parent_widget.deciles_calcules):
            deciles_dict = self.parent_widget.deciles_calcules

            valeurs_deciles = [] # extraction des valeurs des déciles
            for i in range(10, 100, 10):
                key = f'decile_{i}'
                if key in deciles_dict:
                    valeurs_deciles.append(deciles_dict[key])
                    self.progressBar.setValue(50) # maj de la barre de progression
                else:
                    valeurs_deciles.append(0)

            # création d'un dataframe avec pandas pour faciliter la création du graphique
            df = pd.DataFrame({
                'Décile': [f'D{i}' for i in range(1, 10)],
                'Valeur': valeurs_deciles
            })

            self.canvas.figure.clear() # nettoyage de l'interface s'il y a déjà une figure

            # création d'une nouvelle figure
            fig = Figure(figsize=(6, 4))
            ax = fig.add_subplot(111)

            ax.bar(df['Décile'], df['Valeur']) # récupération des valerus stockées dans le dataframe
            fig.suptitle('Distribution des déciles pour la zone d\'étude') # titre de la figure
            ax.set_xlabel('Déciles') # association du df aux abscisses
            ax.set_ylabel('Valeur (m)') # association du df aux ordonnées

            if valeurs_deciles: # zoom sur le haut des barres pour plus de détail
                min_val = min([v for v in valeurs_deciles if v > 0])
                max_val = max(valeurs_deciles)
                margin = (max_val - min_val) * 0.1  # 10% de marge
                ax.set_ylim(min_val - margin, max_val + margin)

            self.canvas.figure = fig # association du graph créé à l'interface de visualisation
            self.canvas.draw() # affichage du graph sur l'interface
            self.current_figure = fig  # stockage de la figure courante

            self.progressBar.setValue(100) # maj de la barre de progression

            QgsMessageLog.logMessage("Graphique des déciles créé avec succès", "Top'Eau", Qgis.Info)
        else:
            QgsMessageLog.logMessage("Aucun décile calculé disponible", "Top'Eau", Qgis.Warning)

    # fonction créant le graphique de visualisation de la surface de chaque niveau d'eau par rapport à la surf totale
    def creer_graphique_surface(self):

        # récupération des attributs parents
        if (self.parent_widget and
                hasattr(self.parent_widget, 'surface_hauteur') and
                self.parent_widget.surface_hauteur and
                hasattr(self.parent_widget, 'niveaueau_hauteur') and
                self.parent_widget.niveaueau_hauteur and
                hasattr(self.parent_widget, 'surface_zoneetude') and
                self.parent_widget.surface_zoneetude):

            surface = self.parent_widget.surface_hauteur
            niveau_eau = self.parent_widget.niveaueau_hauteur
            surfaceze = self.parent_widget.surface_zoneetude

            # vérif si surfaceze est une valeur unique ou une liste
            if isinstance(surfaceze, (int, float)):
                surface_totale = surfaceze
            else:
                surface_totale = surfaceze[0] if surfaceze else 1 # on prend la première valeur si c'est une liste

            self.canvas.figure.clear() # nettoyage de l'interface s'il y a déjà une figure

            # création d'une nouvelle figure
            fig = Figure(figsize=(6, 4))
            ax1 = fig.add_subplot(111)

            # association des valeurs aux abscisses et aux ordonnées principales
            ax1.plot(niveau_eau, surface, color='tab:blue', linewidth=2, marker='o', markersize=3)
            ax1.set_xlabel('Niveau d\'eau (m)')
            ax1.set_ylabel('Surface inondée (m²)', color='tab:blue')
            ax1.tick_params(axis='y', labelcolor='tab:blue')

            # association des valeurs à l'axe Y2 (droite) : échelle en pourcentage basée sur la surface totale de la ze
            ax2 = ax1.twinx()
            ax2.set_ylabel('Pourcentage de la surface totale (%)', color='tab:red')
            # calcul les pourcentages réels pour chaque niveau d'eau
            pourcentages_reels = [(s / surface_totale * 100) for s in surface]
            # définition des limites de l'axe Y2 basées sur les pourcentages réels
            pourcentage_min = min(pourcentages_reels)
            pourcentage_max = max(pourcentages_reels)

            # ajout d'une marge de 5% pour garder une certaine lisibilité
            marge = (pourcentage_max - pourcentage_min) * 0.05
            ax2.set_ylim(max(0, pourcentage_min - marge), min(100, pourcentage_max + marge))
            # graduation pour les pourcentages
            if pourcentage_max <= 25:
                ticks = [0, 5, 10, 15, 20, 25]
            elif pourcentage_max <= 50:
                ticks = [0, 10, 20, 30, 40, 50]
            elif pourcentage_max <= 75:
                ticks = [0, 25, 50, 75]
            else:
                ticks = [0, 25, 50, 75, 100]
            # filtre sur les graduations pour ne garder que celles dans la plage visible
            ticks_visibles = [t for t in ticks if ax2.get_ylim()[0] <= t <= ax2.get_ylim()[1]]
            ax2.set_yticks(ticks_visibles)
            ax2.tick_params(axis='y', labelcolor='tab:red')

            fig.suptitle('Surface inondée par niveau d\'eau') # ajout d'un titre au graphique
            fig.tight_layout()

            self.canvas.figure = fig
            self.canvas.draw()
            self.current_figure = fig

            self.progressBar.setValue(100)

            QgsMessageLog.logMessage("Graphique des surfaces créé avec succès", "Top'Eau", Qgis.Info)
        else:
            QgsMessageLog.logMessage("Aucune donnée récupérée depuis le GPKG disponible", "Top'Eau", Qgis.Warning)

    # fonction créant le graphique de visualisation de la somme des surfaces sup à 10cm de chaque niveau d'eau/à la surf totale
    def creer_graphique_sommesurface(self):

        # récupération des attributs parents
        if (self.parent_widget and
                hasattr(self.parent_widget, 'sommesurf_hauteur') and
                self.parent_widget.sommesurf_hauteur and
                hasattr(self.parent_widget, 'niveaueau_hauteur') and
                self.parent_widget.niveaueau_hauteur and
                hasattr(self.parent_widget, 'surface_zoneetude') and
                self.parent_widget.surface_zoneetude):

            somme_surfaces = self.parent_widget.sommesurf_hauteur
            niveau_eau = self.parent_widget.niveaueau_hauteur
            surfaceze = self.parent_widget.surface_zoneetude

            # vérif si surfaceze est une valeur unique ou une liste
            if isinstance(surfaceze, (int, float)):
                surface_totale = surfaceze
            else:
                surface_totale = surfaceze[0] if surfaceze else 1

            self.canvas.figure.clear() # nettoyage de l'interface s'il y a déjà un graphique

            # création d'une nouvelle figure
            fig = Figure(figsize=(6, 4))
            ax1 = fig.add_subplot(111)

            # association des valeurs aux abscisses et aux ordonnées principales
            ax1.plot(niveau_eau, somme_surfaces, color='tab:blue', linewidth=2, marker='o', markersize=3)
            ax1.set_xlabel('Niveau d\'eau (m)')
            ax1.set_ylabel('Surface > 10cm (m²)', color='tab:blue')
            ax1.tick_params(axis='y', labelcolor='tab:blue')

            # association des valeurs à l'axe Y2 (droite) : échelle en pourcentage basée sur la surface totale de la ze
            ax2 = ax1.twinx()
            ax2.set_ylabel('Pourcentage de la surface totale (%)', color='tab:red')
            # calcul des pourcentages réels pour chaque point
            pourcentages_reels = [(s / surface_totale * 100) for s in somme_surfaces]
            # définition des limites de l'axe Y2 basées sur les pourcentages réels
            pourcentage_min = min(pourcentages_reels)
            pourcentage_max = max(pourcentages_reels)
            # ajout d'une marge de 5% pour garder une certaine lisibilité
            marge = (pourcentage_max - pourcentage_min) * 0.05
            ax2.set_ylim(max(0, pourcentage_min - marge), min(100, pourcentage_max + marge))

            # graduations pour les pourcentages
            if pourcentage_max <= 25:
                ticks = [0, 5, 10, 15, 20, 25]
            elif pourcentage_max <= 50:
                ticks = [0, 10, 20, 30, 40, 50]
            elif pourcentage_max <= 75:
                ticks = [0, 25, 50, 75]
            else:
                ticks = [0, 25, 50, 75, 100]

            # filtre sur les graduations pour ne garder que ceux dans la plage visible
            ticks_visibles = [t for t in ticks if ax2.get_ylim()[0] <= t <= ax2.get_ylim()[1]]
            ax2.set_yticks(ticks_visibles)
            ax2.tick_params(axis='y', labelcolor='tab:red')

            fig.suptitle('Surface > 10cm par niveau d\'eau') # ajout d'un titre
            fig.tight_layout()

            self.canvas.figure = fig
            self.canvas.draw()
            self.current_figure = fig

            self.progressBar.setValue(100)

            QgsMessageLog.logMessage("Graphique des surfaces > 10cm créé avec succès", "Top'Eau", Qgis.Info)
        else:
            QgsMessageLog.logMessage("Aucune donnée récupérée depuis le GPKG disponible", "Top'Eau", Qgis.Warning)

    # fonction gérant l'export des graphiques
    def export_current_graph(self):

        if self.current_figure is None: # vérification de la validité du graphique
            QMessageBox.warning(self, "Attention", "Aucun graphique à exporter. Veuillez d'abord créer un graphique.")
            return

        try:
            output_path, selected_filter = QFileDialog.getSaveFileName(
                self,
                "Exporter le graphique",
                "",
                "PNG files (*.png);;PDF files (*.pdf);;SVG files (*.svg)"
            ) # ouverture de l'explorateur de fichier pour choisir le fichier de sortie avec différents formats

            if output_path: # détermine le format selon l'extension ou le filtre

                if not any(output_path.lower().endswith(ext) for ext in ['.png', '.pdf', '.svg']):
                    # ajout l'extension selon le filtre sélectionné
                    if "PNG" in selected_filter:
                        output_path += ".png"
                    elif "PDF" in selected_filter:
                        output_path += ".pdf"
                    elif "SVG" in selected_filter:
                        output_path += ".svg"
                # export de la figure courante
                dpi = 300 if output_path.lower().endswith('.png') else None
                self.current_figure.savefig(output_path, dpi=dpi, bbox_inches='tight',
                                            facecolor='white', edgecolor='none')

                QMessageBox.information(self, "Export réussi", f"Graphique exporté vers :\n{output_path}")

                QgsMessageLog.logMessage(f"Graphique exporté avec succès : {output_path}", "Top'Eau", Qgis.Info)

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur lors de l'export : {str(e)}", "Top'Eau", Qgis.Critical)
            QMessageBox.critical(self, "Erreur lors de l'export", f"Impossible d'exporter le graphique :\n{str(e)}")
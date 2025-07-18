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

# appel emplacement des fichiers de stockage des sorties temporaires -- style et temp
temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
qml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style")

# lien entre traitement.py et visu.ui
ui_path = os.path.dirname(os.path.abspath(__file__))
ui_path = os.path.join(ui_path, "ui")
form_traitement, _ = uic.loadUiType(os.path.join(ui_path, "traitement.ui"))
form_graph, _ = uic.loadUiType(os.path.join(ui_path, "visu.ui"))
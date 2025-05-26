#import des librairies QTDesigner pour pouvoir afficher correctement l'interface du Plugin
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5 import uic
from PyQt5.QtSql import *

#import des librairies QGIS
from qgis.core import *
from qgis.gui import *

import os

ui_path = os.path.dirname(os.path.abspath(__file__))
ui_path = os.path.join(ui_path, "ui")
form_about, _ = uic.loadUiType(os.path.join(ui_path, "a_propos.ui"))

class AboutWidget(QDialog, form_about):

   def __init__(self, interface):
       self.interface = interface
       QWidget.__init__(self)
       self.setupUi(self)  # méthode pour construire les widgets
       self.setWindowTitle("Top'Eau")
       self.fermer.clicked.connect(self.quitter)

   def quitter(self):
       self.close()

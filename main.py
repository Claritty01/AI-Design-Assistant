# main.py
from PyQt5.QtWidgets import QApplication
from ui_layout import ChatWindow
import sys

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ChatWindow()
    window.show()
    sys.exit(app.exec_())

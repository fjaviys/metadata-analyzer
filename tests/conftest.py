import os
import sys

# Hacer importable shared/python en los tests sin instalar el paquete.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared", "python"))

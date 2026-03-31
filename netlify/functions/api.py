"""
Ghost AI System — Netlify Function Handler
Wraps the FastAPI app using mangum for AWS Lambda / Netlify Functions compatibility.
"""
import sys
import os

# Ensure the robin root is on the path so ghost_api imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from mangum import Mangum
from ghost_api import app

handler = Mangum(app, lifespan="off")

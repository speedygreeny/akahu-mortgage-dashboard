from asgiref.wsgi import WsgiToAsgi

# Import the Flask app instance
from .app import app as flask_app

# Wrap the WSGI Flask app as an ASGI app
asgi_app = WsgiToAsgi(flask_app)

__all__ = ["asgi_app"]

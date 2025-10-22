import os
import logging
from flask import Flask
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__)
    app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev_secret_key_change_in_production')
    
    # Register API routes
    from app.routes.api_routes import api_bp
    app.register_blueprint(api_bp)
    
    logging.info("✅ Flask app created successfully")
    
    return app

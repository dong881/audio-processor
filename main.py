import os
import logging
from app import create_app
from app.services.audio_processor import AudioProcessor

def initialize_processor():
    """Initialize AudioProcessor"""
    try:
        credentials_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials")
        if not os.path.exists(credentials_dir):
            os.makedirs(credentials_dir)
            logging.info(f"✅ Created credentials directory: {credentials_dir}")
        
        processor = AudioProcessor(max_workers=3)
        logging.info("✅ AudioProcessor initialized successfully")
        return processor
    except Exception as e:
        logging.error(f"❌ AudioProcessor initialization failed: {str(e)}")
        processor = AudioProcessor(max_workers=1)
        processor.drive_service = None
        return processor

# Initialize AudioProcessor (global instance)
processor = initialize_processor()

# Create Flask app
app = create_app()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    
    logging.info(f"🚀 Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)

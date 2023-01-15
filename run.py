import os

from dotenv import load_dotenv

if os.getenv("FLASK_DEBUG"):
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env_debug'), override=True)
else:
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from sandik.app import create_app

app = create_app()
if __name__ == '__main__':
    app.run(debug=True)

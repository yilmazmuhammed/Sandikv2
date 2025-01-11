import os
import sys

from dotenv import load_dotenv

sys.path.append(os.path.dirname(__file__))

if os.getenv("FLASK_DEBUG"):
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env_debug'), override=True)
else:
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from sandik.app import create_app

os.environ["SANDIKv2_PROJECT_DIRECTORY"] = os.path.dirname(__file__)

app = create_app()
if __name__ == '__main__':
    app.run(debug=True)

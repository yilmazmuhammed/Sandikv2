import os

from flask import Flask
from pony.flask import Pony

from flask_heroku_template.blueprint_template.api import blueprint_template_api_bp
from flask_heroku_template.blueprint_template.page import blueprint_template_page_bp
from flask_heroku_template.utils import CustomJSONEncoder

app = Flask(
    __name__, instance_relative_config=True,
    template_folder='utils/templates', static_folder='utils/static', static_url_path='/assets'
)
app.secret_key = os.getenv("SECRET_KEY")
app.json_encoder = CustomJSONEncoder

Pony(app)

app.register_blueprint(blueprint_template_api_bp, url_prefix="/api/blueprint_template")
app.register_blueprint(blueprint_template_page_bp, url_prefix="/blueprint_template")


if __name__ == '__main__':
    app.run(debug=True)

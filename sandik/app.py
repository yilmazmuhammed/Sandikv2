import os

from flask import Flask, flash
from flask_jsglue import JSGlue
from pony.flask import Pony

from sandik.auth.page import auth_page_bp
from sandik.auth.utils import setup_login_manager
from sandik.general.page import general_page_bp
from sandik.sandik.api import sandik_api_bp
from sandik.sandik.page import sandik_page_bp
from sandik.transaction.page import transaction_page_bp
from sandik.utils import CustomJSONEncoder, sandik_preferences
from sandik.utils.db_models import MoneyTransaction, Installment, Contribution, SandikRule


def initialize_flask() -> Flask:
    flask_app = Flask(
        __name__, instance_relative_config=True,
        template_folder='utils/templates', static_folder='utils/static', static_url_path='/assets'
    )
    flask_app.secret_key = os.getenv("SECRET_KEY")
    flask_app.json_encoder = CustomJSONEncoder
    return flask_app


def initialize_database(flask_app):
    return Pony(flask_app)


def initialize_login_manager(flask_app):
    return setup_login_manager(flask_app)


def initialize_flask_js_glue(flask_app):
    return JSGlue(flask_app)


def register_blueprints(flask_app):
    flask_app.register_blueprint(general_page_bp, url_prefix="/")
    flask_app.register_blueprint(auth_page_bp, url_prefix="/")
    flask_app.register_blueprint(sandik_page_bp, url_prefix="/sandik/")
    flask_app.register_blueprint(sandik_api_bp, url_prefix="/api/sandik/")
    flask_app.register_blueprint(transaction_page_bp, url_prefix="/sandik/<int:sandik_id>/")
    return flask_app


def catch_exception(func, default_value, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        # flash(str(e), "danger") # BUG: Bir soraki sayfada gösteriliyor
        return default_value


def jinja2_integration(flask_app):
    flask_app.jinja_env.globals.update(MoneyTransaction=MoneyTransaction)
    flask_app.jinja_env.globals.update(isinstance=isinstance)
    flask_app.jinja_env.globals.update(Installment=Installment)
    flask_app.jinja_env.globals.update(Contribution=Contribution)
    flask_app.jinja_env.globals.update(sandik_preferences=sandik_preferences)
    flask_app.jinja_env.globals.update(SandikRule=SandikRule)
    flask_app.jinja_env.globals.update(catch_exception=catch_exception)


def create_app() -> Flask:
    flask_app = initialize_flask()
    initialize_database(flask_app)
    initialize_login_manager(flask_app)
    initialize_flask_js_glue(flask_app)
    jinja2_integration(flask_app)
    register_blueprints(flask_app)
    return flask_app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)

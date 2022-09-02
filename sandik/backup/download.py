from datetime import datetime

from flask import Blueprint, json
from werkzeug import Response

from sandik.auth.requirement import admin_required
from sandik.backup import utils

backup_dw_bp = Blueprint(
    'backup_dw_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@backup_dw_bp.route("/site-yedegi")
@admin_required
def download_backup_page():
    backup_data = utils.backup_database()
    response = Response(json.dumps(backup_data, indent=4), mimetype='text/json')
    time_string = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"sandikv2_site_yedegi_{time_string}.json"
    response.headers.set("Content-Disposition", "attachment", filename=filename)
    return response

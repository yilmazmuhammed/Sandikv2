from datetime import datetime

from flask import Blueprint, json, flash, render_template
from flask_login import current_user, login_user
from werkzeug import Response

from sandik.auth import db as auth_db
from sandik.auth.requirement import admin_required
from sandik.backup import utils, forms
from sandik.utils.forms import FormPI

backup_page_bp = Blueprint(
    'backup_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@backup_page_bp.route("/indir")
@admin_required
def download_backup_page():
    backup_data = utils.backup_database()
    response = Response(json.dumps(backup_data, indent=4), mimetype='text/json')
    time_string = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"sandikv2_site_yedegi_{time_string}.json"
    response.headers.set("Content-Disposition", "attachment", filename=filename)
    return response


@backup_page_bp.route("/geri-yukle", methods=["GET", "POST"])
@admin_required
def restore_backup_page():
    form = forms.RestoreBackupForm()
    print(1)
    print(form.backup_file.data)
    if form.validate_on_submit():
        print(2)
        try:
            if not form.backup_file.data:
                raise Exception("Yedek dosyası yüklenemedi. Lütfen json formatındaki yedek dosyasını yükleyiniz.")

            backup_data = json.loads(form.backup_file.data.read().decode("utf-8"))
            current_user_email_address = current_user.to_dict()["email_address"]
            utils.restore_database(backup_data=backup_data)
            login_user(auth_db.get_web_user(email_address=current_user_email_address))
        except Exception as e:
            flash(str(e), "danger")
            raise(e)

    print(3)
    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Site yedeğini yükle", form=form, active_dropdown="backup"))

from flask import Blueprint, json, flash, render_template
from flask_login import current_user, login_user

from sandik.auth import db as auth_db
from sandik.auth.requirement import admin_required
from sandik.backup import utils, forms
from sandik.utils.forms import FormPI

backup_page_bp = Blueprint(
    'backup_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@backup_page_bp.route("/geri-yukle", methods=["GET", "POST"])
@admin_required
def restore_backup_page():
    form = forms.RestoreBackupForm()
    print(form.backup_file.data)
    if form.validate_on_submit():
        try:
            if not form.backup_file.data:
                raise Exception("Yedek dosyası okunamadı. Lütfen json formatındaki yedek dosyasını yükleyiniz.")

            backup_data = json.loads(form.backup_file.data.read().decode("utf-8"))
            current_user_email_address = current_user.to_dict()["email_address"]
            utils.restore_database(backup_data=backup_data)
            login_user(auth_db.get_web_user(email_address=current_user_email_address))
        except Exception as e:
            flash(str(e), "danger")
            raise e

    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Site yedeğini yükle", form=form, active_dropdown="backup"))


@backup_page_bp.route("/sandikv1-den-yukle", methods=["GET", "POST"])
@admin_required
def create_sandik_from_sandikv1_data_page():
    form = forms.RestoreBackupForm(form_title="Sandıkv1 verisinden sandık oluştur")

    if form.validate_on_submit():
        try:
            if not form.backup_file.data:
                raise Exception("Yedek dosyası okunamadı. Lütfen json formatındaki yedek dosyasını yükleyiniz.")

            backup_data = json.loads(form.backup_file.data.read().decode("utf-8"))
            utils.create_sandik_from_sandikv1_data(data=backup_data, created_by=current_user)
        except Exception as e:
            flash(str(e), "danger")
            raise e

    return render_template(
        "utils/form_layout.html",
        page_info=FormPI(title="Sandıkv1 verisinden sandık oluştur", form=form, active_dropdown="backup")
    )

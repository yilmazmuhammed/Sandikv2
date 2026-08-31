from flask import Blueprint, json, flash, render_template
from flask_login import current_user, login_user
from pony.orm import rollback

from sandik.auth import db as auth_db
from sandik.auth.requirement import admin_required
from sandik.backup import utils, forms
from sandik.backup.exceptions import InconsistentBackupData
from sandik.utils.forms import FormPI

backup_page_bp = Blueprint(
    'backup_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@backup_page_bp.route("/geri-yukle", methods=["GET", "POST"])
@admin_required
def restore_backup_page():
    form = forms.RestoreBackupForm()

    if form.validate_on_submit():
        try:
            if not form.backup_file.data:
                raise Exception("Yedek dosyası okunamadı. Lütfen json formatındaki yedek dosyasını yükleyiniz.")

            backup_data = json.loads(form.backup_file.data.read().decode("utf-8"))
            current_user_email_address = current_user.to_dict()["email_address"]
            utils.restore_database(backup_data=backup_data)
            login_user(auth_db.get_web_user(email_address=current_user_email_address))

            flash("Yedek geri yüklendi.", "success")
        except InconsistentBackupData as e:
            # Geri yükleme mevcut verileri silerek başlar; tutarsızlık tespit edildiğinde
            # işlemin geri alınması şarttır, aksi halde veritabanı yarım kalmış olur.
            rollback()
            flash(str(e), "danger")
            for inconsistency in e.inconsistencies:
                flash(inconsistency, "danger")
        except Exception as e:
            rollback()
            flash(str(e), "danger")
            raise e

    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Site yedeğini yükle", form=form, active_dropdown="backup"))

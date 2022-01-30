from flask import Blueprint, render_template, request, redirect, flash, url_for, g
from flask_login import current_user

from sandik.auth.requirement import login_required
from sandik.general import forms, db
from sandik.general.exceptions import BankAccountException
from sandik.general.requirement import notification_required
from sandik.sandik import db as sandik_db
from sandik.utils import LayoutPI, get_next_url
from sandik.utils.forms import flask_form_to_dict, FormPI

general_page_bp = Blueprint(
    'general_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@general_page_bp.route("/")
@login_required
def index_page():
    return render_template("utils/layout.html", page_info=LayoutPI(title="Ana sayfa"))


@login_required
@general_page_bp.route("/banka-hesabi-ekle", methods=["GET", "POST"])
def create_bank_account_page():
    form = forms.BankAccountForm()

    if form.validate_on_submit():
        form_data = flask_form_to_dict(request_form=request.form, boolean_fields=["is_primary"])
        print(form_data)
        if request.args.get("sandik"):
            # TODO
            sandik = sandik_db.get_sandik(id=request.args.get("sandik"))
            if not sandik:
                flash("Sandık bulunamadı.", "danger")
                return render_template(
                    "utils/form_layout.html",
                    page_info=FormPI(title="Üyelik başvurusu yap", form=form, active_dropdown='sandik')
                )
            form_data["sandik_ref"] = sandik
        else:
            form_data["web_user_ref"] = current_user
        try:
            db.create_bank_account(created_by=current_user, **form_data)

            next_url = get_next_url(request.args, default_url=url_for("general_page_bp.index_page"))
            return redirect(next_url)
        except BankAccountException as e:
            flash(str(e), "danger")

    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Üyelik başvurusu yap", form=form, active_dropdown='sandik'))


@general_page_bp.route("/bildirim/<int:notification_id>")
@login_required
@notification_required
def read_notification_page(notification_id):
    db.read_notification(notification=g.notification)
    if g.notification.url:
        return redirect(g.notification.url)
    else:
        return redirect(request.referrer)


@general_page_bp.route("/bildirimler")
@login_required
def notifications_page():
    return render_template("general/notifications_page.html",
                           page_info=LayoutPI(title="Bildirimler"))

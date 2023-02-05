from datetime import datetime

from flask import Blueprint, request, render_template, redirect, url_for, g
from flask_login import current_user

from sandik.auth import db as auth_db
from sandik.auth.requirement import admin_required
from sandik.utils import LayoutPI
from sandik.utils.db_models import get_paging_variables
from sandik.utils.forms import flask_form_to_dict, FormPI
from sandik.utils.requirement import paging_must_be_verified
from sandik.website_transaction import forms, db
from sandik.website_transaction.authorization import website_transaction_required

website_transaction_page_bp = Blueprint(
    'website_transaction_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@website_transaction_page_bp.route('islem-ekle', methods=["GET", "POST"])
@admin_required
def add_website_transaction_page():
    form = forms.WebsiteTransactionForm(categories=db.get_categories(), form_title="Websitesi Masraf İşlemi Ekle ")

    if form.validate_on_submit():
        form_data = flask_form_to_dict(request_form=request.form, exclude=["category_list", "web_user"])
        try:
            web_user = auth_db.get_web_user(id=form.web_user.data) if form.web_user.data.isnumeric() else None

            website_transaction = db.create_website_transaction(web_user_ref=web_user, **form_data,
                                                                created_by=current_user)
            return redirect(url_for("website_transaction_page_bp.add_website_transaction_page"))
        except Exception as e:
            raise e
            rollback()
            flash(str(e), "danger")
    elif not form.is_submitted():
        form.date.data = datetime.today()

    return render_template("website_transaction/add_website_transaction_page.html",
                           page_info=FormPI(title="Websitesi Masraf İşlemi Ekle", form=form,
                                            active_dropdown="website-transactions"))


@website_transaction_page_bp.route('websitesi-masraflari')
@paging_must_be_verified(default_page_num=1, default_page_size=50)
def website_transactions_of_sandik_page():
    g.total_count, g.page_count, g.first_index, g.website_transactions = get_paging_variables(
        entities_query=db.select_website_transactions(), page_size=g.page_size, page_num=g.page_num
    )
    g.sum_of_transactions = db.sum_of_website_transactions()

    return render_template("website_transaction/website_transactions_page.html",
                           page_info=LayoutPI(title="Websitesi masrafları", active_dropdown="website-transactions"))


@website_transaction_page_bp.route("wt-<int:website_transaction_id>/sil")
@admin_required
@website_transaction_required
def delete_website_transaction_page(website_transaction_id):
    db.delete_website_transaction(website_transaction=g.website_transaction, deleted_by=current_user)
    return redirect(request.referrer)

from flask import Blueprint, request, render_template, g, flash, url_for
from flask_login import current_user
from pony.orm import desc
from werkzeug.utils import redirect

from sandik.sandik import db as sandik_db
from sandik.sandik.exceptions import ThereIsNoMember
from sandik.sandik.requirement import sandik_authorization_required, member_required
from sandik.transaction import forms, utils
from sandik.transaction.exceptions import MaximumDebtAmountExceeded
from sandik.utils import LayoutPI
from sandik.utils.db_models import MoneyTransaction
from sandik.utils.forms import FormPI, flask_form_to_dict

transaction_page_bp = Blueprint(
    'transaction_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@transaction_page_bp.route('islem-ekle', methods=["GET", "POST"])
@sandik_authorization_required("write")
def add_money_transaction_by_manager_page(sandik_id):
    form = forms.MoneyTransactionForm(sandik=g.sandik, form_title="Para giriş/çıkışı")

    if form.validate_on_submit():
        print(request.form)
        form_data = flask_form_to_dict(request_form=request.form, exclude=["member"],
                                       boolean_fields=["use_untreated_amount", "pay_future_payments"])
        try:
            member = sandik_db.get_member(id=form.member.data)
            if not member:
                raise ThereIsNoMember("Üye açılan listeden seçilmelidir")

            if form.type.data == MoneyTransaction.TYPE.EXPENSE:
                max_amount = member.max_amount_can_borrow(use_untreated_amount=form_data["use_untreated_amount"])
                if form.amount.data > max_amount:
                    raise MaximumDebtAmountExceeded(f"Üye bu miktarı alamaz. En fazla {max_amount}₺ alabilir.")

            print(form_data)
            money_transaction = utils.add_money_transaction(
                member=member, creation_type=MoneyTransaction.CREATION_TYPE.BY_MANUEL,
                created_by=current_user, **form_data
            )
            print(money_transaction.to_dict())
            return redirect(url_for("transaction_page_bp.add_money_transaction_by_manager_page", sandik_id=sandik_id))
        except Exception as e:
            flash(str(e), "danger")

    return render_template("transaction/add_money_transaction_by_manager_page.html",
                           page_info=FormPI(title="Para giriş/çıkışı ekle", form=form, active_dropdown="transactions"))


@transaction_page_bp.route('butun-uyeler-icin-vadesi-gelmis-aidatlari-olustur', methods=["GET", "POST"])
@sandik_authorization_required("write")
def create_due_contributions_for_all_members_page(sandik_id):
    utils.create_due_contributions_for_all_members(sandik=g.sandik, created_by=current_user,
                                                   created_from="create_due_contributions_for_all_members_page")
    return redirect(request.referrer or url_for("sandik_page_bp.sandik_index_page", sandik_id=sandik_id))


@transaction_page_bp.route('sandik-para-giris-cikislari', methods=["GET", "POST"])
@sandik_authorization_required("read")
def money_transactions_of_sandik_page(sandik_id):
    g.money_transactions = g.sandik.get_money_transactions().order_by(lambda mt: desc(mt.id))
    return render_template("transaction/money_transactions_page.html",
                           page_info=LayoutPI(title="Para giriş/çıkış işlemleri", active_dropdown="transactions"))


@transaction_page_bp.route('uye-para-giris-cikislari', methods=["GET", "POST"])
@member_required
def money_transactions_of_member_page(sandik_id):
    g.money_transactions = g.member.money_transactions_set.order_by(lambda mt: desc(mt.id))
    return render_template(
        "transaction/money_transactions_page.html",
        page_info=LayoutPI(title="Para giriş/çıkış işlemlerim", active_dropdown="member-transactions")
    )

from flask import Blueprint, request, render_template, g, flash, url_for
from flask_login import current_user
from pony.orm import desc, rollback
from werkzeug.utils import redirect

from sandik.sandik import db as sandik_db
from sandik.sandik.exceptions import ThereIsNoMember, ThereIsNoShare
from sandik.sandik.requirement import sandik_authorization_required, member_required
from sandik.transaction import forms, utils
from sandik.transaction.exceptions import MaximumDebtAmountExceeded
from sandik.utils import LayoutPI
from sandik.utils.db_models import MoneyTransaction
from sandik.utils.forms import FormPI, flask_form_to_dict
from sandik.utils.period import NotValidPeriod

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

            if int(form.type.data) == MoneyTransaction.TYPE.EXPENSE:
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
        except MaximumDebtAmountExceeded as e:
            # rollback()
            flash(str(e), "danger")
        except Exception as e:
            raise e
            rollback()
            flash(str(e), "danger")

    return render_template("transaction/add_money_transaction_by_manager_page.html",
                           page_info=FormPI(title="Para giriş/çıkışı ekle", form=form,
                                            active_dropdown="management-transactions"))


@transaction_page_bp.route('aidat-ekle', methods=["GET", "POST"])
@sandik_authorization_required("write")
def add_custom_contribution_page(sandik_id):
    form = forms.ContributionForm(sandik=g.sandik)

    if form.validate_on_submit():
        try:
            member = sandik_db.get_member(id=form.member.data)
            if not member:
                raise ThereIsNoMember("Üye açılan listeden seçilmelidir.")

            share = sandik_db.get_share(id=form.share.data, member_ref=member)
            if not share:
                raise ThereIsNoShare("Hisse, üye seçildikten sonra gelen listeden seçilmelidir.")

            utils.add_custom_contribution(amount=form.amount.data, period=form.period.data, share=share,
                                          created_by=current_user)
            return redirect(url_for("transaction_page_bp.add_custom_contribution_page", sandik_id=sandik_id))
        except (ThereIsNoMember, ThereIsNoShare) as e:
            flash(str(e), "danger")
        except NotValidPeriod as e:
            flash(str(e), "danger")

    return render_template("transaction/add_custom_contribution_page.html",
                           page_info=FormPI(title="Manuel aidat ekle", form=form,
                                            active_dropdown="management-transactions"))


@transaction_page_bp.route('butun-uyeler-icin-vadesi-gelmis-aidatlari-olustur', methods=["GET", "POST"])
@sandik_authorization_required("write")
def create_due_contributions_for_all_members_page(sandik_id):
    utils.create_due_contributions_for_all_members(sandik=g.sandik, created_by=current_user,
                                                   created_from="create_due_contributions_for_all_members_page")
    return redirect(request.referrer or url_for("sandik_page_bp.sandik_index_page", sandik_id=sandik_id))


@transaction_page_bp.route('s-para-giris-cikislari')
@sandik_authorization_required("read")
def money_transactions_of_sandik_page(sandik_id):
    g.money_transactions = g.sandik.get_money_transactions().order_by(lambda mt: desc(mt.id))
    return render_template("transaction/money_transactions_page.html",
                           page_info=LayoutPI(title="Para giriş/çıkış işlemleri",
                                              active_dropdown="management-transactions"))


@transaction_page_bp.route('u-para-giris-cikislari')
@member_required
def money_transactions_of_member_page(sandik_id):
    g.money_transactions = g.member.money_transactions_set.order_by(lambda mt: desc(mt.id))
    return render_template(
        "transaction/money_transactions_page.html",
        page_info=LayoutPI(title="Para giriş/çıkış işlemlerim", active_dropdown="member-transactions")
    )


@transaction_page_bp.route('s-sandik-islemleri')
@sandik_authorization_required("read")
def transactions_of_sandik_page(sandik_id):
    print("sandik:", g.sandik)
    g.transactions = utils.get_transactions(whose=g.sandik)
    return render_template("transaction/sandik_transactions_page.html",
                           page_info=LayoutPI(title="Sandık işlemleri", active_dropdown="management-transactions"))


@transaction_page_bp.route('u-sandik-islemleri')
@member_required
def transactions_of_member_page(sandik_id):
    g.transactions = utils.get_transactions(whose=g.member)
    return render_template("transaction/sandik_transactions_page.html",
                           page_info=LayoutPI(title="Sandık işlemlerim", active_dropdown="member-transactions"))


@transaction_page_bp.route('s-odemeler')
@sandik_authorization_required("read")
def payments_of_sandik_page(sandik_id):
    g.payments = utils.get_payments(whose=g.sandik)
    g.due_and_unpaid_payments = utils.get_payments(whose=g.sandik, is_fully_paid=False, is_due=True)
    return render_template("transaction/payments_page.html",
                           page_info=LayoutPI(title="Sandıktaki ödemeler", active_dropdown="management-transactions"))


@transaction_page_bp.route('u-odemeler')
@member_required
def payments_of_member_page(sandik_id):
    g.payments = utils.get_payments(whose=g.member)
    g.due_and_unpaid_payments = utils.get_payments(whose=g.member, is_fully_paid=False, is_due=True)
    return render_template("transaction/payments_page.html",
                           page_info=LayoutPI(title="Ödemelerim", active_dropdown="member-transactions"))


@transaction_page_bp.route('s-borclar')
@sandik_authorization_required("read")
def debts_of_sandik_page(sandik_id):
    g.unpaid_debts = utils.get_debts(whose=g.sandik, only_unpaid=True)
    g.debts = utils.get_debts(whose=g.sandik)
    return render_template("transaction/debts_page.html",
                           page_info=LayoutPI(title="Sandıktaki borçlar", active_dropdown="management-transactions"))


@transaction_page_bp.route('u-borclar')
@member_required
def debts_of_member_page(sandik_id):
    g.unpaid_debts = utils.get_debts(whose=g.member, only_unpaid=True)
    g.debts = utils.get_debts(whose=g.member)
    return render_template("transaction/debts_page.html",
                           page_info=LayoutPI(title="Borçlarım", active_dropdown="member-transactions"))

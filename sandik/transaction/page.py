from flask import Blueprint, request, render_template, g, flash, url_for, abort
from flask_login import current_user
from pony.orm import desc, rollback
from werkzeug.utils import redirect

from sandik.sandik import db as sandik_db
from sandik.sandik.exceptions import ThereIsNoMember, ThereIsNoShare
from sandik.sandik.requirement import sandik_authorization_required, to_be_member_of_sandik_required
from sandik.transaction import forms, utils
from sandik.transaction.authorization import money_transaction_required, contribution_required
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
def add_custom_contribution_by_manager_page(sandik_id):
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
            return redirect(url_for("transaction_page_bp.add_custom_contribution_by_manager_page", sandik_id=sandik_id))
        except (ThereIsNoMember, ThereIsNoShare) as e:
            flash(str(e), "danger")
        except NotValidPeriod as e:
            flash(str(e), "danger")

    return render_template("transaction/add_custom_contribution_by_manager_page.html",
                           page_info=FormPI(title="Manuel aidat ekle", form=form,
                                            active_dropdown="management-transactions"))


@transaction_page_bp.route('mt-<int:money_transaction_id>/sil')
@sandik_authorization_required("write")
@money_transaction_required
def remove_money_transaction_by_manager_page(sandik_id, money_transaction_id):
    # TODO bu fonksiyonun içindeki flush'lar çok tehlikeli
    try:
        utils.remove_money_transaction(money_transaction=g.money_transaction, removed_by=current_user)
    except Exception as e:
        rollback()
        flash(str(e), "danger")
        print(e, type(e))
        raise e
    return redirect(request.referrer or url_for("transaction_page_bp.money_transactions_of_sandik_page"))


@transaction_page_bp.route('c-<int:contribution_id>/sil')
@sandik_authorization_required("write")
@contribution_required
def remove_contribution_by_manager_page(sandik_id, contribution_id):
    utils.remove_contribution(contribution=g.contribution, removed_by=current_user)
    return redirect(request.referrer or url_for("transaction_page_bp.payments_of_sandik_page"))


@transaction_page_bp.route('butun-uyeler-icin-vadesi-gelmis-aidatlari-olustur', methods=["GET", "POST"])
@sandik_authorization_required("write")
def create_due_contributions_for_all_members_page(sandik_id):
    utils.create_due_contributions_for_sandik(sandik=g.sandik, created_by=current_user,
                                              created_from="create_due_contributions_for_all_members_page")
    return redirect(request.referrer or url_for("sandik_page_bp.sandik_index_page", sandik_id=sandik_id))


@transaction_page_bp.route('s-para-giris-cikislari')
@sandik_authorization_required("read")
def money_transactions_of_sandik_page(sandik_id):
    g.type = "management"
    g.money_transactions = g.sandik.get_money_transactions().order_by(lambda mt: (desc(mt.date), desc(mt.id)))
    return render_template("transaction/money_transactions_page.html",
                           page_info=LayoutPI(title="Para giriş/çıkış işlemleri",
                                              active_dropdown="management-transactions"))


@transaction_page_bp.route('u-para-giris-cikislari')
@to_be_member_of_sandik_required
def money_transactions_of_member_page(sandik_id):
    g.type = "member"
    g.money_transactions = g.member.money_transactions_set.order_by(lambda mt: (desc(mt.date), desc(mt.id)))
    return render_template(
        "transaction/money_transactions_page.html",
        page_info=LayoutPI(title="Para giriş/çıkış işlemlerim", active_dropdown="member-transactions")
    )


@transaction_page_bp.route('uye-<int:member_id>/para-giris-cikislari')
@sandik_authorization_required("read")
def money_transactions_of_member_for_management_page(sandik_id, member_id):
    g.member = sandik_db.get_member(id=member_id, sandik_ref=g.sandik)
    if not g.member:
        abort(404)

    g.type = "management"
    page_title = f"Para giriş/çıkış işlemleri: {g.member.web_user_ref.name_surname}"

    g.money_transactions = g.member.money_transactions_set.order_by(lambda mt: (desc(mt.date), desc(mt.id)))
    return render_template(
        "transaction/money_transactions_page.html",
        page_info=LayoutPI(title=page_title, active_dropdown="management-transactions")
    )


@transaction_page_bp.route('s-sandik-islemleri')
@sandik_authorization_required("read")
def transactions_of_sandik_page(sandik_id):
    print("sandik:", g.sandik)
    g.transactions = utils.get_transactions(whose=g.sandik)
    return render_template("transaction/sandik_transactions_page.html",
                           page_info=LayoutPI(title="Sandık işlemleri", active_dropdown="management-transactions"))


@transaction_page_bp.route('u-sandik-islemleri')
@to_be_member_of_sandik_required
def transactions_of_member_page(sandik_id):
    g.transactions = utils.get_transactions(whose=g.member)
    return render_template("transaction/sandik_transactions_page.html",
                           page_info=LayoutPI(title="Sandık işlemlerim", active_dropdown="member-transactions"))


@transaction_page_bp.route('s-odemeler')
@sandik_authorization_required("read")
def payments_of_sandik_page(sandik_id):
    g.type = "management"
    g.payments = utils.get_payments(whose=g.sandik)
    due_and_unpaid_payments = utils.get_payments(whose=g.sandik, is_fully_paid=False, is_due=True)
    g.due_and_unpaid_payments = sorted(due_and_unpaid_payments, key=lambda p: p.term)
    return render_template("transaction/payments_page.html",
                           page_info=LayoutPI(title="Sandıktaki ödemeler", active_dropdown="management-transactions"))


@transaction_page_bp.route('u-odemeler')
@to_be_member_of_sandik_required
def payments_of_member_page(sandik_id):
    g.type = "member"
    g.payments = utils.get_payments(whose=g.member)
    due_and_unpaid_payments = utils.get_payments(whose=g.member, is_fully_paid=False, is_due=True)
    g.due_and_unpaid_payments = sorted(due_and_unpaid_payments, key=lambda t: t.term)
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
@to_be_member_of_sandik_required
def debts_of_member_page(sandik_id):
    g.unpaid_debts = utils.get_debts(whose=g.member, only_unpaid=True)
    g.debts = utils.get_debts(whose=g.member)
    return render_template("transaction/debts_page.html",
                           page_info=LayoutPI(title="Borçlarım", active_dropdown="member-transactions"))


@transaction_page_bp.route("u-ödemeleri-yenile")
@to_be_member_of_sandik_required
def pay_unpaid_payments_from_untreated_amount_of_member_page(sandik_id):
    utils.pay_unpaid_payments_from_untreated_amount_for_member(member=g.member, pay_future_payments=False,
                                                               created_by=current_user)
    return redirect(request.referrer or url_for("transaction_page_bp.payments_of_member_page", sandik_id=sandik_id))


@transaction_page_bp.route("s-ödemeleri-yenile")
@sandik_authorization_required("write")
def pay_unpaid_payments_from_untreated_amount_of_sandik_page(sandik_id):
    utils.pay_unpaid_payments_from_untreated_amount_for_sandik(sandik=g.sandik, pay_future_payments=False,
                                                               created_by=current_user)
    return redirect(request.referrer or url_for("transaction_page_bp.payments_of_sandik_page", sandik_id=sandik_id))


@transaction_page_bp.route("uye-<int:member_id>/ödemeleri-yenile")
@sandik_authorization_required("write")
def pay_unpaid_payments_from_untreated_amount_of_member_for_management_page(sandik_id, member_id):
    member = sandik_db.get_member(id=member_id, sandik_ref=g.sandik)
    if not member:
        abort(404)

    utils.pay_unpaid_payments_from_untreated_amount_for_member(member=member, pay_future_payments=False,
                                                               created_by=current_user)
    return redirect(request.referrer or url_for("sandik_page_bp.member_summary_for_management_page",
                                                sandik_id=sandik_id, member_id=member_id))

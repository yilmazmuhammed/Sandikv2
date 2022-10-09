from flask import Blueprint, request, render_template, g, flash, url_for, abort
from flask_login import current_user
from pony.orm import desc, rollback
from werkzeug.utils import redirect

from sandik.sandik import db as sandik_db
from sandik.sandik.exceptions import ThereIsNoMember, ThereIsNoShare, NoValidRuleFound
from sandik.sandik.requirement import sandik_authorization_required, to_be_member_of_sandik_required
from sandik.transaction import forms, utils, db
from sandik.transaction.authorization import money_transaction_required, contribution_required
from sandik.transaction.exceptions import MaximumDebtAmountExceeded, ThereIsNoDebt, MaximumAmountExceeded
from sandik.utils import LayoutPI
from sandik.utils.db_models import MoneyTransaction, get_paging_variables
from sandik.utils.forms import FormPI, flask_form_to_dict
from sandik.utils.period import NotValidPeriod
from sandik.utils.requirement import paging_must_be_verified

transaction_page_bp = Blueprint(
    'transaction_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@transaction_page_bp.route('islem-ekle', methods=["GET", "POST"])
@sandik_authorization_required("write")
def add_money_transaction_by_manager_page(sandik_id):
    form = forms.MoneyTransactionForm(sandik=g.sandik, form_title="Para giriş/çıkışı")

    if form.validate_on_submit():
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

            money_transaction = utils.add_money_transaction(
                member=member, creation_type=MoneyTransaction.CREATION_TYPE.BY_MANUEL,
                created_by=current_user, **form_data
            )
            return redirect(url_for("transaction_page_bp.add_money_transaction_by_manager_page", sandik_id=sandik_id))
        except (MaximumDebtAmountExceeded, NoValidRuleFound) as e:
            # rollback()
            flash(str(e), "danger")
        except Exception as e:
            raise e
            rollback()
            flash(str(e), "danger")

    return render_template("transaction/add_money_transaction_by_manager_page.html",
                           page_info=FormPI(title="Para giriş/çıkışı ekle", form=form,
                                            active_dropdown="management-transactions"))


@transaction_page_bp.route('borc-odemesi-ekle', methods=["GET", "POST"])
@sandik_authorization_required("write")
def add_money_transaction_for_debt_payment_by_manager_page(sandik_id):
    form = forms.DebtPaymentForm(sandik=g.sandik, form_title="Borç ödemesi")

    if form.validate_on_submit():
        form_data = flask_form_to_dict(request_form=request.form, exclude=["member", "debt"])
        try:
            member = sandik_db.get_member(id=form.member.data)
            if not member:
                raise ThereIsNoMember("Üye açılan listeden seçilmelidir")

            debt = db.get_debt(id=form.debt.data)
            if not debt or debt.member_ref != member:
                raise ThereIsNoDebt("Borç açılan listeden seçilmelidir")

            remaining_unpaid_amount = debt.get_unpaid_amount()
            if remaining_unpaid_amount < form.amount.data:
                raise MaximumAmountExceeded(f"Kalan borç miktarından daha fazla ödeme yapılamaz. <br>"
                                            f"Kalan borç miktarı: {remaining_unpaid_amount}")

            money_transaction = utils.add_money_transaction(
                type=MoneyTransaction.TYPE.REVENUE, payments=debt.get_unpaid_installments(),
                use_untreated_amount=None, pay_future_payments=True,
                member=member, creation_type=MoneyTransaction.CREATION_TYPE.BY_MANUEL,
                created_by=current_user, **form_data
            )
            return redirect(url_for("transaction_page_bp.add_money_transaction_for_debt_payment_by_manager_page",
                                    sandik_id=sandik_id))
        # MaximumDebtAmountExceeded, NoValidRuleFound olma ihtimali yok, bu kontrol çıkartılabilir
        except (MaximumDebtAmountExceeded, NoValidRuleFound) as e:
            # rollback()
            flash(str(e), "danger")
        except MaximumAmountExceeded as e:
            # rollback()
            flash(str(e), "danger")
        except Exception as e:
            raise e
            rollback()
            flash(str(e), "danger")

    return render_template(
        "transaction/add_money_transaction_for_debt_payment_by_manager_page.html",
        page_info=FormPI(title="Borç ödemesi ekle", form=form, active_dropdown="management-transactions")
    )


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
@paging_must_be_verified(default_page_num=1, default_page_size=50)
def money_transactions_of_sandik_page(sandik_id):
    g.type = "management"

    g.total_count, g.page_count, g.first_index, g.money_transactions = get_paging_variables(
        entities_query=utils.get_latest_money_transactions(whose=g.sandik), page_size=g.page_size, page_num=g.page_num
    )

    return render_template("transaction/money_transactions_page.html",
                           page_info=LayoutPI(title="Para giriş/çıkış işlemleri",
                                              active_dropdown="management-transactions"))


@transaction_page_bp.route('u-para-giris-cikislari')
@to_be_member_of_sandik_required
@paging_must_be_verified(default_page_num=1, default_page_size=50)
def money_transactions_of_member_page(sandik_id):
    g.type = "member"

    g.total_count, g.page_count, g.first_index, g.money_transactions = get_paging_variables(
        entities_query=utils.get_latest_money_transactions(whose=g.member), page_size=g.page_size, page_num=g.page_num
    )

    return render_template(
        "transaction/money_transactions_page.html",
        page_info=LayoutPI(title="Para giriş/çıkış işlemlerim", active_dropdown="member-transactions")
    )


@transaction_page_bp.route('uye-<int:member_id>/para-giris-cikislari')
@sandik_authorization_required("read")
@paging_must_be_verified(default_page_num=1, default_page_size=50)
def money_transactions_of_member_for_management_page(sandik_id, member_id):
    g.member = sandik_db.get_member(id=member_id, sandik_ref=g.sandik)
    if not g.member:
        abort(404)

    g.type = "management"

    g.total_count, g.page_count, g.first_index, g.money_transactions = get_paging_variables(
        entities_query=utils.get_latest_money_transactions(whose=g.member), page_size=g.page_size, page_num=g.page_num
    )

    page_title = f"Para giriş/çıkış işlemleri: {g.member.web_user_ref.name_surname}"
    return render_template(
        "transaction/money_transactions_page.html",
        page_info=LayoutPI(title=page_title, active_dropdown="management-transactions")
    )


@transaction_page_bp.route('s-sandik-islemleri')
@sandik_authorization_required("read")
@paging_must_be_verified(default_page_num=1, default_page_size=50)
def transactions_of_sandik_page(sandik_id):
    g.type = "management"
    g.transactions = utils.get_transactions(whose=g.sandik)

    return render_template("transaction/sandik_transactions_page.html",
                           page_info=LayoutPI(title="Sandık işlemleri", active_dropdown="management-transactions"))


@transaction_page_bp.route('u-sandik-islemleri')
@to_be_member_of_sandik_required
@paging_must_be_verified(default_page_num=1, default_page_size=50)
def transactions_of_member_page(sandik_id):
    g.type = "member"

    g.total_count, g.page_count, g.first_index, g.transactions = get_paging_variables(
        entities_query=utils.get_transactions(whose=g.member), page_size=g.page_size, page_num=g.page_num
    )

    return render_template("transaction/sandik_transactions_page.html",
                           page_info=LayoutPI(title="Sandık işlemlerim", active_dropdown="member-transactions"))


@transaction_page_bp.route('s-odemeler')
@sandik_authorization_required("read")
# TODO tablolara göre ayrı ayrı paging yapılacak
def payments_of_sandik_page(sandik_id):
    g.type = "management"
    g.payments = utils.get_payments(whose=g.sandik)
    due_and_unpaid_payments = utils.get_payments(whose=g.sandik, is_fully_paid=False, is_due=True)
    g.due_and_unpaid_payments = sorted(due_and_unpaid_payments, key=lambda p: p.term)
    return render_template("transaction/payments_page.html",
                           page_info=LayoutPI(title="Sandıktaki ödemeler", active_dropdown="management-transactions"))


@transaction_page_bp.route('u-odemeler')
@to_be_member_of_sandik_required
# TODO tablolara göre ayrı ayrı paging yapılacak
def payments_of_member_page(sandik_id):
    g.type = "member"
    g.payments = utils.get_payments(whose=g.member)
    due_and_unpaid_payments = utils.get_payments(whose=g.member, is_fully_paid=False, is_due=True)
    g.due_and_unpaid_payments = sorted(due_and_unpaid_payments, key=lambda t: t.term)
    return render_template("transaction/payments_page.html",
                           page_info=LayoutPI(title="Ödemelerim", active_dropdown="member-transactions"))


@transaction_page_bp.route('s-borclar')
@sandik_authorization_required("read")
# TODO tablolara göre ayrı ayrı paging yapılacak
def debts_of_sandik_page(sandik_id):
    g.type = "management"
    g.unpaid_debts = utils.get_debts(whose=g.sandik, only_unpaid=True)
    g.debts = utils.get_debts(whose=g.sandik)
    return render_template("transaction/debts_page.html",
                           page_info=LayoutPI(title="Sandıktaki borçlar", active_dropdown="management-transactions"))


@transaction_page_bp.route('u-borclar')
@to_be_member_of_sandik_required
# TODO tablolara göre ayrı ayrı paging yapılacak
def debts_of_member_page(sandik_id):
    g.type = "member"
    g.unpaid_debts = utils.get_debts(whose=g.member, only_unpaid=True)
    g.debts = utils.get_debts(whose=g.member)
    return render_template("transaction/debts_page.html",
                           page_info=LayoutPI(title="Borçlarım", active_dropdown="member-transactions"))


@transaction_page_bp.route("u-odemeleri-yenile")
@to_be_member_of_sandik_required
def pay_unpaid_payments_from_untreated_amount_of_member_page(sandik_id):
    pay_future_payments = False
    if request.args.get("pay_future_payments") == "1":
        pay_future_payments = True

    utils.pay_unpaid_payments_from_untreated_amount_for_member(member=g.member, pay_future_payments=pay_future_payments,
                                                               created_by=current_user)
    return redirect(request.referrer or url_for("transaction_page_bp.payments_of_member_page", sandik_id=sandik_id))


@transaction_page_bp.route("s-odemeleri-yenile")
@sandik_authorization_required("write")
def pay_unpaid_payments_from_untreated_amount_of_sandik_page(sandik_id):
    pay_future_payments = False
    if request.args.get("pay_future_payments") == "1":
        pay_future_payments = True
    utils.pay_unpaid_payments_from_untreated_amount_for_sandik(sandik=g.sandik, pay_future_payments=pay_future_payments,
                                                               created_by=current_user)
    return redirect(request.referrer or url_for("transaction_page_bp.payments_of_sandik_page", sandik_id=sandik_id))


@transaction_page_bp.route("uye-<int:member_id>/odemeleri-yenile")
@sandik_authorization_required("write")
def pay_unpaid_payments_from_untreated_amount_of_member_for_management_page(sandik_id, member_id):
    member = sandik_db.get_member(id=member_id, sandik_ref=g.sandik)
    if not member:
        abort(404)

    pay_future_payments = False
    if request.args.get("pay_future_payments") == "1":
        pay_future_payments = True

    utils.pay_unpaid_payments_from_untreated_amount_for_member(member=member, pay_future_payments=pay_future_payments,
                                                               created_by=current_user)
    return redirect(request.referrer or url_for("sandik_page_bp.member_summary_for_management_page",
                                                sandik_id=sandik_id, member_id=member_id))

from flask import Blueprint, request, render_template, g, flash, url_for, abort
from flask_login import current_user
from pony.orm import desc, rollback
from werkzeug.utils import redirect

from sandik.sandik import db as sandik_db, utils as sandik_utils
from sandik.sandik.exceptions import ThereIsNoMember, ThereIsNoShare, NoValidRuleFound
from sandik.sandik.requirement import sandik_authorization_required, to_be_member_of_sandik_required, member_required
from sandik.transaction import forms, utils, db
from sandik.transaction.authorization import money_transaction_required, contribution_required
from sandik.transaction.exceptions import MaximumDebtAmountExceeded, ThereIsNoDebt, MaximumAmountExceeded, \
    MaximumInstallmentExceeded, InvalidStartingTerm, TransactionException
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
            member, _ = sandik_utils.validate_whose_of_sandik(sandik=g.sandik, member_id=form.member.data)

            if int(form.type.data) == MoneyTransaction.TYPE.EXPENSE:
                utils.validate_money_transaction_for_expense(
                    mt_type=int(form.type.data), use_untreated_amount=form_data["use_untreated_amount"],
                    amount=form.amount.data, whose=member
                )

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


@transaction_page_bp.route('aidat-odemesi-ekle', methods=["GET", "POST"])
@sandik_authorization_required("write")
def add_money_transaction_for_contribution_payment_by_manager_page(sandik_id):
    form = forms.ContributionPaymentForm(sandik=g.sandik, form_title="Aidat ödemesi")

    if form.validate_on_submit():
        form_data = flask_form_to_dict(request_form=request.form, exclude=["member", "contribution"])
        try:
            member = sandik_db.get_member(id=form.member.data)
            if not member:
                raise ThereIsNoMember("Üye açılan listeden seçilmelidir")

            contribution = db.get_contribution(id=form.contribution.data)
            if not contribution or contribution.member_ref != member:
                raise ThereIsNoDebt("Ödenecek aidat açılan listeden seçilmelidir")

            remaining_unpaid_amount = contribution.get_unpaid_amount()
            if remaining_unpaid_amount < form.amount.data:
                raise MaximumAmountExceeded("Kalan aidat miktarından daha fazla ödeme yapılamaz. <br>"
                                            f"Kalan aidat miktarı: {remaining_unpaid_amount}")

            money_transaction = utils.add_money_transaction(
                type=MoneyTransaction.TYPE.REVENUE, payments=[contribution],
                use_untreated_amount=None, pay_future_payments=None,
                member=member, creation_type=MoneyTransaction.CREATION_TYPE.BY_MANUEL,
                created_by=current_user, **form_data
            )
            return redirect(
                url_for("transaction_page_bp.add_money_transaction_for_contribution_payment_by_manager_page",
                        sandik_id=sandik_id)
            )
        except MaximumAmountExceeded as e:
            # rollback()
            flash(str(e), "danger")
        except Exception as e:
            raise e
            rollback()
            flash(str(e), "danger")

    return render_template(
        "transaction/add_money_transaction_for_contribution_payment_by_manager_page.html",
        page_info=FormPI(title="Aidat ödemesi ekle", form=form, active_dropdown="management-transactions")
    )


@transaction_page_bp.route('aidat-ekle', methods=["GET", "POST"])
@sandik_authorization_required("write")
def add_custom_contribution_by_manager_page(sandik_id):
    form = forms.ContributionForm(sandik=g.sandik)

    if form.validate_on_submit():
        try:
            member, share = sandik_utils.validate_whose_of_sandik(sandik=g.sandik, member_id=form.member.data,
                                                                  share_id=form.share.data)
            utils.add_custom_contribution(amount=form.amount.data, period=form.period.data, share=share,
                                          created_by=current_user)
            return redirect(url_for("transaction_page_bp.add_custom_contribution_by_manager_page", sandik_id=sandik_id))
        except (ThereIsNoMember, ThereIsNoShare, NotValidPeriod) as e:
            flash(str(e), "danger")

    return render_template("transaction/add_custom_contribution_by_manager_page.html",
                           page_info=FormPI(title="Manuel aidat ekle", form=form,
                                            active_dropdown="management-transactions"))


@transaction_page_bp.route('eskiye-yonelik-aidat-ekle', methods=["GET", "POST"])
@sandik_authorization_required("write")
def add_custom_old_contributions_by_manager_page(sandik_id):
    form = forms.AddOldContributionsForm(sandik=g.sandik)

    if form.validate_on_submit():
        try:
            member, share = sandik_utils.validate_whose_of_sandik(sandik=g.sandik, member_id=form.member.data,
                                                                  share_id=form.share.data)
            added_contributions, not_added_contributions_with_amounts = utils.add_old_contributions(
                share=share,
                number_of_contributions=form.number_of_contribution.data,
                created_by=current_user
            )

            if added_contributions:
                success_messages = "Eklenen aidatlar:"
                for c in added_contributions:
                    success_messages += f"<br>{c.term} ({c.amount}₺)"
                flash(success_messages, "success")

            if not_added_contributions_with_amounts:
                warning_msg = ("Bazı aidat dönemlerinde birden farklı aidat miktarı var. Bu dönemler için eskiye "
                               "yönelik aidatlar otomatik olarak eklenemez. Bunları manuel eklemeniz gerekmektedir.")
                for period, amounts in not_added_contributions_with_amounts.items():
                    warning_msg += f"<br>{period} -> {', '.join([f'{a}₺' for a in amounts])}"
                flash(warning_msg, "warning")

            return redirect(url_for("transaction_page_bp.add_custom_old_contributions_by_manager_page", sandik_id=sandik_id))
        except (ThereIsNoMember, ThereIsNoShare, TransactionException) as e:
            flash(str(e), "danger")

    return render_template("transaction/add_custom_old_contributions_by_manager_page.html",
                           page_info=FormPI(title="Eskiye yönelik aidat ekle", form=form,
                                            active_dropdown="management-transactions"))


@transaction_page_bp.route('borc-ekle', methods=["GET", "POST"])
@sandik_authorization_required("write")
def add_custom_debt_by_manager_page(sandik_id):
    form = forms.DebtForm(sandik=g.sandik)

    if form.validate_on_submit():
        try:
            member, share = sandik_utils.validate_whose_of_sandik(sandik=g.sandik, member_id=form.member.data,
                                                                  share_id=form.share.data)
            use_untreated_amount = False

            utils.validate_money_transaction_for_expense(
                mt_type=MoneyTransaction.TYPE.EXPENSE, use_untreated_amount=use_untreated_amount,
                amount=form.amount.data, whose=share, start_period=form.start_period.data, mt_date=form.date.data,
                number_of_installment=form.number_of_installment.data, validate_noi=False
            )

            debt_mt = utils.add_money_transaction(
                member=member, amount=form.amount.data, created_by=current_user,
                date=form.date.data,
                type=MoneyTransaction.TYPE.EXPENSE, use_untreated_amount=use_untreated_amount,
                pay_future_payments=None, creation_type=MoneyTransaction.CREATION_TYPE.BY_CUSTOM_DEBT,
                detail=form.detail.data, share=form.share.data,
                number_of_installment=form.number_of_installment.data or None,
                start_period=form.start_period.data or None
            )
            return redirect(url_for("transaction_page_bp.add_custom_debt_by_manager_page", sandik_id=sandik_id))
        except (ThereIsNoMember, ThereIsNoShare) as e:
            flash(str(e), "danger")
        except (MaximumDebtAmountExceeded, NoValidRuleFound, InvalidStartingTerm, MaximumInstallmentExceeded) as e:
            flash(str(e), "danger")
            form.share.choices += sandik_db.shares_of_member_form_choices(member=member)

        except Exception as e:
            raise e
            rollback()
            flash(str(e), "danger")

    return render_template("transaction/add_custom_contribution_by_manager_page.html",
                           page_info=FormPI(title="Manuel borç ekle", form=form,
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
@member_required
def money_transactions_of_member_for_management_page(sandik_id, member_id):
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
    g.all_payments = {"is_grouped": True, "groups": utils.get_payment_grouped_by_member(whose=g.sandik)}
    g.due_and_unpaid_payment = {
        "is_grouped": True,
        "groups": utils.get_payment_grouped_by_member(whose=g.sandik, is_fully_paid=False, is_due=True)
    }

    return render_template("transaction/payments_page.html",
                           page_info=LayoutPI(title="Sandıktaki ödemeler", active_dropdown="management-transactions"))


@transaction_page_bp.route('u-odemeler')
@to_be_member_of_sandik_required
# TODO tablolara göre ayrı ayrı paging yapılacak
def payments_of_member_page(sandik_id):
    g.type = "member"
    g.all_payments = {"is_grouped": True, "groups": utils.get_payment_grouped_by_member(whose=g.member)}
    g.due_and_unpaid_payment = {
        "is_grouped": False,
        "payments": sorted(utils.get_payments(whose=g.member, is_fully_paid=False, is_due=True), key=lambda t: t.term)
    }
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
@member_required
def pay_unpaid_payments_from_untreated_amount_of_member_for_management_page(sandik_id, member_id):
    pay_future_payments = False
    if request.args.get("pay_future_payments") == "1":
        pay_future_payments = True

    utils.pay_unpaid_payments_from_untreated_amount_for_member(member=g.member, pay_future_payments=pay_future_payments,
                                                               created_by=current_user)
    return redirect(request.referrer or url_for("sandik_page_bp.member_summary_for_management_page",
                                                sandik_id=sandik_id, member_id=member_id))

from pony.orm import desc, flush  # ponyorm order_by icin lambda string'inde 'desc' fonksiyonukullaniliyor

from sandik.transaction import db
from sandik.transaction.exceptions import UndefinedRemoveOperation
from sandik.utils import period as period_utils
from sandik.utils.db_models import Share, Member, MoneyTransaction, Contribution, Installment, Sandik, Debt, Log, \
    WebUser
from sandik.utils.exceptions import InvalidWhoseType
from sandik.utils.period import NotValidPeriod


def sum_of_unpaid_and_due_payments(whose):
    """
    Vadesi gelmiş odemeler sunlardir:
        - Bu ay ve onceki aylarin odenmemis aidatlari
        - Bu ay ve onceki aylarin odenmemis taksitleri
    """
    if not isinstance(whose, Share) and not isinstance(whose, Member):
        raise Exception("'whose' sadece 'Member' yada 'Share' olabilir.")
    return db.sum_of_unpaid_and_due_contributions(whose=whose) + db.sum_of_unpaid_and_due_installments(whose=whose)


def sum_of_future_and_unpaid_payments(whose):
    if not isinstance(whose, Share) and not isinstance(whose, Member):
        raise Exception("'whose' sadece 'Member' yada 'Share' olabilir.")
    # TODO vadesi gelmemiş ve ödenmemiş aidatları da ekle
    return db.sum_of_future_and_unpaid_installments(whose=whose)


def pay_contribution(contribution, amount, money_transaction, created_by):
    return db.create_sub_receipt(money_transaction=money_transaction, contribution_ref=contribution, amount=amount,
                                 is_auto=True, created_by=created_by)


def pay_installment(installment, amount, money_transaction, created_by):
    return db.create_sub_receipt(money_transaction=money_transaction, installment_ref=installment, amount=amount,
                                 is_auto=True, created_by=created_by)


def borrow_debt(amount, money_transaction, created_by):
    member = money_transaction.member_ref

    shares_with_max_amount_can_borrow = [(share, share.max_amount_can_borrow()) for share in member.shares_set]
    sorted_shares_by_max_amount_can_borrow = sorted(shares_with_max_amount_can_borrow, key=lambda x: x[1])

    remaining_amount = amount
    optimal_share = None
    for share, macb in sorted_shares_by_max_amount_can_borrow:
        if not optimal_share and remaining_amount > macb:
            # Alınacak borcun bir hisseden alınması yetmiyorsa,
            # bu miktar en çok borç alabilen hisseden başlanarak hisselere paylaştırılır.
            db.create_debt(amount=macb, money_transaction=money_transaction, created_by=created_by, share=share)
            remaining_amount -= macb
        elif macb >= remaining_amount:
            # Hangi hisseden borç alınacağı belirlenirken,
            # borç alabileceği miktar borç miktarından büyük ve en yakın olan hisse tercih edilir.
            optimal_share = share
        else:
            break
    if optimal_share:
        db.create_debt(amount=remaining_amount, money_transaction=money_transaction, share=optimal_share,
                       created_by=created_by)


def borrow_from_untreated_amount(untreated_money_transaction, amount, money_transaction, created_by):
    return db.create_retracted(
        amount=amount, created_by=created_by,
        untreated_money_transaction=untreated_money_transaction, money_transaction=money_transaction
    )


# TODO ismi değişebilir, unpaid paymentları ödüyor
def add_revenue_transactions(money_transaction, pay_future_payments, created_by):
    member = money_transaction.member_ref
    remaining_amount = money_transaction.get_undistributed_amount()
    if remaining_amount <= 0:
        return False

    payments = get_payments(whose=member, is_fully_paid=False, is_due=True)
    if pay_future_payments:
        payments += get_payments(whose=member, is_fully_paid=False, is_due=False)

    payments = sorted(payments, key=lambda t: t.term)
    for p in payments:
        amount = p.get_unpaid_amount() if remaining_amount >= p.get_unpaid_amount() else remaining_amount

        if isinstance(p, Contribution):
            pay_contribution(contribution=p, amount=amount, money_transaction=money_transaction,
                             created_by=created_by)
        elif isinstance(p, Installment):
            pay_installment(installment=p, amount=amount, money_transaction=money_transaction,
                            created_by=created_by)
        else:
            Exception("ERRCODE: 0002, MSG: Site yöneticisiyle iletişime geçiniz...")

        remaining_amount -= amount

        if remaining_amount <= 0:
            break

    if remaining_amount < 0:
        raise Exception("ERR_CODE: 0001, MSG: Site yöneticisiyle iletişime geçiniz...")

    return True


def add_expense_transactions(money_transaction, use_untreated_amount, created_by):
    member = money_transaction.member_ref
    remaining_amount = money_transaction.amount

    if use_untreated_amount:
        untreated_money_transactions = member.get_revenue_money_transactions_are_not_fully_distributed()
        for mt in untreated_money_transactions:
            undistributed_amount = mt.get_undistributed_amount()
            amount = undistributed_amount if remaining_amount >= undistributed_amount else remaining_amount
            borrow_from_untreated_amount(untreated_money_transaction=mt, amount=amount,
                                         money_transaction=money_transaction, created_by=created_by)
            remaining_amount -= amount

            if remaining_amount <= 0:
                break

    if remaining_amount > 0:
        borrow_debt(amount=remaining_amount, money_transaction=money_transaction, created_by=created_by)

    return True


def add_money_transaction(member, created_by, use_untreated_amount, pay_future_payments, creation_type, **kwargs):
    money_transaction = db.create_money_transaction(member_ref=member, is_fully_distributed=False,
                                                    creation_type=creation_type, created_by=created_by, **kwargs)
    if money_transaction.type == MoneyTransaction.TYPE.REVENUE:
        # TODO add_revenue_transactions yerine pay_unpaid_payments_... fonksiyonu mu kullanılmalı?
        add_revenue_transactions(money_transaction=money_transaction, pay_future_payments=pay_future_payments,
                                 created_by=created_by)

    elif money_transaction.type == MoneyTransaction.TYPE.EXPENSE:
        print("expense")
        # TODO Önce kendi parasından, güven bağı olan kişilerin parasından bu para borç olarak
        #  alınabiliyor mu diye kontrol et.
        add_expense_transactions(money_transaction=money_transaction, use_untreated_amount=use_untreated_amount,
                                 created_by=created_by)
    return money_transaction


def create_due_contributions_for_share(share, created_by, created_from="", periods=None):
    print(f"START: Creating contributions for '{share}'...")

    if not isinstance(periods, list):
        first_period = period_utils.date_to_period(share.date_of_opening)
        last_period = period_utils.current_period()
        periods = period_utils.get_periods_between_two_period(
            first_period=first_period, last_period=last_period
        ) if first_period <= last_period else []

    for period in periods:
        try:
            if not period_utils.is_valid_period(period):
                raise NotValidPeriod(f"Period '{period}' is not valid: Period is not str)")
            if not db.get_contribution(share_ref=share, term=period):
                db.create_contribution(share=share, period=period, created_by=created_by, log_detail=created_from)
                print(f"Create contribution for share: '{share}', period: '{period}'")
            else:
                print(f"Contribution already exist for share: '{share}', period: '{period}'")
        except Exception as e:
            print("Exception in create_due_contributions_for_share:", str(type(e)), " -> ", str(e))
            print(created_by)
            Log(web_user_ref=created_by, type=Log.TYPE.LOG_LEVEL.ERROR,
                detail=f"created_from: {created_from} \n Exception: {str(type(e))} -> {str(e)}")
    print(f"FINISH: Creating contributions for '{share}'...")


def create_due_contributions_for_member(member, created_by, created_from=""):
    print(f"START: Creating contributions for '{member}'...")
    for share in member.shares_set:
        create_due_contributions_for_share(share=share, created_by=created_by, created_from=created_from)

    pay_unpaid_payments_from_untreated_amount_for_member(member=member, pay_future_payments=False,
                                                         created_by=created_by)
    print(f"FINISH: Creating contributions for '{member}'...")


def create_due_contributions_for_sandik(sandik, created_by, created_from=""):
    print(f"START: Creating contributions for '{sandik}'...")
    for member in sandik.get_active_members():
        create_due_contributions_for_member(member=member, created_by=created_by, created_from=created_from)
    print(f"FINISH: Creating contributions for '{sandik}'...")


def create_due_contributions_for_all_sandiks(created_by, created_from=""):
    print(f"START: Creating contributions for 'all sandiks'...")
    for sandik in Sandik.select():
        create_due_contributions_for_sandik(sandik=sandik, created_by=created_by, created_from=created_from)
    print(f"FINISH: Creating contributions for 'all sandiks'...")


def pay_unpaid_payments_from_untreated_amount_for_member(member: Member, pay_future_payments: bool,
                                                         created_by: WebUser):
    print(f"START: Paying payments for '{member}' with pay_future_payments={pay_future_payments} ...")
    money_transactions = member.get_revenue_money_transactions_are_not_fully_distributed()
    for mt in money_transactions:
        add_revenue_transactions(money_transaction=mt, pay_future_payments=pay_future_payments, created_by=created_by)
    print(f"FINISH: Paying payments for '{member}' with pay_future_payments={pay_future_payments} ...")


def pay_unpaid_payments_from_untreated_amount_for_sandik(sandik: Sandik, pay_future_payments: bool,
                                                         created_by: WebUser):
    print(f"START: Paying payments for '{sandik}' with pay_future_payments={pay_future_payments} ...")
    for member in sandik.get_active_members():
        pay_unpaid_payments_from_untreated_amount_for_member(member=member, pay_future_payments=pay_future_payments,
                                                             created_by=created_by)
    print(f"FINISH: Paying payments for '{sandik}' with pay_future_payments={pay_future_payments} ...")


def get_transactions(whose):
    if isinstance(whose, Sandik):
        whose_filter_ref = "sandik_ref"
    elif isinstance(whose, Member):
        whose_filter_ref = "member_ref"
    elif isinstance(whose, Share):
        whose_filter_ref = "share_ref"
    else:
        raise InvalidWhoseType("whose 'Sandik', 'Member' veya 'Share' olmalıdır", errcode=1, create_log=True)
    print("get_transactions -> whose_filter_ref:", whose_filter_ref, "whose:", whose)
    contributions = db.select_contributions(f"lambda c: c.{whose_filter_ref} == {whose}").order_by(
        lambda c: (c.term, c.id)
    )[:][:]
    installment = db.select_installments(f"lambda i: i.{whose_filter_ref} == {whose}").order_by(
        lambda i: (i.term, i.id)
    )[:][:]
    debts = db.select_debts(f"lambda d: d.{whose_filter_ref} == {whose}").order_by(
        lambda d: (d.sub_receipt_ref.money_transaction_ref.date, d.id)
    )[:][:]

    transactions = contributions + installment + debts

    sorting_function = lambda t: t.term if not isinstance(t, Debt) else period_utils.date_to_period(
        t.sub_receipt_ref.money_transaction_ref.date
    )
    sorted_transactions = sorted(transactions, key=sorting_function, reverse=True)

    ret = []
    for t in sorted_transactions:
        if isinstance(t, Contribution):
            temp = {"term": t.term,
                    "detail": "",
                    "id_prefix": "C", "transaction_type": "Aidat", "transaction": t}
        elif isinstance(t, Installment):
            temp = {"term": t.term,
                    "detail": f"Borç: #{t.debt_ref.id}",
                    "id_prefix": "I", "transaction_type": "Taksit", "transaction": t}
        elif isinstance(t, Debt):
            # temp = {"term": period_utils.date_to_period(t.sub_receipt_ref.money_transaction_ref.date),
            temp = {"term": t.sub_receipt_ref.money_transaction_ref.date.strftime("%Y-%m-%d"),
                    "detail": "",
                    "id_prefix": "D", "transaction_type": "Borç", "transaction": t}
        else:
            temp = {"term": "-", "id_prefix": "-", "transaction_type": "-", "detail": "", "transaction": t}

        ret.append(temp)

    return ret


def get_payments(whose, is_fully_paid: bool = None, is_due: bool = None, periods: list = None):
    filter_str = "lambda p: p"
    order_str = "lambda p: (p.is_fully_paid, p.term, p.member_ref.web_user_ref.name_surname, p.id)"
    if isinstance(whose, Sandik):
        filter_str += f" and p.sandik_ref == {whose}"
    elif isinstance(whose, Member):
        filter_str += f" and p.member_ref == {whose}"
    elif isinstance(whose, Share):
        filter_str += f" and p.share_ref == {whose}"
    else:
        raise InvalidWhoseType("whose 'Sandik', 'Member' veya 'Share' olmalıdır", errcode=2, create_log=True)

    if periods is None:
        pass
    elif not isinstance(periods, list):
        raise InvalidWhoseType("periods liste olmalıdır")
    else:
        for period in periods:
            if not period_utils.is_valid_period(period=period):
                raise NotValidPeriod(f"'{period}' geçerli bir periyod değil'")
        filter_str += f" and p.term in {periods} "

    if is_due is True:
        filter_str += f" and p.term <= '{period_utils.current_period()}' "
    elif is_due is False:
        filter_str += f" and p.term > '{period_utils.current_period()}' "

    if is_fully_paid in [True, False]:
        filter_str += f"and p.is_fully_paid == {is_fully_paid}"

    print("get_payments -> filter_str:", filter_str)
    print("get_payments -> order_str:", order_str)

    contributions = db.select_contributions(filter_str).order_by(order_str)
    installment = db.select_installments(filter_str).order_by(order_str)

    transactions = contributions[:][:] + installment[:][:]
    sorted_transactions = sorted(transactions, key=lambda t: t.term, reverse=True)

    return sorted_transactions


def get_debts(whose, only_unpaid=False):
    filter_str = "lambda d: d"
    if isinstance(whose, Sandik):
        filter_str += f" and d.sandik_ref == {whose}"
    elif isinstance(whose, Member):
        filter_str += f" and d.member_ref == {whose}"
    elif isinstance(whose, Share):
        filter_str += f" and d.share_ref == {whose}"
    else:
        raise InvalidWhoseType("whose 'Sandik', 'Member' veya 'Share' olmalıdır", errcode=3, create_log=True)

    if only_unpaid:
        filter_str += f" and d.get_unpaid_amount() > 0"

    debts = db.select_debts(filter_str).order_by(
        lambda d: (d.sub_receipt_ref.money_transaction_ref.date, d.id)
    )

    return debts


def get_latest_money_transactions(whose, periods_count: int = 0):
    filter_str = "lambda mt: mt"
    order_str = "lambda mt: (desc(mt.date), desc(mt.id))"

    if isinstance(whose, Sandik):
        filter_str += f" and mt.sandik_ref == {whose}"
    elif isinstance(whose, Member):
        filter_str += f" and mt.member_ref == {whose}"
    else:
        raise InvalidWhoseType("whose 'Sandik' veya 'Member' olmalıdır", errcode=2, create_log=True)

    # if periods_count > 0:
    #     filter_str += f" and mt.date >= {period_utils.period_to_date(period_utils.previous_period(prev_count=periods_count))}"

    money_transactions = db.select_money_transactions(filter_str)

    if periods_count > 0:
        money_transactions = money_transactions.filter(lambda mt: mt.date >= period_utils.period_to_date(
            period_utils.previous_period(prev_count=periods_count - 1)))

    money_transactions = money_transactions.order_by(order_str)

    return money_transactions


def add_custom_contribution(amount, period, share, created_by):
    if not period_utils.is_valid_period(period=period):
        raise NotValidPeriod(f"'{period}' geçerli bir aidat dönemi değil. Lütfen YYYY-AA (Yıl-Ay) formatında giriniz.")
    db.create_contribution(share=share, period=period, amount=amount, created_by=created_by)


def remove_sub_receipt_from_contribution(sub_receipt, removed_by):
    return db.delete_sub_receipt(sub_receipt=sub_receipt, removed_by=removed_by)


def remove_sub_receipt_from_installment(sub_receipt, removed_by):
    return db.delete_sub_receipt(sub_receipt=sub_receipt, removed_by=removed_by)


def remove_sub_receipt(sub_receipt, removed_by):
    if sub_receipt.contribution_ref:
        remove_sub_receipt_from_contribution(sub_receipt=sub_receipt, removed_by=removed_by)
    elif sub_receipt.installment_ref:
        remove_sub_receipt_from_installment(sub_receipt=sub_receipt, removed_by=removed_by)
    else:
        raise UndefinedRemoveOperation("Tanımlanmamış sub receipt silme işlemi")


def remove_money_transaction(money_transaction, removed_by):
    member = money_transaction.member_ref
    flush()  # TODO acaba neden bunu koymuşum??
    for sub_receipt in money_transaction.sub_receipts_set:
        remove_sub_receipt(sub_receipt=sub_receipt, removed_by=removed_by)
    db.delete_money_transaction(money_transaction=money_transaction, removed_by=removed_by)

    # Bir para işlemi silinince ödenmiş olan bazı ödemeler, ödenmemiş durumuna geçebilir.
    # Bu durumda üyenin işleme konmamış parası varsa bu parayla ödemeler tekrar ödenmelidir
    pay_unpaid_payments_from_untreated_amount_for_member(member=member, pay_future_payments=False,
                                                         created_by=removed_by)


def remove_contribution(contribution, removed_by):
    for sub_receipt in contribution.sub_receipts_set:
        remove_sub_receipt(sub_receipt=sub_receipt, removed_by=removed_by)
    db.delete_contribution(contribution=contribution, removed_by=removed_by)

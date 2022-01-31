from sandik.transaction import db
from sandik.utils import period as period_utils
from sandik.utils.db_models import Share, Member, MoneyTransaction, Contribution, Installment


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
    return db.sum_of_future_and_unpaid_installments(whose=whose)


def untreated_amount(member):
    return db.sum_of_untreated_money_transactions(member=member)


def get_unpaid_and_due_payments(whose):
    contributions = db.get_unpaid_and_due_contributions(whose=whose)[:][:]
    installments = db.get_unpaid_and_due_installments(whose=whose)[:][:]
    payments = []
    while len(contributions) > 0 and len(installments) > 0:
        if contributions[0].term <= installments[0].term:
            payments.append(contributions.pop(0))
        else:
            payments.append(installments.pop(0))
    payments += contributions
    payments += installments
    return payments


def get_future_and_unpaid_payments(whose):
    installments = db.get_future_and_unpaid_installments(whose=whose)[:]
    return installments


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


def add_revenue_transactions(money_transaction, pay_future_payments, created_by):
    member = money_transaction.member_ref
    remaining_amount = money_transaction.amount
    payments = get_unpaid_and_due_payments(whose=member)
    if pay_future_payments:
        payments += get_future_and_unpaid_payments(whose=member)

    for p in payments:
        amount = p.unpaid_amount() if remaining_amount >= p.unpaid_amount() else remaining_amount

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
    if remaining_amount == 0:
        # TODO test et SubReceipt.after_insert fonksiyonunda yapılıyor,
        #  çalışmıyorsa burada yap, çalışıyorsa fonksiyonu sil
        # db.sign_money_transaction_as_fully_distributed(money_transaction=money_transaction, signed_by=created_by)
        pass


def add_expense_transactions(money_transaction, use_untreated_amount, created_by):
    member = money_transaction.member_ref
    remaining_amount = money_transaction.amount

    if use_untreated_amount:
        untreated_money_transactions = member.get_untreated_money_transactions()
        for mt in untreated_money_transactions:
            amount = mt.untreated_amount() if remaining_amount >= mt.untreated_amount() else remaining_amount
            borrow_from_untreated_amount(untreated_money_transaction=mt, amount=amount,
                                         money_transaction=money_transaction, created_by=created_by)
            remaining_amount -= amount

            if remaining_amount <= 0:
                break

    if remaining_amount > 0:
        borrow_debt(amount=remaining_amount, money_transaction=money_transaction, created_by=created_by)

    if remaining_amount == 0:
        # TODO test et: SubReceipt.after_insert fonksiyonunda yapılıyor,
        #  çalışmıyorsa burada yap, çalışıyorsa fonksiyonu sil
        # db.sign_money_transaction_as_fully_distributed(money_transaction=money_transaction, signed_by=created_by)
        pass

    pass


def add_money_transaction(member, created_by, use_untreated_amount, pay_future_payments, creation_type, **kwargs):
    money_transaction = db.create_money_transaction(member_ref=member, is_fully_distributed=False,
                                                    creation_type=creation_type, created_by=created_by, **kwargs)
    if money_transaction.type == MoneyTransaction.TYPE.REVENUE:
        add_revenue_transactions(money_transaction=money_transaction, pay_future_payments=pay_future_payments,
                                 created_by=created_by)

    elif money_transaction.type == MoneyTransaction.TYPE.EXPENSE:
        print("expense")
        # TODO Önce kendi parasından, güven bağı olan kişilerin parasından bu para aborç olarak
        #  alınabiliyor mu diye kontrol et.
        add_expense_transactions(money_transaction=money_transaction, use_untreated_amount=use_untreated_amount,
                                 created_by=created_by)
    return money_transaction


# def due_all_contributions_periods(whose):
#     if isinstance(whose, Share):
#         return get_periods_between_two_period(date_to_period(whose.date_of_opening), current_period())
#     elif isinstance(whose, Member):
#         ret = []
#         for share in whose.shares_set:
#             ret += [(share.id, period) for period in due_all_contributions_periods(share)]
#         return ret
#     else:
#         raise Exception("'whose' sadece 'Member' yada 'Share' olabilir.")
#
#
# def total_amount_of_due_unpaid_contributions(whose):
#     half_paid_contribution = db.get_due_contribution(whose=whose)
#     paid_contributions = db.get_paid_contributions(whose=whose)
#     old_contribution_periods = due_all_contributions_periods(whose=whose)
#     for c in paid_contributions:
#         old_contribution_periods.remove((c.share_ref.id, c.period))
#     return
def create_due_contributions_for_the_share(share, created_by, created_from=""):
    print(f"START: Creating contributions for '{share}'...")
    first_period = period_utils.date_to_period(share.date_of_opening)
    last_period = period_utils.current_period()
    periods = period_utils.get_periods_between_two_period(first_period=first_period, last_period=last_period)
    for period in periods:
        if not db.get_contribution(share_ref=share, term=period):
            db.create_contribution(share=share, period=period, created_by=created_by, log_detail=created_from)
            print(f"Create contribution for share: '{share}', period: '{period}'")
        else:
            print(f"Contribution already exist for share: '{share}', period: '{period}'")
    print(f"FINISH: Creating contributions for '{share}'...")


def create_due_contributions_for_the_member(member, created_by, created_from=""):
    print(f"START: Creating contributions for '{member}'...")
    for share in member.shares_set:
        create_due_contributions_for_the_share(share=share, created_by=created_by, created_from=created_from)
    print(f"FINISH: Creating contributions for '{member}'...")


def create_due_contributions_for_all_members(sandik, created_by, created_from=""):
    print(f"START: Creating contributions for '{sandik}'...")
    for member in sandik.members_set:
        create_due_contributions_for_the_member(member=member, created_by=created_by, created_from=created_from)
    print(f"FINISH: Creating contributions for '{sandik}'...")

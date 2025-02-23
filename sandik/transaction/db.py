from math import ceil

from pony.orm import select, flush, distinct

from sandik.transaction.exceptions import InvalidRemoveOperation, TransactionException
from sandik.utils import period as period_utils, sandik_preferences
from sandik.utils.db_models import Contribution, Share, Member, Installment, MoneyTransaction, Log, SubReceipt, Debt, \
    PieceOfDebt, Retracted, Sandik
from sandik.utils.exceptions import UnexpectedValue


def create_money_transaction(member_ref, created_by, **kwargs) -> MoneyTransaction:
    log = Log(web_user_ref=created_by, type=Log.TYPE.MONEY_TRANSACTION.CREATE,
              logged_sandik_ref=member_ref.sandik_ref, logged_member_ref=member_ref)
    return MoneyTransaction(logs_set=log, member_ref=member_ref, **kwargs)


def create_sub_receipt(money_transaction, created_by, **kwargs) -> SubReceipt:
    share = None
    logged_ref_items = {
        "logged_money_transaction_ref": money_transaction,
        "logged_member_ref": money_transaction.member_ref,
        "logged_sandik_ref": money_transaction.member_ref.sandik_ref,
    }
    for ref_item in ["contribution_ref", "installment_ref", "debt_ref"]:
        if kwargs.get(ref_item):
            share = kwargs.get(ref_item).share_ref
            logged_ref_items[f"logged_{ref_item}"] = kwargs.get(ref_item)
            logged_ref_items["logged_share_ref"] = share

    log = Log(web_user_ref=created_by, type=Log.TYPE.SUB_RECEIPT.CREATE, **logged_ref_items)

    return SubReceipt(money_transaction_ref=money_transaction, share_ref=share, logs_set=log, **kwargs)


def create_installment(debt, created_by, **kwargs) -> Installment:
    logged_ref_items = {
        "logged_debt_ref": debt,
        "logged_sub_receipt_ref": debt.sub_receipt_ref,
        "logged_money_transaction_ref": debt.sub_receipt_ref.money_transaction_ref,
        "logged_share_ref": debt.share_ref,
        "logged_member_ref": debt.share_ref.member_ref,
        "logged_sandik_ref": debt.share_ref.member_ref.sandik_ref,
    }
    return Installment(
        debt_ref=debt, **kwargs,
        logs_set=Log(web_user_ref=created_by, type=Log.TYPE.INSTALLMENT.CREATE, **logged_ref_items)
    )


def create_contribution(share, period, created_by, amount=None, log_detail=""):
    if amount is None:
        amount = share.member_ref.contribution_amount
    return Contribution(
        amount=amount, term=period, share_ref=share,
        logs_set=Log(web_user_ref=created_by, type=Log.TYPE.CONTRIBUTION.CREATE, detail=log_detail)
    )


def create_piece_of_debt(member, debt, amount, trust_relationship_for_log, created_by) -> PieceOfDebt:
    logged_ref_items = {
        "logged_debt_ref": debt,
        "logged_sub_receipt_ref": debt.sub_receipt_ref,
        "logged_money_transaction_ref": debt.sub_receipt_ref.money_transaction_ref,
        "logged_share_ref": debt.share_ref,
        "logged_member_ref": debt.share_ref.member_ref,
        "logged_sandik_ref": debt.share_ref.member_ref.sandik_ref,
        "logged_trust_relationship_ref": trust_relationship_for_log,
    }
    log = Log(web_user_ref=created_by, type=Log.TYPE.PIECE_OF_DEBT.CREATE, **logged_ref_items)
    return PieceOfDebt(logs_set=log, member_ref=member, debt_ref=debt, amount=amount)


def create_installments_of_debt(debt, created_by):
    debt_amount = debt.amount
    number_of_installment = debt.number_of_installment
    start_period = debt.starting_term

    remaining_amount = debt_amount
    installment_amount = ceil(debt_amount / number_of_installment)
    for i in range(1, number_of_installment + 1):
        if remaining_amount <= 0:
            raise UnexpectedValue(f"RA: {remaining_amount}, "
                                  f"MSG: Beklenmedik bir hata ile karşılaşıldı. Düzeltilmesi için "
                                  f"lütfen site yöneticisi ile iletişime geçerek ERRCODE'u ve RA'yı söyleyiniz.",
                                  errcode=15, create_log=True)

        temp_amount = installment_amount if remaining_amount >= installment_amount else remaining_amount
        installment_term = period_utils.get_last_installment_period(start_period, i)
        create_installment(amount=temp_amount, term=installment_term, debt=debt, created_by=created_by)
        remaining_amount -= temp_amount

    if remaining_amount != 0:
        raise UnexpectedValue(f"RA: {remaining_amount}, "
                              f"MSG: Beklenmedik bir hata ile karşılaşıldı. Düzeltilmesi için "
                              f"lütfen site yöneticisi ile iletişime geçerek ERRCODE'u ve RA'yı söyleyiniz.",
                              errcode=14, create_log=True)

    return debt.installments_set


def create_piece_of_debts(debt, created_by):
    debt_amount = debt.amount

    member = debt.share_ref.member_ref
    trusted_links = member.accepted_trust_links()
    # TODO performans için get_balance bir defa çağrılarak bir listede tutulabilir
    sorted_trusted_links = sorted(trusted_links, key=lambda tl: tl.other_member(whose=member).get_balance())

    remaining_amount = debt_amount

    # Önce kendinden borç almalı
    temp_amount = member.get_balance() if member.get_balance() <= remaining_amount else remaining_amount
    create_piece_of_debt(member=member, debt=debt, amount=temp_amount,
                         trust_relationship_for_log=None, created_by=created_by)
    remaining_amount -= temp_amount

    if remaining_amount == 0:
        return debt.piece_of_debts_set

    for i, link in enumerate(sorted_trusted_links):
        if remaining_amount <= 0:
            raise Exception(f"ERRCODE: 0016, RA: {remaining_amount}, "
                            f"MSG: Beklenmedik bir hata ile karşılaşıldı. Düzeltilmesi için "
                            f"lütfen site yöneticisi ile iletişime geçerek ERRCODE'u ve RA'yı söyleyiniz.")

        temp_amount = ceil(remaining_amount / (len(sorted_trusted_links) - i))
        temp_amount = temp_amount if temp_amount <= remaining_amount else remaining_amount

        other_member = link.other_member(whose=member)
        temp_amount = temp_amount if temp_amount <= other_member.get_balance() else other_member.get_balance()

        create_piece_of_debt(member=other_member, debt=debt, amount=temp_amount,
                             trust_relationship_for_log=link, created_by=created_by)
        remaining_amount -= temp_amount

    if remaining_amount != 0:
        raise Exception(f"ERRCODE: 0017, RA: {remaining_amount}, "
                        f"MSG: Beklenmedik bir hata ile karşılaşıldı. Düzeltilmesi için "
                        f"lütfen site yöneticisi ile iletişime geçerek ERRCODE'u ve RA'yı söyleyiniz.")

    return debt.piece_of_debts_set


def create_debt(amount, share, money_transaction, created_by, start_period=None, number_of_installment=None) -> Debt:
    sandik = money_transaction.member_ref.sandik_ref
    if number_of_installment is None:
        number_of_installment = sandik_preferences.max_number_of_installment(sandik=sandik, amount=amount)
    if start_period is None:
        start_period = sandik_preferences.get_start_period(sandik=sandik, debt_date=money_transaction.date)

    due_term = period_utils.get_last_installment_period(start_period, number_of_installment)

    logged_ref_items = {
        "logged_money_transaction_ref": money_transaction,
        "logged_member_ref": money_transaction.member_ref,
        "logged_sandik_ref": money_transaction.member_ref.sandik_ref,
        "logged_share_ref": share,
    }

    debt = Debt(
        amount=amount, share_ref=share,
        number_of_installment=number_of_installment, starting_term=start_period, due_term=due_term,
        logs_set=Log(web_user_ref=created_by, type=Log.TYPE.DEBT.CREATE, **logged_ref_items),
        sub_receipt_ref=create_sub_receipt(money_transaction=money_transaction, amount=amount, is_auto=True,
                                           created_by=created_by)
    )

    create_installments_of_debt(debt=debt, created_by=created_by)
    if sandik.is_type_with_trust_relationship():
        create_piece_of_debts(debt=debt, created_by=created_by)

    return debt


def create_retracted(amount, untreated_money_transaction, money_transaction, created_by) -> Retracted:
    logged_ref_items = {
        "logged_sandik_ref": money_transaction.member_ref.sandik_ref
    }
    return Retracted(
        amount=amount,
        expense_sub_receipt_ref=create_sub_receipt(money_transaction=money_transaction, amount=amount, is_auto=True,
                                                   created_by=created_by),
        revenue_sub_receipt_ref=create_sub_receipt(money_transaction=untreated_money_transaction, amount=amount,
                                                   is_auto=True, created_by=created_by),
        logs_set=Log(web_user_ref=created_by, type=Log.TYPE.RETRACTED.CREATE, **logged_ref_items)
    )


def delete_sub_receipt(sub_receipt, removed_by):
    if sub_receipt.debt_ref is not None:
        raise InvalidRemoveOperation("Borca ait bir sub receipt, borç silinmeden silinemez!")
    if sub_receipt.expense_retracted_ref is not None or sub_receipt.revenue_retracted_ref is not None:
        raise InvalidRemoveOperation("Retracted'a ait bir sub receipt, retracted silinmeden silinemez!")

    logged_ref_items = {
        "logged_money_transaction_ref": sub_receipt.money_transaction_ref,
        "logged_share_ref": sub_receipt.share_ref,
        "logged_member_ref": sub_receipt.money_transaction_ref.member_ref,
        "logged_sandik_ref": sub_receipt.money_transaction_ref.member_ref.sandik_ref,
        "logged_contribution_ref": sub_receipt.contribution_ref,
        "logged_installment_ref": sub_receipt.installment_ref,
        "logged_retracted_ref": sub_receipt.revenue_retracted_ref or sub_receipt.expense_retracted_ref,
        "logged_debt_ref": sub_receipt.debt_ref,
    }

    sub_receipt_logs = sub_receipt.logs_set
    sub_receipt_id = sub_receipt.id
    contribution = sub_receipt.contribution_ref
    installment = sub_receipt.installment_ref
    money_transaction = sub_receipt.money_transaction_ref
    amount = sub_receipt.amount
    flush()

    Log(web_user_ref=removed_by, type=Log.TYPE.SUB_RECEIPT.DELETE, detail=str(sub_receipt.to_dict()),
        **logged_ref_items)
    for log in sub_receipt_logs:
        log.detail += f", deleted_sub_receipt_id: {sub_receipt_id}"

    sub_receipt.delete()

    money_transaction.recalculate_is_fully_distributed()
    if contribution:
        contribution.recalculate_is_fully_paid()
    if installment:
        installment.recalculate_is_fully_paid()
        if money_transaction.member_ref.sandik_ref.is_type_with_trust_relationship():
            installment.debt_ref.update_pieces_of_debt()


def delete_money_transaction(money_transaction, removed_by):
    if money_transaction.sub_receipts_set.count() > 0:
        raise InvalidRemoveOperation("Alt işlemleri silinmemiş bir para işlemi silinemez!")

    logged_ref_items = {
        "logged_member_ref": money_transaction.member_ref,
        "logged_sandik_ref": money_transaction.member_ref.sandik_ref,
    }
    Log(web_user_ref=removed_by, type=Log.TYPE.MONEY_TRANSACTION.DELETE, detail=str(money_transaction.to_dict()),
        **logged_ref_items)
    for log in money_transaction.logs_set:
        log.detail += f", deleted_money_transaction_id: {money_transaction.id}"
    money_transaction.delete()


def delete_contribution(contribution, removed_by):
    if contribution.sub_receipts_set.count() > 0:
        raise InvalidRemoveOperation("Alt işlemleri silinmemiş bir aidat silinemez!")

    logged_ref_items = {
        "logged_share_ref": contribution.share_ref,
        "logged_member_ref": contribution.share_ref.member_ref,
        "logged_sandik_ref": contribution.share_ref.member_ref.sandik_ref,
    }
    Log(web_user_ref=removed_by, type=Log.TYPE.CONTRIBUTION.DELETE, detail=str(contribution.to_dict()),
        **logged_ref_items)
    for log in contribution.logs_set:
        log.detail += f", deleted_contribution_id: {contribution.id}"
    contribution.delete()


def delete_retracted_and_sub_receipts(retracted, removed_by):
    expense_sub_receipt_id = revenue_sub_receipt_id = None
    if retracted.expense_sub_receipt_ref:
        expense_sub_receipt_id = retracted.expense_sub_receipt_ref.id

    if retracted.revenue_sub_receipt_ref:
        revenue_sub_receipt_id = retracted.revenue_sub_receipt_ref.id

    logged_ref_items = {
        "logged_member_ref": retracted.expense_sub_receipt_ref.member_ref,
        "logged_sandik_ref": retracted.expense_sub_receipt_ref.member_ref.sandik_ref,
    }
    Log(web_user_ref=removed_by, type=Log.TYPE.RETRACTED.DELETE, detail=str(retracted.to_dict()),
        **logged_ref_items)
    for log in retracted.logs_set:
        log.detail += f", deleted_retracted_id: {retracted.id}"
    retracted.delete()

    if expense_sub_receipt_id:
        delete_sub_receipt(sub_receipt=get_sub_receipt(id=expense_sub_receipt_id), removed_by=removed_by)
    if revenue_sub_receipt_id:
        delete_sub_receipt(sub_receipt=get_sub_receipt(id=revenue_sub_receipt_id), removed_by=removed_by)


def delete_piece_of_debt(piece_of_debt, removed_by):
    """ DİKKAT: Bu fonksiyon ile borç parçası silindiğinde, diğer borç parçalarının miktarları düzenlenmez"""

    logged_ref_items = {
        "logged_debt_ref": piece_of_debt.debt_ref,
    }
    Log(web_user_ref=removed_by, type=Log.TYPE.PIECE_OF_DEBT.DELETE, detail=str(piece_of_debt.to_dict()),
        **logged_ref_items)
    for log in piece_of_debt.logs_set:
        log.detail += f", deleted_piece_of_debt_id: {piece_of_debt.id}"
    piece_of_debt.delete()


def delete_debt(debt, removed_by):
    logged_ref_items = {
        "logged_money_transaction_ref": debt.sub_receipt_ref.money_transaction_ref,
        "logged_member_ref": debt.member_ref,
        "logged_sandik_ref": debt.sandik_ref,
        "logged_share_ref": debt.share_ref,
    }
    Log(web_user_ref=removed_by, type=Log.TYPE.DEBT.DELETE, detail=str(debt.to_dict()),
        **logged_ref_items)
    for log in debt.logs_set:
        log.detail += f", deleted_debt_id: {debt.id}"
    debt.delete()


def delete_installment(installment, removed_by):
    """ DİKKAT: Bu fonksiyon ile taksit silindiğinde, kalan taksitlerin miktarları düzenlenmez"""

    logged_ref_items = {
        "logged_debt_ref": installment.debt_ref,
        "logged_share_ref": installment.debt_ref.share_ref,
        "logged_member_ref": installment.debt_ref.member_ref,
        "logged_sandik_ref": installment.debt_ref.sandik_ref,
    }
    Log(web_user_ref=removed_by, type=Log.TYPE.INSTALLMENT.DELETE, detail=str(installment.to_dict()),
        **logged_ref_items)
    for log in installment.logs_set:
        log.detail += f", deleted_installment_id: {installment.id}"
    installment.delete()


def get_contribution(*args, **kwargs) -> Contribution:
    return Contribution.get(*args, **kwargs)


def get_money_transaction(*args, **kwargs) -> MoneyTransaction:
    return MoneyTransaction.get(*args, **kwargs)


def get_debt(*args, **kwargs) -> Debt:
    return Debt.get(*args, **kwargs)


def get_sub_receipt(*args, **kwargs) -> SubReceipt:
    return SubReceipt.get(*args, **kwargs)


def select_contributions(*args, **kwargs):
    return Contribution.select(*args, **kwargs)


def select_installments(*args, **kwargs):
    return Installment.select(*args, **kwargs)


def select_money_transactions(*args, **kwargs):
    return MoneyTransaction.select(*args, **kwargs)


def select_debts(*args, **kwargs):
    return Debt.select(*args, **kwargs)


def select_sub_receipts(*args, **kwargs):
    return SubReceipt.select(*args, **kwargs)


def get_paid_contributions(whose):
    if isinstance(whose, Share):
        return select_contributions(lambda c: c.share_ref == whose and c.is_fully_paid)
    elif isinstance(whose, Member):
        return select_contributions(lambda c: c.share_ref.member_ref == whose and c.is_fully_paid)
    else:
        raise Exception("ERRCODE: 0008, MSG: 'whose' sadece 'Member' yada 'Share' olabilir.")


def get_unpaid_and_due_contributions(whose):
    """
    Ödenmemiş aidatları !!term'e gore sirali!! olarak doner
    """
    if isinstance(whose, Share):
        return select_contributions(
            lambda c: c.share_ref == whose and not c.is_fully_paid and c.term <= period_utils.current_period()
        ).order_by(lambda c: c.term)
    elif isinstance(whose, Member):
        return select_contributions(
            lambda c:
            c.share_ref.member_ref == whose and not c.is_fully_paid and c.term <= period_utils.current_period()
        ).order_by(lambda c: (c.term, c.share_ref.share_order_of_member))
    elif isinstance(whose, Sandik):
        return select_contributions(
            lambda c:
            c.share_ref.member_ref.sandik_ref == whose and not c.is_fully_paid and c.term <= period_utils.current_period()
        ).order_by(lambda c: (c.term, c.share_ref.share_order_of_member))
    else:
        raise Exception("ERRCODE: 0007, MSG: 'whose' sadece 'Member' yada 'Share' olabilir.")


def get_unpaid_and_due_installments(whose):
    """
    Ödenmemiş taksitler !!term'e gore sirali!! olarak doner
    """
    if isinstance(whose, Share):
        return select_installments(
            lambda i: i.share_ref == whose and not i.is_fully_paid and i.term <= period_utils.current_period()
        ).order_by(lambda c: c.term)
    elif isinstance(whose, Member):
        return select_installments(
            lambda i:
            i.share_ref.member_ref == whose and not i.is_fully_paid and i.term <= period_utils.current_period()
        ).order_by(lambda c: (c.term, c.share_ref.share_order_of_member))
    elif isinstance(whose, Sandik):
        return select_installments(
            lambda i:
            i.share_ref.member_ref.sandik_ref == whose and not i.is_fully_paid and i.term <= period_utils.current_period()
        ).order_by(lambda c: (c.term, c.share_ref.share_order_of_member))
    else:
        raise Exception("ERRCODE: 0006, MSG: 'whose' sadece 'Member' yada 'Share' olabilir.")


def get_future_and_unpaid_installments(whose):
    if isinstance(whose, Share):
        return select_installments(
            lambda i: i.share_ref == whose and not i.is_fully_paid and i.term > period_utils.current_period()
        )
    elif isinstance(whose, Member):
        return select_installments(
            lambda i: i.share_ref.member_ref == whose and not i.is_fully_paid and i.term > period_utils.current_period()
        )
    else:
        raise Exception("ERRCODE: 0003, MSG: 'whose' sadece 'Member' yada 'Share' olabilir.")


def sum_of_unpaid_and_due_contributions(whose):
    return select(c.get_unpaid_amount() for c in get_unpaid_and_due_contributions(whose=whose)).sum()


def sum_of_unpaid_and_due_installments(whose):
    return select(i.get_unpaid_amount() for i in get_unpaid_and_due_installments(whose=whose)).sum()


def sum_of_future_and_unpaid_installments(whose):
    return select(i.get_unpaid_amount() for i in get_future_and_unpaid_installments(whose=whose)).sum()


def total_paid_contributions_of_trusted_links(member):
    total = member.sum_of_paid_contributions()
    for link in member.accepted_trust_links():
        total += link.other_member(whose=member).sum_of_paid_contributions()
    return total


def total_paid_installments_of_trusted_links(member):
    total = member.get_paid_amount_of_loaned()
    for link in member.accepted_trust_links():
        total += link.other_member(whose=member).get_paid_amount_of_loaned()
    return total


def total_loaned_amount_of_trusted_links(member):
    total = member.get_loaned_amount()
    for link in member.accepted_trust_links():
        total += link.other_member(whose=member).get_loaned_amount()
    return total


def total_balance_of_trusted_links(member):
    return member.total_balance_from_accepted_trust_links()


def get_contribution_periods_with_amounts(sandik: Sandik = None, member: Member = None,
                                          first_period: str = None, last_period: str = None):
    if sandik is None and member is None:
        raise TransactionException("Hem sandik hem de member boş olamaz")

    first_period = first_period or period_utils.date_to_period(sandik.date_of_opening)
    last_period = last_period or period_utils.current_period()
    periods = period_utils.get_periods_between_two_period(first_period=first_period, last_period=last_period)
    periods_with_amounts = {}
    for period in periods:
        periods_with_amounts[period] = distinct(
            c.amount for c in Contribution if
            (not sandik or c.sandik_ref == sandik)
            and (not member or c.member_ref == member) and c.term == period
        )[:]
    return periods_with_amounts


def get_first_contribution_period(share: Share):
    first_period = select(c.term for c in Contribution if c.share_ref == share).min()
    return first_period

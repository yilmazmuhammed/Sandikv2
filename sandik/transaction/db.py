from math import ceil

from pony.orm import select

from sandik.utils.db_models import Contribution, Share, Member, Installment, MoneyTransaction, Log, SubReceipt, Debt, \
    PieceOfDebt, Retracted
from sandik.utils import period as period_utils


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
    log = Log(web_user_ref=created_by, type=Log.TYPE.INSTALLMENT.CREATE, **logged_ref_items)
    return Installment(logs_set=log, debt_ref=debt, share_ref=debt.share_ref, **kwargs)


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


def get_contribution(*args, **kwargs) -> Contribution:
    return Contribution.get(*args, **kwargs)


def select_contributions(*args, **kwargs):
    return Contribution.select(*args, **kwargs)


def select_installments(*args, **kwargs):
    return Installment.select(*args, **kwargs)


def select_money_transactions(*args, **kwargs):
    return MoneyTransaction.select(*args, **kwargs)


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
        return select_contributions(
            lambda i:
            i.share_ref.member_ref == whose and not i.is_fully_paid and i.term <= period_utils.current_period()
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


def get_untreated_money_transactions(member):
    return select_money_transactions(lambda mt: mt.member_ref == member and mt.is_fully_distributed is False)


def sum_of_unpaid_and_due_contributions(whose):
    return select(c.unpaid_amount() for c in get_unpaid_and_due_contributions(whose=whose)).sum()
    if isinstance(whose, Share):
        return select(c.unpaid_amount() for c in Contribution if
                      c.share_ref == whose and not c.is_fully_paid and c.term <= current_period()).sum()
    elif isinstance(whose, Member):
        return select(c.unpaid_amount() for c in Contribution if
                      c.share_ref.member_ref == whose and not c.is_fully_paid and c.term <= current_period()).sum()
    else:
        raise Exception("ERRCODE: 0005, MSG: 'whose' sadece 'Member' yada 'Share' olabilir.")


def sum_of_unpaid_and_due_installments(whose):
    return select(c.unpaid_amount() for c in get_unpaid_and_due_installments(whose=whose)).sum()
    if isinstance(whose, Share):
        return select(i.unpaid_amount() for i in Installment if
                      i.share_ref == whose and not i.is_fully_paid and i.term <= current_period()).sum()
    elif isinstance(whose, Member):
        return select(i.unpaid_amount() for i in Installment if
                      i.share_ref.member_ref == whose and not i.is_fully_paid and i.term <= current_period()).sum()
    else:
        raise Exception("ERRCODE: 0004, MSG: 'whose' sadece 'Member' yada 'Share' olabilir.")


def sum_of_future_and_unpaid_installments(whose):
    return select(c.unpaid_amount() for c in get_future_and_unpaid_installments(whose=whose)).sum()
    if isinstance(whose, Share):
        return select(i.unpaid_amount() for i in Installment if
                      i.share_ref == whose and not i.is_fully_paid and i.term > current_period()).sum()
    elif isinstance(whose, Member):
        return select(i.unpaid_amount() for i in Installment if
                      i.share_ref.member_ref == whose and not i.is_fully_paid and i.term > current_period()).sum()
    else:
        raise Exception("ERRCODE: 0009, MSG: 'whose' sadece 'Member' yada 'Share' olabilir.")


def sum_of_untreated_money_transactions(member):
    return select(mt.untreated_amount() for mt in get_untreated_money_transactions(member=member)).sum()
    return select(mt.untreated_amount() for mt in MoneyTransaction if
                  mt.member_ref == member and not mt.is_fully_distributed).sum()


def sign_money_transaction_as_fully_distributed(money_transaction, signed_by):
    Log(web_user_ref=signed_by, type=Log.TYPE.MONEY_TRANSACTION.SIGN_FULLY_DISTRIBUTED,
        logged_money_transaction_ref=money_transaction, logged_member_ref=money_transaction.member_ref,
        logged_sandik_ref=money_transaction.member_ref.sandik_ref)
    money_transaction.set(is_fully_distributed=True)


def create_installments_of_debt(debt, created_by):
    debt_amount = debt.amount
    number_of_installment = debt.number_of_installment
    start_period = debt.start_period

    remaining_amount = debt_amount
    installment_amount = ceil(debt_amount / number_of_installment)
    for i in range(number_of_installment):
        if remaining_amount <= 0:
            raise Exception(f"ERRCODE: 0015, RA: {remaining_amount}, "
                            f"MSG: Beklenmedik bir hata ile karşılaşıldı. Düzeltilmesi için "
                            f"lütfen site yöneticisi ile iletişime geçerek ERRCODE'u ve RA'yı söyleyiniz.")

        temp_amount = installment_amount if remaining_amount >= installment_amount else remaining_amount
        installment_term = period_utils.get_last_period(start_period, i + 1)
        create_installment(amount=temp_amount, term=installment_term, debt=debt, created_by=created_by)
        remaining_amount -= temp_amount

    if remaining_amount != 0:
        raise Exception(f"ERRCODE: 0014, RA: {remaining_amount}, "
                        f"MSG: Beklenmedik bir hata ile karşılaşıldı. Düzeltilmesi için "
                        f"lütfen site yöneticisi ile iletişime geçerek ERRCODE'u ve RA'yı söyleyiniz.")

    return debt.installments_set


def create_piece_of_debts(debt, created_by):
    debt_amount = debt.amount

    member = debt.share_ref.member_ref
    trusted_links = member.accepted_trust_links()
    sorted_trusted_links = sorted(trusted_links, key=lambda tl: tl.other_member(whose=member).balance)

    remaining_amount = debt_amount

    # Önce kendinden borç almalı
    temp_amount = member.balance if member.balance <= remaining_amount else remaining_amount
    create_piece_of_debt(member=member, debt=debt, amount=temp_amount,
                         trust_relationship_for_log=None, created_by=created_by)
    remaining_amount -= temp_amount

    for i, link in enumerate(sorted_trusted_links):
        if remaining_amount <= 0:
            raise Exception(f"ERRCODE: 0016, RA: {remaining_amount}, "
                            f"MSG: Beklenmedik bir hata ile karşılaşıldı. Düzeltilmesi için "
                            f"lütfen site yöneticisi ile iletişime geçerek ERRCODE'u ve RA'yı söyleyiniz.")

        temp_amount = ceil(remaining_amount / (len(sorted_trusted_links) - i))
        temp_amount = temp_amount if temp_amount <= remaining_amount else remaining_amount

        other_member = link.other_member(whose=member)
        temp_amount = temp_amount if temp_amount <= other_member.balance else other_member.balance

        create_piece_of_debt(member=other_member, debt=debt, amount=temp_amount,
                             trust_relationship_for_log=link, created_by=created_by)
        remaining_amount -= temp_amount

    if remaining_amount != 0:
        raise Exception(f"ERRCODE: 0017, RA: {remaining_amount}, "
                        f"MSG: Beklenmedik bir hata ile karşılaşıldı. Düzeltilmesi için "
                        f"lütfen site yöneticisi ile iletişime geçerek ERRCODE'u ve RA'yı söyleyiniz.")

    return debt.piece_of_debts_set


def create_debt(amount, share, number_of_installment, start_period, money_transaction, created_by) -> Debt:
    due_term = period_utils.get_last_period(start_period, number_of_installment)
    logged_ref_items = {
        "logged_money_transaction_ref": money_transaction,
        "logged_member_ref": money_transaction.member_ref,
        "logged_sandik_ref": money_transaction.member_ref.sandik_ref,
        "logged_share_ref": share,
    }
    sub_receipt = create_sub_receipt(
        debt_ref=Debt(
            amount=amount, share_ref=share,
            number_of_installment=number_of_installment, starting_term=start_period, due_term=due_term,
            logs_set=Log(web_user_ref=created_by, type=Log.TYPE.DEBT.CREATE, **logged_ref_items)),
        money_transaction=money_transaction, amount=amount, is_auto=True, created_by=created_by
    )
    debt = sub_receipt.debt_ref

    create_installments_of_debt(debt=debt, created_by=created_by)
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
        logs_set=Log(web_user_ref=created_by, type=Log.TYPE.DEBT.CREATE, **logged_ref_items)
    )

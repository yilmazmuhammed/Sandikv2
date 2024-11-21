import os
from datetime import datetime

from flask import url_for

from sandik.bot.sms import SmsBot
from sandik.general import db as general_db
from sandik.sandik import db
from sandik.sandik.exceptions import MaxShareCountExceed, NotActiveMemberException, ThereIsUnpaidDebtOfMemberException, \
    ThereIsUnpaidAmountOfLoanedException, NotActiveShareException, ThereIsUnpaidDebtOfShareException, InvalidSmsType, \
    InvalidRuleVariable, InvalidRuleCharacter, InvalidArgument, RuleOperatorCountException, ThereIsNoMember, \
    ThereIsNoShare
from sandik.sandik.exceptions import UpdateMemberException
from sandik.transaction import utils as transaction_utils, db as transaction_db
from sandik.utils import period as period_utils, sandik_preferences
from sandik.utils.db_models import Member, Share, MoneyTransaction, TrustRelationship, SmsPackage, Sandik, SandikRule


def add_share_to_member(member, added_by, create_contributions=True, force=False, **kwargs):
    if not force:
        max_share_count = sandik_preferences.get_max_number_of_share(sandik=member.sandik_ref)
        if member.get_active_shares().count() >= max_share_count:
            raise MaxShareCountExceed(f"Bir üyenin en fazla {max_share_count} adet hissesi olabilir.")

    order = db.get_last_share_order(member) + 1
    share = db.create_share(member=member, created_by=added_by, share_order_of_member=order, **kwargs)
    if create_contributions:
        transaction_utils.create_due_contributions_for_member(member=member, created_by=added_by)
    return share


def create_trust_relationships_with_all_members_of_sandik(member, created_by):
    sandik = member.sandik_ref
    for m in sandik.members_set:
        if member is not m:
            trust_relationship = db.get_trust_relationship_between_two_member(member1=m, member2=member)
            if not trust_relationship:
                pass
            elif trust_relationship.status == TrustRelationship.STATUS.ACCEPTED:
                continue
            elif trust_relationship.status == TrustRelationship.STATUS.WAITING:
                db.remove_trust_relationship_request(trust_relationship=trust_relationship, rejected_by=created_by)

            db.create_trust_relationship(requester_member=member, receiver_member=m, created_by=created_by,
                                         status=TrustRelationship.STATUS.ACCEPTED)


def create_trust_relationships_between_all_members_of_sandik(sandik, created_by):
    for member in sandik.members_set:
        create_trust_relationships_with_all_members_of_sandik(member=member, created_by=created_by)


def remove_trust_relationships_of_member_with_all_members_of_sandik(member, removed_by):
    for tr in member.accepted_trust_links():
        db.remove_trust_relationship_request(trust_relationship=tr, rejected_by=removed_by)
    for tr in member.waiting_trust_links():
        db.remove_trust_relationship_request(trust_relationship=tr, rejected_by=removed_by)


def remove_trust_relationships_from_sandik(sandik, removed_by):
    for member in sandik.members_set:
        remove_trust_relationships_of_member_with_all_members_of_sandik(member=member, removed_by=removed_by)


def add_member_to_sandik(sandik, web_user, date_of_membership, contribution_amount, detail,
                         number_of_share, added_by):
    member = db.create_member(sandik=sandik, web_user=web_user, created_by=added_by,
                              contribution_amount=contribution_amount, detail=detail,
                              date_of_membership=date_of_membership)
    for i in range(number_of_share):
        add_share_to_member(member=member, added_by=added_by, date_of_opening=date_of_membership)

    # TODO Klasik sandıkta güven bağı oluşturulmasına gerek var mı?
    if sandik.is_type_classic():
        create_trust_relationships_with_all_members_of_sandik(member=member, created_by=added_by)

    return member


def update_member_of_sandik(member, updated_by, date_of_membership=None, **kwargs):
    if date_of_membership and date_of_membership != member.date_of_membership:
        if date_of_membership < member.date_of_membership:
            for share in member.get_active_shares().filter(date_of_opening=member.date_of_membership):
                if share.date_of_opening == member.date_of_membership:
                    db.update_share(share=share, updated_by=updated_by, date_of_opening=date_of_membership)
            transaction_utils.create_due_contributions_for_member(member=member, created_by=updated_by)
        else:
            # TODO ödenmemiş aidatları sil
            raise UpdateMemberException("Üyelik tarihi ileriye alınamaz.")
        kwargs["date_of_membership"] = date_of_membership

    return db.update_member(member=member, updated_by=updated_by, **kwargs)


def update_sandik_type(sandik, sandik_type: int, updated_by):
    if sandik.type == Sandik.TYPE.CLASSIC and sandik_type == Sandik.TYPE.WITH_TRUST_RELATIONSHIP:
        remove_trust_relationships_from_sandik(sandik=sandik, removed_by=updated_by)
    elif sandik.type == Sandik.TYPE.WITH_TRUST_RELATIONSHIP and sandik_type == Sandik.TYPE.CLASSIC:
        create_trust_relationships_between_all_members_of_sandik(sandik=sandik, created_by=updated_by)
    db.update_sandik(sandik=sandik, type=sandik_type, updated_by=updated_by)


def update_sandik(sandik: Sandik, updated_by, contribution_amount, **kwargs):
    if sandik.contribution_amount != contribution_amount:
        for member in sandik.get_active_members():
            update_member_of_sandik(member=member, updated_by=updated_by, contribution_amount=contribution_amount)
    return db.update_sandik(sandik=sandik, updated_by=updated_by, contribution_amount=contribution_amount, **kwargs)


def confirm_membership_application(sandik, web_user, confirmed_by):
    member = db.create_member(sandik=sandik, web_user=web_user, confirmed_by=confirmed_by,
                              contribution_amount=sandik.contribution_amount)
    add_share_to_member(member=member, added_by=confirmed_by)

    if sandik.is_type_classic():
        create_trust_relationships_with_all_members_of_sandik(member=member, created_by=confirmed_by)

    return member


def send_sms_from_sandik(sandik, sms_type, created_by):
    if int(sms_type) == SmsPackage.TYPE.SANDIK.THERE_IS_UNCONFIRMED_TRUST_RELATIONSHIP_REQUEST:
        text = f"{sandik.name.upper()}\n" \
               f"Bekleyen güven bağı isteğiniz var. İncelemek ve onaylamak için: " \
               f"{url_for('sandik_page_bp.trust_links_page', sandik_id=sandik.id, _external=True)}"
        web_users = []
        for member in sandik.get_active_members():
            if member.waiting_received_trust_relationships_request().count() > 0:
                web_users.append(member.web_user_ref)
    else:
        raise InvalidSmsType("Geçersiz sms türü girildi. Lütfen sms türünü listeden seçiniz.")
    sms_package = db.create_sms_package(text=text, header=os.getenv("SMS_BOT_DEFAULT_MESSAGE_HEADER"),
                                        sandik_ref=sandik, web_users_set=web_users,
                                        type=sms_type, created_by=created_by)
    sms_bot = SmsBot()
    sms_bot.send_sms_package(sms_package=sms_package)
    return sms_package


class Notification:
    class MembershipApplication:

        @staticmethod
        def send_confirming_notification(sandik, web_user):
            for member in sandik.get_active_members():
                if web_user is not member.web_user_ref:
                    general_db.create_notification(
                        to_web_user=member.web_user_ref,
                        title=f"{web_user.name_surname} üyelik başvurusu onaylandı.", text=sandik.name,
                        url=url_for("sandik_page_bp.trust_links_page", sandik_id=sandik.id)
                    )
            general_db.create_notification(
                to_web_user=web_user, title="Üyelik başvurunuz onaylandı", text=sandik.name,
                url=url_for("sandik_page_bp.sandik_summary_for_member_page", sandik_id=sandik.id)
            )

        @staticmethod
        def send_adding_share_notification(sandik, web_user):
            general_db.create_notification(
                to_web_user=web_user, title="Yeni hisse açıldı.", text=sandik.name,
                url=url_for("sandik_page_bp.sandik_summary_for_member_page", sandik_id=sandik.id)
            )

        @staticmethod
        def send_member_adding_notification(sandik, web_user):
            for member in sandik.get_active_members():
                if web_user is not member.web_user_ref:
                    general_db.create_notification(
                        to_web_user=member.web_user_ref,
                        title=f"{web_user.name_surname} sandığa katıldı.", text=sandik.name,
                        url=url_for("sandik_page_bp.trust_links_page", sandik_id=sandik.id)
                    )
            general_db.create_notification(
                to_web_user=web_user, title="Sandık üyeliğiniz oluşturuldu", text=sandik.name,
                url=url_for("sandik_page_bp.sandik_summary_for_member_page", sandik_id=sandik.id)
            )

        @staticmethod
        def send_apply_notification(sandik, applied_by):
            for member in sandik.get_active_members():
                general_db.create_notification(
                    to_web_user=member.web_user_ref,
                    title=f"{applied_by.name_surname} üyelik başvurusunda bulundu.", text=sandik.name,
                    url=url_for("sandik_page_bp.sandik_detail_page", sandik_id=sandik.id)
                )


def send_notification_for_trust_relationship(trust_relationship):
    # TODO class'a taşı
    # TODO yöneticilere de bildirim gönder
    requester_name = trust_relationship.requester_member_ref.web_user_ref.name_surname
    receiver_web_user = trust_relationship.receiver_member_ref.web_user_ref
    sandik = trust_relationship.receiver_member_ref.sandik_ref
    return general_db.create_notification(to_web_user=receiver_web_user,
                                          title=f"{requester_name} güven bağı isteği gönderdi.",
                                          text=sandik.name,
                                          url=url_for("sandik_page_bp.trust_links_page", sandik_id=sandik.id))


def get_member_summary_page(member):
    sum_of_unpaid_and_due_payments = transaction_utils.sum_of_unpaid_and_due_payments(whose=member)
    sum_of_future_and_unpaid_payments = transaction_utils.sum_of_future_and_unpaid_payments(whose=member)
    sum_of_payments = sum_of_unpaid_and_due_payments + sum_of_future_and_unpaid_payments
    my_upcoming_payments = transaction_utils.get_payments(
        whose=member, is_fully_paid=False, is_due=True
    ) + transaction_utils.get_payments(
        whose=member, is_fully_paid=False, periods=[period_utils.next_period()]
    )
    my_latest_money_transactions = transaction_utils.get_latest_money_transactions(whose=member, periods_count=2)
    if member.sandik_ref.is_type_classic():
        trusted_links = {
            "total_paid_contributions": member.sandik_ref.sum_of_contributions(),
            "total_loaned_amount": member.sandik_ref.sum_of_debts(),
            "total_paid_installments": member.sandik_ref.sum_of_paid_installments(),
            "total_balance": member.sandik_ref.get_final_status(),
        }
    elif member.sandik_ref.is_type_with_trust_relationship():
        trusted_links = {
            "total_paid_contributions": transaction_db.total_paid_contributions_of_trusted_links(member=member),
            "total_loaned_amount": transaction_db.total_loaned_amount_of_trusted_links(member=member),
            "total_balance": transaction_db.total_balance_of_trusted_links(member=member),
            "total_paid_installments": transaction_db.total_paid_installments_of_trusted_links(member=member)
        }
    else:
        raise Exception("Bilinmeyen sandık tipi")

    return {
        "sum_of_unpaid_and_due_payments": sum_of_unpaid_and_due_payments,
        "sum_of_payments": sum_of_payments,
        "my_upcoming_payments": my_upcoming_payments,
        "my_latest_money_transactions": my_latest_money_transactions,
        "trusted_links": trusted_links,
    }


def remove_member_from_sandik(member: Member, removed_by):
    if not member.is_active:
        raise NotActiveMemberException("Silinmek istenen üye zaten aktif üye değil.", create_log=True)

    if member.get_unpaid_debts().count() > 0:
        raise ThereIsUnpaidDebtOfMemberException("Silinmek istenen üyenin ödenmemiş borcu var.", create_log=True)

    if member.sandik_ref.is_type_with_trust_relationship():
        if member.get_unpaid_amount_of_loaned() > 0:
            # TODO Sandık kurallarının güncellenmesi gerekli
            raise ThereIsUnpaidAmountOfLoanedException("Üyenin verdiği borçlardan ödenmesi tamamlanmamış olan borç var",
                                                       create_log=True)

    total_amount_to_be_refunded = member.sum_of_paid_contributions() + member.total_of_undistributed_amount()
    refunded_money_transaction = transaction_db.create_money_transaction(
        member_ref=member, amount=total_amount_to_be_refunded, type=MoneyTransaction.TYPE.EXPENSE,
        detail="Üye ayrılışı", creation_type=MoneyTransaction.CREATION_TYPE.BY_AUTO, is_fully_distributed=False,
        created_by=removed_by
    )

    # Hisseler kaldiriliyor ve odenen aidatlar uyeye geri veriliyor
    for share in member.get_active_shares():
        remove_share_from_member(share=share, removed_by=removed_by,
                                 refunded_money_transaction=refunded_money_transaction)

    # İsleme konmamis miktarlar uyeye geri iade ediliyor
    for mt in member.get_revenue_money_transactions_are_not_fully_distributed():
        undistributed_amount = mt.get_undistributed_amount()
        transaction_utils.borrow_from_untreated_amount(
            untreated_money_transaction=mt, amount=undistributed_amount, money_transaction=refunded_money_transaction,
            created_by=removed_by
        )

    # Üye pasif üyeye dönüştürülüyor
    db.update_member(member=member, updated_by=removed_by, is_active=False)

    # Güven bağları siliniyor
    remove_trust_relationships_of_member_with_all_members_of_sandik(member=member, removed_by=removed_by)

    return refunded_money_transaction


def remove_share_from_member(share: Share, removed_by, refunded_money_transaction=None, removed_date=datetime.today()):
    if not share.is_active:
        raise NotActiveShareException("Silinmek istenen hisse zaten aktif hisse değil.", create_log=True)

    if share.get_unpaid_debts().count() > 0:
        raise ThereIsUnpaidDebtOfShareException("Silinmek istenen hissenin ödenmemiş borcu var.", create_log=True)

    refunded_amount = share.sum_of_paid_contributions()
    refunded_contribution = transaction_db.create_contribution(
        share=share, period="9999-01", amount=-refunded_amount, created_by=removed_by,
    )

    if not refunded_money_transaction:
        refunded_money_transaction = transaction_db.create_money_transaction(
            member_ref=share.member_ref, amount=refunded_amount, type=MoneyTransaction.TYPE.EXPENSE,
            detail="Hisse kapatılması", creation_type=MoneyTransaction.CREATION_TYPE.BY_AUTO,
            is_fully_distributed=False, created_by=removed_by, date=removed_date
        )

    transaction_db.create_sub_receipt(
        money_transaction=refunded_money_transaction, contribution_ref=refunded_contribution,
        amount=refunded_amount, is_auto=True, created_by=removed_by
    )

    db.update_share(share=share, updated_by=removed_by, is_active=False)

    transaction_utils.remove_unpaid_contributions(share=share, removed_by=removed_by)

    return refunded_money_transaction


def rule_formula_validator(formula_string, variables, operators, formula_type):
    if formula_type not in SandikRule.FORMULA_TYPE.strings.keys():
        raise InvalidArgument(f"type is {formula_type} not in {SandikRule.FORMULA_TYPE.strings.keys()}")

    data = formula_string.replace(' ', '')
    operators = sorted(operators, reverse=True, key=len)
    i = 0
    comp_operator_counts = 0
    while i < len(data):
        if data[i] == "{":
            variable = data[i + 1:].split("}")[0]
            if variable not in variables:
                raise InvalidRuleVariable("{" + variable + "}")
            i += 1 + len(variable) + 1
            continue
        elif data[i].isnumeric():
            i += 1
            continue

        for operator in operators:
            if data[i: i + len(operator)] == operator:
                i += len(operator)
                if operator in SandikRule.COMPARISON_OPERATOR.strings.keys():
                    comp_operator_counts += 1
                break
        else:
            raise InvalidRuleCharacter(i)
    if formula_type == SandikRule.FORMULA_TYPE.VALUE and comp_operator_counts != 0:
        raise RuleOperatorCountException("Değer formülünde karşılaştırma işareti bulunamaz")
    if formula_type == SandikRule.FORMULA_TYPE.CONDITION and comp_operator_counts > 1:
        raise RuleOperatorCountException("Koşul formülünde en fazla 1 tane karşılaştırma işareti bulunmalıdır.")


def add_sandik_rule_to_sandik(condition_formula, value_formula, type, sandik, **kwargs):
    try:
        comp_ops = list(SandikRule.COMPARISON_OPERATOR.strings.keys())
        arith_ops = list(SandikRule.ARITHMETIC_OPERATOR.strings.keys())
        rule_formula_validator(formula_string=condition_formula, variables=SandikRule.FORMULA_VARIABLE.strings.keys(),
                               operators=comp_ops + arith_ops, formula_type=SandikRule.FORMULA_TYPE.CONDITION)
        rule_formula_validator(formula_string=value_formula, variables=SandikRule.FORMULA_VARIABLE.strings.keys(),
                               operators=comp_ops + arith_ops, formula_type=SandikRule.FORMULA_TYPE.VALUE)
    except InvalidRuleVariable as e:
        raise InvalidRuleVariable(f"Sandık kuralı geçersiz değişken veya geçersiz karakter içeriyor: {e}")

    order = db.get_last_rule_order(sandik=sandik, type=type) + 1
    return db.create_sandik_rule(condition_formula=condition_formula, value_formula=value_formula, type=type,
                                 order=order, sandik=sandik, **kwargs)


def validate_whose_of_sandik(sandik, share_id: int = None, member_id: int = None):
    member = share = None
    share_kwargs = {}
    if member_id is not None:
        member = db.get_member(id=member_id, sandik_ref=sandik)
        if not member:
            raise ThereIsNoMember("Üye açılan listeden seçilmelidir.")
        share_kwargs["member_ref"] = member

    if share_id is not None:
        share = db.get_share(id=share_id, **share_kwargs)
        if not share or share.sandik_ref != sandik:
            raise ThereIsNoShare("Hisse, üye seçildikten sonra gelen listeden seçilmelidir.")

    return member, share


def get_borrowing_priority(sandik):
    shares = sandik.get_shares(all_shares=False, is_active=True)
    ordered_shares: list = shares.order_by(lambda s: s.date_of_opening)[:][:]

    sub_receipts = transaction_utils.get_sub_receipts(whose=sandik)[:]

    last_status = {share: {"contributions": 0, "unpaid_debts": 0} for share in ordered_shares}

    siralama_degistiren_islemler = [(datetime.combine(s.date_of_opening, datetime.min.time()), s) for s in
                                    ordered_shares]

    for sr in sub_receipts:
        share = sr.share_ref or sr.debt_ref.share_ref
        if last_status.get(share):
            if sr.contribution_ref is not None:
                last_status[share]["contributions"] += sr.amount
            elif sr.debt_ref is not None:
                last_status[share]["unpaid_debts"] += sr.amount
                if last_status[share]["unpaid_debts"] > last_status[share]["contributions"]:
                    siralama_degistiren_islemler.append((sr.creation_time, share))
            elif sr.installment_ref is not None:
                last_status[share]["unpaid_debts"] -= sr.amount

    siralama_degistiren_islemler = sorted(siralama_degistiren_islemler, key=lambda i: i[0])

    for d, share in siralama_degistiren_islemler:
        ordered_shares.remove(share)
        ordered_shares.append(share)

    return ordered_shares

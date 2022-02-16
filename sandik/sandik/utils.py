from datetime import date

from flask import url_for

from sandik.general import db as general_db
from sandik.sandik import db
from sandik.sandik.exceptions import UpdateMemberException, MaxShareCountExceed
from sandik.transaction import utils as transaction_utils, db as transaction_db
from sandik.utils import period as period_utils, sandik_preferences
from sandik.sandik.exceptions import UpdateMemberException
from sandik.transaction import utils as transaction_utils, db as transaction_db
from sandik.utils import period as period_utils


def add_share_to_member(member, added_by, **kwargs):
    max_share_count = sandik_preferences.get_max_number_of_share(sandik=member.sandik_ref)
    if member.shares_set.select(lambda s: s.is_active).count() >= max_share_count:
        raise MaxShareCountExceed(f"Bir üyenin en fazla {max_share_count} adet hissesi olabilir.")

    order = db.get_last_share_order(member) + 1
    share = db.create_share(member=member, created_by=added_by, share_order_of_member=order, **kwargs)
    transaction_utils.create_due_contributions_for_the_share(share, created_by=added_by)
    return share


def add_member_to_sandik(sandik, web_user, date_of_membership, contribution_amount, detail,
                         number_of_share, added_by):
    member = db.create_member(sandik=sandik, web_user=web_user, created_by=added_by,
                              contribution_amount=contribution_amount, detail=detail,
                              date_of_membership=date_of_membership)
    for i in range(number_of_share):
        add_share_to_member(member=member, added_by=added_by, date_of_opening=date_of_membership)

    return member


def update_member_of_sandik(member, updated_by, date_of_membership=None, **kwargs):
    if date_of_membership and date_of_membership != member.date_of_membership:
        if date_of_membership < member.date_of_membership:
            for share in member.shares_set.filter(date_of_opening=member.date_of_membership):
                db.update_share(share=share, updated_by=updated_by, date_of_opening=date_of_membership)
                transaction_utils.create_due_contributions_for_the_share(share, created_by=updated_by)
        else:
            # TODO ödenmemiş aidatları sil
            raise UpdateMemberException("Üyelik tarihi ileriye alınamaz.")
        kwargs["date_of_membership"] = date_of_membership

    return db.update_member(member=member, updated_by=updated_by, **kwargs)


def confirm_membership_application(sandik, web_user, confirmed_by):
    member = db.create_member(sandik=sandik, web_user=web_user, confirmed_by=confirmed_by,
                              contribution_amount=sandik.contribution_amount)
    add_share_to_member(member=member, added_by=confirmed_by)
    return member


class Notification:
    class MembershipApplication:

        @staticmethod
        def send_confirming_notification(sandik, web_user):
            for member in sandik.members_set:
                if web_user is not member.web_user_ref:
                    general_db.create_notification(
                        to_web_user=member.web_user_ref,
                        title=f"{web_user.name_surname} üyelik başvurusu onaylandı.", text=sandik.name,
                        url=url_for("sandik_page_bp.sandik_detail_page", sandik_id=sandik.id)
                    )
            general_db.create_notification(
                to_web_user=web_user, title=f"Üyelik başvurunuz onaylandı", text=sandik.name,
                url=url_for("sandik_page_bp.sandik_summary_for_member_page", sandik_id=sandik.id)
            )

        @staticmethod
        def send_adding_share_notification(sandik, web_user):
            general_db.create_notification(
                to_web_user=web_user, title=f"Yeni hisse açıldı.", text=sandik.name,
                url=url_for("sandik_page_bp.sandik_summary_for_member_page", sandik_id=sandik.id)
            )

        @staticmethod
        def send_member_adding_notification(sandik, web_user):
            for member in sandik.members_set:
                if web_user is not member.web_user_ref:
                    general_db.create_notification(
                        to_web_user=member.web_user_ref,
                        title=f"{web_user.name_surname} sandığa katıldı.", text=sandik.name,
                        url=url_for("sandik_page_bp.sandik_detail_page", sandik_id=sandik.id)
                    )
            general_db.create_notification(
                to_web_user=web_user, title=f"Sandık üyeliğiniz oluşturuldu", text=sandik.name,
                url=url_for("sandik_page_bp.sandik_summary_for_member_page", sandik_id=sandik.id)
            )

        @staticmethod
        def send_apply_notification(sandik, applied_by):
            for member in sandik.members_set:
                general_db.create_notification(
                    to_web_user=member.web_user_ref,
                    title=f"{applied_by.name_surname} üyelik başvurusunda bulundu.", text=sandik.name,
                    url=url_for("sandik_page_bp.sandik_detail_page", sandik_id=sandik.id)
                )


def send_notification_for_trust_relationship(trust_relationship):
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
    trusted_links = {
        "total_paid_contributions": transaction_db.total_paid_contributions_of_trusted_links(member=member),
        "total_loaned_amount": transaction_db.total_loaned_amount_of_trusted_links(member=member),
        "total_balance": transaction_db.total_balance_of_trusted_links(member=member),
        "total_paid_installments": transaction_db.total_paid_installments_of_trusted_links(member=member)
    }
    return {
        "sum_of_unpaid_and_due_payments": sum_of_unpaid_and_due_payments,
        "sum_of_payments": sum_of_payments,
        "my_upcoming_payments": my_upcoming_payments,
        "my_latest_money_transactions": my_latest_money_transactions,
        "trusted_links": trusted_links,
    }

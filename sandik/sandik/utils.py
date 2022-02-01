from flask import url_for

from sandik.general import db as general_db
from sandik.sandik import db
from sandik.transaction import utils as transaction_utils


def add_share_to_member(member, added_by):
    order = db.get_last_share_order(member) + 1
    return db.create_share(member=member, created_by=added_by, share_order_of_member=order)


def confirm_membership_application(sandik, web_user, confirmed_by):
    iban = web_user.get_primary_bank_account().iban
    member = db.create_member(sandik=sandik, web_user=web_user, confirmed_by=confirmed_by, iban=iban,
                              contribution_amount=sandik.contribution_amount)
    share = add_share_to_member(member=member, added_by=confirmed_by)
    transaction_utils.create_due_contributions_for_the_share(share, created_by=confirmed_by)
    return None


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
                url=url_for("sandik_page_bp.sandik_summary_page", sandik_id=sandik.id)
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

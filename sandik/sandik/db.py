from datetime import datetime

from pony.orm import flush, select

from sandik.sandik.exceptions import TrustRelationshipAlreadyExist, TrustRelationshipCreationException, \
    MembershipApplicationAlreadyExist, WebUserIsAlreadyMember
from sandik.utils.db_models import Sandik, Log, SandikAuthorityType, Member, Share, TrustRelationship


def save():
    flush()


def create_sandik_authority_type(created_by, **kwargs) -> SandikAuthorityType:
    log = Log(web_user_ref=created_by, type=Log.TYPE.CREATE)
    return SandikAuthorityType(logs_set=log, **kwargs)


def create_sandik(created_by, **kwargs) -> Sandik:
    log = Log(web_user_ref=created_by, type=Log.TYPE.CREATE)
    sandik = Sandik(logs_set=log, **kwargs)
    create_sandik_authority_type(created_by=created_by, is_admin=True, name="Yönetici", sandik_ref=sandik,
                                 web_users_set=created_by)
    return sandik


def get_sandik(**kwargs) -> Sandik:
    return Sandik.get(**kwargs)


def sandiks_form_choices():
    choices = [(s.id, s.name) for s in Sandik.select()]
    return choices


def apply_for_membership(sandik, applied_by):
    if applied_by in sandik.applicant_web_users_set.select():
        raise MembershipApplicationAlreadyExist()
    if get_member(sandik_ref=sandik, web_user_ref=applied_by):
        raise WebUserIsAlreadyMember()
    Log(web_user_ref=applied_by, type=Log.TYPE.SANDIK.APPLY_FOR_MEMBERSHIP, logged_sandik_ref=sandik,
        logged_web_user_ref=applied_by)
    sandik.applicant_web_users_set.add(applied_by)


def reject_membership_application(sandik, web_user, rejected_by) -> Sandik:
    sandik.applicant_web_users_set.remove(web_user)
    Log(web_user_ref=rejected_by, type=Log.TYPE.SANDIK.REJECT_MEMBERSHIP_APPLICATION,
        logged_web_user_ref=web_user, logged_sandik_ref=sandik)


def create_member(sandik, web_user, created_by=None, confirmed_by=None, **kwargs) -> Member:
    if get_member(sandik_ref=sandik, web_user_ref=web_user):
        raise WebUserIsAlreadyMember()

    logs = []
    if confirmed_by:
        logs.append(Log(web_user_ref=confirmed_by, type=Log.TYPE.SANDIK.CONFIRM_MEMBERSHIP_APPLICATION,
                        logged_sandik_ref=sandik, logged_web_user_ref=web_user,
                        detail=f"Üyelik başvurusu onaylandı: '{web_user.name_surname}'"))
    sandik.applicant_web_users_set.remove(web_user)
    logs.append(Log(web_user_ref=created_by or confirmed_by, type=Log.TYPE.CREATE, logged_sandik_ref=sandik,
                    logged_web_user_ref=web_user, detail=f"Üye oluşturuldu: '{web_user.name_surname}'"))
    member = Member(sandik_ref=sandik, web_user_ref=web_user, logs_set=logs, **kwargs)
    return member


def get_last_share_order(member):
    return select(share.share_order_of_member for share in member.shares_set).max() or 0


def create_share(member, created_by, **kwargs) -> Share:
    log = Log(web_user_ref=created_by, type=Log.TYPE.CREATE)
    return Share(logs_set=log, member_ref=member, **kwargs)


def get_member(**kwargs) -> Member:
    return Member.get(**kwargs)


def members_form_choices(sandik):
    choices = [(m.id, m.web_user_ref.name_surname) for m in sandik.members_set]
    return choices


def get_trust_relationship_between_two_member(member1, member2) -> TrustRelationship:
    return TrustRelationship.get(lambda tr:
                                 tr.status in [TrustRelationship.STATUS.WAITING, TrustRelationship.STATUS.ACCEPTED]
                                 and ((tr.requester_member_ref == member1 and tr.receiver_member_ref == member2)
                                      or (tr.requester_member_ref == member2 and tr.receiver_member_ref == member1)))


def create_trust_relationship(requester_member, receiver_member, requested_by) -> TrustRelationship:
    if requester_member == receiver_member:
        raise TrustRelationshipCreationException("Bir üye kendi kendine güven bağı kuramaz")

    tr = get_trust_relationship_between_two_member(member1=requester_member, member2=receiver_member)
    if tr:
        raise TrustRelationshipAlreadyExist()
    Log(web_user_ref=requested_by, type=Log.TYPE.CREATE,
        logged_sandik_ref=requester_member.sandik_ref)
    return TrustRelationship(requester_member_ref=requester_member, receiver_member_ref=receiver_member,
                             status=TrustRelationship.STATUS.WAITING)


def accept_trust_relationship_request(trust_relationship, confirmed_by):
    Log(web_user_ref=confirmed_by, type=Log.TYPE.TRUST_RELATIONSHIP.ACCEPT,
        logged_trust_relationship_ref=trust_relationship)
    trust_relationship.set(status=TrustRelationship.STATUS.ACCEPTED, time=datetime.now())


def reject_trust_relationship_request(trust_relationship, rejected_by):
    Log(web_user_ref=rejected_by, type=Log.TYPE.TRUST_RELATIONSHIP.REJECT,
        logged_trust_relationship_ref=trust_relationship)
    trust_relationship.set(status=TrustRelationship.STATUS.REJECTED, time=datetime.now())


def get_trust_relationship(**kwargs) -> TrustRelationship:
    return TrustRelationship.get(**kwargs)



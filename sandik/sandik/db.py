from datetime import datetime

from pony.orm import flush, select

from sandik.sandik.exceptions import TrustRelationshipAlreadyExist, TrustRelationshipCreationException, \
    MembershipApplicationAlreadyExist, WebUserIsAlreadyMember, ThereIsNotSandikAuthority
from sandik.utils.db_models import Sandik, Log, SandikAuthorityType, Member, Share, TrustRelationship, \
    get_updated_fields, SmsPackage


def save():
    flush()


"""
########################################################################################################################
###########################################  Sandık yetkileri fonksiyonları  ###########################################
########################################################################################################################
"""


def create_sandik_authority(created_by, **kwargs) -> SandikAuthorityType:
    log = Log(web_user_ref=created_by, type=Log.TYPE.SANDIK_AUTHORITY_TYPE.CREATE)
    return SandikAuthorityType(logs_set=log, **kwargs)


def get_sandik_authority(*args, **kwargs) -> SandikAuthorityType:
    return SandikAuthorityType.get(*args, **kwargs)


def delete_sandik_authority(sandik_authority, deleted_by):
    Log(web_user_ref=deleted_by, type=Log.TYPE.SANDIK_AUTHORITY_TYPE.DELETE, detail=str(sandik_authority.to_dict()))
    for log in sandik_authority.logs_set:
        log.detail += f"deleted_sandik_authority_type_id: {sandik_authority.id}"
    sandik_authority.delete()


def sandik_authorities_form_choices(sandik):
    choices = [(sat.id, sat.name) for sat in sandik.sandik_authority_types_set.order_by(lambda sat: sat.name)]
    return choices


def add_authorized_to_sandik(web_user, sandik_authority, connected_by):
    if web_user.get_sandik_authority(sandik=sandik_authority.sandik_ref):
        raise ThereIsNotSandikAuthority("Bu kullanızı zaten bu sandıkta yetkili. "
                                        "Aynı kullanıcı bir sandıkta sadece bir yetkiye sahip olabilir. "
                                        "Kullanıcının yetkisini değiştirmek istiyorsanız, "
                                        "lütfen önceki yetkiyi siliniz.")
    Log(web_user_ref=connected_by, type=Log.TYPE.SANDIK_AUTHORITY_TYPE.ADD_AUTHORIZED,
        logged_web_user_ref=web_user, logged_sandik_authority_type_ref=sandik_authority)
    sandik_authority.web_users_set.add(web_user)


def select_authorized_web_users_of_sandik(sandik):
    return select(web_user for web_user in (sat.web_users_set for sat in sandik.sandik_authority_types_set))


def delete_authorized_from_sandik(sandik_authority, web_user, removed_by):
    Log(web_user_ref=removed_by, type=Log.TYPE.SANDIK_AUTHORITY_TYPE.REMOVE_AUTHORIZED,
        logged_web_user_ref=web_user, logged_sandik_authority_type_ref=sandik_authority)
    sandik_authority.web_users_set.remove(web_user)


"""
########################################################################################################################
#############################################  Temel sandık fonksiyonları  #############################################
########################################################################################################################
"""


def create_sandik(created_by, **kwargs) -> Sandik:
    log = Log(web_user_ref=created_by, type=Log.TYPE.CREATE)
    sandik = Sandik(logs_set=log, **kwargs)
    create_sandik_authority(created_by=created_by, is_admin=True, name="Yönetici", sandik_ref=sandik,
                            web_users_set=created_by)
    return sandik


def get_sandik(**kwargs) -> Sandik:
    return Sandik.get(**kwargs)


def sandiks_form_choices():
    choices = [(s.id, s.name) for s in Sandik.select()]
    return choices


"""
########################################################################################################################
############################################  Sandık üyeliği fonksiyonları  ############################################
########################################################################################################################
"""


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
        raise WebUserIsAlreadyMember("Bu kullanıcı zaten sandığa üye")

    logs = []
    if confirmed_by:
        logs.append(Log(web_user_ref=confirmed_by, type=Log.TYPE.SANDIK.CONFIRM_MEMBERSHIP_APPLICATION,
                        logged_sandik_ref=sandik, logged_web_user_ref=web_user,
                        detail=f"Üyelik başvurusu onaylandı: '{web_user.name_surname}'"))
    sandik.applicant_web_users_set.remove(web_user)
    logs.append(Log(web_user_ref=created_by or confirmed_by, type=Log.TYPE.MEMBER.CREATE, logged_sandik_ref=sandik,
                    logged_web_user_ref=web_user, detail=f"Üye oluşturuldu: '{web_user.name_surname}'"))
    member = Member(sandik_ref=sandik, web_user_ref=web_user, logs_set=logs, **kwargs)
    return member


def get_last_share_order(member):
    return select(share.share_order_of_member for share in member.shares_set).max() or 0


def create_share(member, created_by, **kwargs) -> Share:
    log = Log(web_user_ref=created_by, type=Log.TYPE.SHARE.CREATE)
    return Share(logs_set=log, member_ref=member, **kwargs)


def update_share(share, updated_by, **kwargs):
    updated_fields = get_updated_fields(new_values=kwargs, db_object=share)
    Log(web_user_ref=updated_by, type=Log.TYPE.SHARE.UPDATE, logged_share_ref=share, detail=str(updated_fields))
    share.set(**kwargs)
    return share


def update_member(member, updated_by, **kwargs):
    updated_fields = get_updated_fields(new_values=kwargs, db_object=member)
    Log(web_user_ref=updated_by, type=Log.TYPE.MEMBER.UPDATE, logged_member_ref=member, detail=str(updated_fields))
    member.set(**kwargs)
    return member


def get_member(**kwargs) -> Member:
    return Member.get(**kwargs)


def get_share(**kwargs) -> Share:
    return Share.get(**kwargs)


def members_form_choices(sandik, only_active=True):
    if only_active:
        choices = [(m.id, m.web_user_ref.name_surname) for m in sandik.get_active_members()]
    else:
        choices = [(m.id, m.web_user_ref.name_surname) for m in sandik.members_set]
    choices = sorted(choices, key=lambda c: c[1])
    return choices


"""
########################################################################################################################
##############################################  Güven bağı fonksiyonları  ##############################################
########################################################################################################################
"""


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
    Log(web_user_ref=requested_by, type=Log.TYPE.TRUST_RELATIONSHIP.CREATE,
        logged_sandik_ref=requester_member.sandik_ref)
    return TrustRelationship(requester_member_ref=requester_member, receiver_member_ref=receiver_member,
                             status=TrustRelationship.STATUS.WAITING)


def accept_trust_relationship_request(trust_relationship, confirmed_by):
    Log(web_user_ref=confirmed_by, type=Log.TYPE.TRUST_RELATIONSHIP.ACCEPT,
        logged_trust_relationship_ref=trust_relationship)
    trust_relationship.set(status=TrustRelationship.STATUS.ACCEPTED, time=datetime.now())


def remove_trust_relationship_request(trust_relationship, rejected_by):
    Log(web_user_ref=rejected_by, type=Log.TYPE.TRUST_RELATIONSHIP.REMOVE,
        logged_trust_relationship_ref=trust_relationship)
    trust_relationship.set(status=TrustRelationship.STATUS.CANCELLED, time=datetime.now())
    return trust_relationship


def get_trust_relationship(**kwargs) -> TrustRelationship:
    return TrustRelationship.get(**kwargs)


"""
########################################################################################################################
############################################  Sms bildirimi fonksiyonları   ############################################
########################################################################################################################
"""


def create_sms_package(created_by, **kwargs) -> SmsPackage:
    log = Log(web_user_ref=created_by, type=Log.TYPE.SMS_PACKAGE.CREATE)
    return SmsPackage(logs_set=log, **kwargs)


"""
########################################################################################################################
########################################################################################################################
########################################################################################################################
"""

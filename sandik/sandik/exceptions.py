class TrustRelationshipException(Exception):
    pass


class TrustRelationshipCreationException(TrustRelationshipException):
    pass


class TrustRelationshipAlreadyExist(TrustRelationshipCreationException):
    pass


class MembershipException(Exception):
    pass


class MembershipApplicationAlreadyExist(MembershipException):
    pass


class WebUserIsAlreadyMember(MembershipException):
    pass


class ThereIsNoMember(Exception):
    pass

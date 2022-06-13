from sandik.utils.exceptions import Sandikv2Exception, THOUSANDS, Sandikv2UtilsException


class SandikException(Sandikv2Exception):
    ERRCODE_THOUSAND = THOUSANDS.SandikException

    def __init__(self, msg="", errcode=1, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log,
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class TrustRelationshipException(SandikException):
    ERRCODE_THOUSAND = THOUSANDS.TrustRelationshipException

    def __init__(self, msg="", errcode=1, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log,
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class TrustRelationshipCreationException(TrustRelationshipException):
    pass


class TrustRelationshipAlreadyExist(TrustRelationshipCreationException):
    pass


class MembershipException(SandikException):
    ERRCODE_THOUSAND = THOUSANDS.MembershipException

    def __init__(self, msg="", errcode=1, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log,
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class MembershipApplicationAlreadyExist(MembershipException):
    pass


class AddMemberException(MembershipException):
    pass


class UpdateMemberException(MembershipException):
    pass


class RemoveMemberException(MembershipException):
    pass


class RemoveShareException(MembershipException):
    pass


class NotActiveShareException(MembershipException):
    pass


class ThereIsUnpaidDebtOfShareException(RemoveShareException):
    pass


class NotActiveMemberException(MembershipException):
    pass


class ThereIsUnpaidDebtOfMemberException(RemoveMemberException):
    pass


class ThereIsUnpaidAmountOfLoanedException(RemoveMemberException):
    pass


class MaxShareCountExceed(MembershipException):
    pass


class WebUserIsAlreadyMember(MembershipException):
    pass


class ThereIsNoMember(Sandikv2UtilsException):
    pass


class ThereIsNoShare(Sandikv2UtilsException):
    pass


class SandikAuthorityException(SandikException):
    ERRCODE_THOUSAND = THOUSANDS.SandikAuthorityException

    def __init__(self, msg="", errcode=1, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log,
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class WebUserIsAlreadyAuthorized(SandikAuthorityException):
    pass


class ThereIsNotSandikAuthority(SandikAuthorityException):
    pass


class ThereIsNotAuthorizedOfSandik(SandikAuthorityException):
    pass


class ThereIsNoSandik(SandikException):
    pass


class SmsPackageException(SandikException):
    ERRCODE_THOUSAND = THOUSANDS.SmsPackageException

    def __init__(self, msg="", errcode=1, create_log=True, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log,
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class InvalidSmsType(SmsPackageException):
    pass


class SandikRuleFormulaException(SandikException):
    ERRCODE_THOUSAND = THOUSANDS.SandikRuleException

    def __init__(self, msg="", errcode=1, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log,
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)
    pass


class InvalidRuleVariable(SandikRuleFormulaException):
    pass


class InvalidRuleCharacter(SandikRuleFormulaException):
    pass

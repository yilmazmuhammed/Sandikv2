import inspect
import math
import os
from datetime import date
from datetime import datetime
from decimal import Decimal

from flask_login import UserMixin
from pony.orm import *

db = Database()


class BankTransaction(db.Entity):
    id = PrimaryKey(int, auto=True)
    time = Required(datetime)
    description = Optional(str)
    amount = Required(Decimal)
    tref_id = Optional(str)  # KuveytApi ile ilgili
    logs_set = Set('Log')
    bank_account_ref = Required('BankAccount')
    money_transaction_ref = Optional('MoneyTransaction')


class MoneyTransaction(db.Entity):
    # TODO para çıkışı ise is_fully_distributed true olmak zorundadır
    id = PrimaryKey(int, auto=True)
    date = Required(date, default=lambda: date.today())
    amount = Required(Decimal)
    detail = Optional(str)
    type = Required(int)
    is_fully_distributed = Required(bool, default=False)  # MoneyTransaction amount ile SubReceipts amountları toplamı eşit ise True
    creation_type = Required(int)
    bank_transaction_ref = Optional(BankTransaction)
    logs_set = Set('Log')
    member_ref = Required('Member')
    sub_receipts_set = Set('SubReceipt')

    class TYPE:
        REVENUE = 0  # sandık geliri
        EXPENSE = 1  # sandık gideri

        strings = {REVENUE: "Para girişi", EXPENSE: "Para çıkışı"}

    def is_type_revenue(self):
        return self.type == MoneyTransaction.TYPE.REVENUE

    def is_type_expense(self):
        return self.type == MoneyTransaction.TYPE.EXPENSE

    class CREATION_TYPE:
        BY_MANUEL = 0
        BY_BANK_TRANSACTION = 1
        BY_AUTO = 2

    def distributed_amount(self):
        return select(sr.amount for sr in self.sub_receipts_set).sum()

    def get_undistributed_amount(self):
        return self.amount - self.distributed_amount()

    def recalculate_is_fully_distributed(self):
        mt_untreated_amount = self.get_undistributed_amount()
        if mt_untreated_amount == 0:
            self.is_fully_distributed = True
        elif mt_untreated_amount > 0:
            self.is_fully_distributed = False
        elif mt_untreated_amount < 0:
            raise Exception("ERRCODE: 0013, MSG: Site yöneticisi ile iletişime geçerek ERRCODE'u söyleyiniz.")


class Share(db.Entity):
    """composite_key(membre_ref, share_order_of_member)"""
    id = PrimaryKey(int, auto=True)
    logs_set = Set('Log')
    member_ref = Required('Member')
    share_order_of_member = Required(int)
    date_of_opening = Required(date, default=lambda: date.today())
    is_active = Required(bool, default=True)
    sub_receipts_set = Set('SubReceipt')
    contributions_set = Set('Contribution')
    debts_set = Set('Debt')

    def sum_of_paid_contributions(self):
        return select(
            sr.amount for sr in self.sub_receipts_set
            if sr.contribution_ref and sr.money_transaction_ref.is_type_revenue()
        ).sum() - select(
            sr.amount for sr in self.sub_receipts_set
            if sr.contribution_ref and sr.money_transaction_ref.is_type_expense()
        ).sum()

    def final_status(self, t_type):
        if t_type == "contribution":
            return self.sum_of_paid_contributions()
        elif t_type == "debt":
            return select(sr.amount for sr in self.sub_receipts_set if sr.debt_ref).sum()
        elif t_type == "installment":
            return select(sr.amount for sr in self.sub_receipts_set if sr.installment_ref).sum()
        elif t_type == "total":
            return "xxx"
            revenue = select(sr.amount for sr in self.sub_receipts_set
                             if sr.installment_ref or sr.contribution_ref).sum()
            expense = select(sr.amount for sr in self.sub_receipts_set if sr.debt_ref).sum()
            return revenue - expense

    def max_amount_can_borrow(self, use_untreated_amount=False):
        amount = self.member_ref.total_balance_from_accepted_trust_links()

        from sandik.utils import sandik_preferences
        remaining_debt_amount = sandik_preferences.remaining_debt_balance(sandik=self.member_ref.sandik_ref, whose=self)
        amount = amount if amount <= remaining_debt_amount else remaining_debt_amount

        if use_untreated_amount:
            amount += self.member_ref.total_of_undistributed_amount()

        return amount

    def total_amount_of_paid_contribution(self):
        total_of_half_paid_contributions = select(
            c.get_paid_amount() for c in Contribution if c.share_ref == self and c.is_fully_paid is False
        ).sum()
        total_of_fully_paid_contributions = select(
            c.amount for c in Contribution if c.share_ref == self and c.is_fully_paid is True
        ).sum()
        return total_of_half_paid_contributions + total_of_fully_paid_contributions

    def total_amount_unpaid_installments(self):
        return select(i.get_unpaid_amount() for i in Installment if
                      i.debt_ref.share_ref == self and i.is_fully_paid is False).sum()

    def get_unpaid_debts(self):
        return select(d for d in Debt if d.share_ref == self and d.get_unpaid_amount() > 0)

    @property
    def sandik_ref(self):
        return self.member_ref.sandik_ref


class Member(db.Entity):
    id = PrimaryKey(int, auto=True)
    web_user_ref = Optional('WebUser')
    sandik_ref = Required('Sandik')
    date_of_membership = Required(date, default=lambda: date.today())
    contribution_amount = Required(Decimal)
    detail = Optional(str)
    is_active = Required(bool, default=True)
    balance = Required(Decimal, default=0)
    logs_set = Set('Log')
    money_transactions_set = Set(MoneyTransaction)
    requested_trust_relationships_set = Set('TrustRelationship', reverse='requester_member_ref')
    received_trust_relationships_set = Set('TrustRelationship', reverse='receiver_member_ref')
    shares_set = Set(Share)
    piece_of_debts_set = Set('PieceOfDebt')
    composite_key(sandik_ref, web_user_ref)

    def get_balance(self):
        contributions_amount = select(sr.amount for sr in SubReceipt
                                      if sr.money_transaction_ref.member_ref == self and sr.contribution_ref).sum()
        undistributed_amount = self.total_of_undistributed_amount()
        unpaid_amount_of_loaned = select(
            pod.get_unpaid_amount() for pod in self.piece_of_debts_set if pod.debt_ref).sum()
        return contributions_amount + undistributed_amount - unpaid_amount_of_loaned

    """
    ######################################################################################################
    ################### UYENIN VERDIGI BORCLAR (PIECE_OF_DEBT) ILE ILGILI FONKSIYONLAR ###################
    """

    def get_loaned_amount(self):
        return select(pod.amount for pod in self.piece_of_debts_set).sum()

    def get_paid_amount_of_loaned(self):
        return select(pod.paid_amount for pod in self.piece_of_debts_set).sum()

    def get_unpaid_amount_of_loaned(self):
        return select(pod.get_unpaid_amount() for pod in self.piece_of_debts_set).sum()

    """
    ################### UYENIN VERDIGI BORCLAR (PIECE_OF_DEBT) ILE ILGILI FONKSIYONLAR ###################
    ######################################################################################################
    """

    """
    ######################################################################################################
    ################################## HISSELER ILE ILGILI FONKSIYONLAR ##################################
    """

    def shares_count(self, all_shares=False, is_active=True):
        if all_shares:
            return self.shares_set.count()
        return self.shares_set.filter(lambda s: s.is_active == is_active).count()

    def get_active_shares(self):
        return self.shares_set.filter(lambda s: s.is_active)

    """
    ################################## HISSELER ILE ILGILI FONKSIYONLAR ##################################
    ######################################################################################################
    """

    def transactions_count(self):
        contribution_count = select(c for c in Contribution if c.share_ref.member_ref == self).count()
        debt_count = select(d for d in Debt if d.share_ref.member_ref == self).count()
        installment_count = select(i for i in Installment if i.share_ref.member_ref == self).count()
        return contribution_count + debt_count + installment_count

    def sum_of_paid_contributions(self):
        return select(
            sr.amount for sr in SubReceipt
            if sr.contribution_ref and sr.member_ref == self and sr.money_transaction_ref.is_type_revenue()
        ).sum() - select(
            sr.amount for sr in SubReceipt
            if sr.contribution_ref and sr.member_ref == self and sr.money_transaction_ref.is_type_expense()
        ).sum()

    def sum_of_paid_installments(self):
        return select(sr.amount for sr in SubReceipt if
                      sr.installment_ref and sr.money_transaction_ref.member_ref == self).sum()

    def final_status(self, t_type):
        if t_type == "contribution":
            return self.sum_of_paid_contributions()
        elif t_type == "debt":
            return select(sr.amount for sr in SubReceipt if
                          sr.debt_ref and sr.money_transaction_ref.member_ref == self).sum()
        elif t_type == "installment":
            return self.sum_of_paid_installments()
        elif t_type == "total":
            return "xxx"
            revenue = select(mt.amount for mt in self.money_transactions_set if
                             mt.type == MoneyTransaction.TYPE.REVENUE).sum()
            expense = select(mt.amount for mt in self.money_transactions_set if
                             mt.type == MoneyTransaction.TYPE.EXPENSE).sum()
            return revenue - expense

    def get_trust_link_with_member(self, other_member):
        return TrustRelationship.get(
            lambda t: ((t.requester_member_ref == self and t.receiver_member_ref == other_member)
                       or (t.requester_member_ref == other_member and t.receiver_member_ref == self))
                      and t.status != TrustRelationship.STATUS.REJECTED
                      and t.status != TrustRelationship.STATUS.CANCELLED
        )

    def accepted_trust_links(self):
        return select(t for t in TrustRelationship
                      if (t.requester_member_ref == self or t.receiver_member_ref == self)
                      and t.status == TrustRelationship.STATUS.ACCEPTED)

    def waiting_trust_links(self):
        return select(t for t in TrustRelationship
                      if (t.requester_member_ref == self or t.receiver_member_ref == self)
                      and t.status == TrustRelationship.STATUS.WAITING)

    def waiting_received_trust_relationships_request(self):
        return select(t for t in TrustRelationship
                      if t.receiver_member_ref == self and t.status == TrustRelationship.STATUS.WAITING)

    def total_balance_from_accepted_trust_links(self):
        amount = 0
        amount += self.get_balance()
        print("member.total_balance_from_accepted_trust_links .... member.get_balance():", amount)
        for link in self.accepted_trust_links():
            amount += link.other_member(whose=self).get_balance()
        return amount

    def max_amount_can_borrow(self, use_untreated_amount=False):
        amount = self.total_balance_from_accepted_trust_links()

        from sandik.utils import sandik_preferences
        remaining_debt_amount = sandik_preferences.remaining_debt_balance(sandik=self.sandik_ref, whose=self)
        amount = amount if amount <= remaining_debt_amount else remaining_debt_amount

        if use_untreated_amount:
            amount += self.total_of_undistributed_amount()

        return amount

    def get_revenue_money_transactions_are_not_fully_distributed(self):
        return select(mt for mt in self.money_transactions_set if
                      mt.type == MoneyTransaction.TYPE.REVENUE and mt.is_fully_distributed is False)

    def total_of_undistributed_amount(self):
        return select(
            mt.get_undistributed_amount() for mt in
            self.get_revenue_money_transactions_are_not_fully_distributed()).sum()

    def total_amount_unpaid_installments(self):
        return select(i.get_unpaid_amount() for i in Installment if
                      i.debt_ref.share_ref.member_ref == self and i.is_fully_paid is False).sum()

    def total_amount_of_paid_contribution(self):
        total_of_half_paid_contributions = select(
            c.get_paid_amount() for c in Contribution if c.share_ref.member_ref == self and c.is_fully_paid is False
        ).sum()
        total_of_fully_paid_contributions = select(
            c.amount for c in Contribution if c.share_ref.member_ref == self and c.is_fully_paid is True
        ).sum()
        return total_of_half_paid_contributions + total_of_fully_paid_contributions

    def get_unpaid_debts(self):
        return select(d for d in Debt if d.member_ref == self and d.get_unpaid_amount() > 0)


class WebUser(db.Entity, UserMixin):
    id = PrimaryKey(int, auto=True)
    email_address = Required(str, unique=True)
    password_hash = Required(str)
    tc = Optional(str)
    name = Required(str)
    surname = Required(str)
    registration_time = Required(datetime, default=lambda: datetime.now())
    is_active_ = Required(bool, default=False)
    telegram_chat_id = Optional(int)
    phone_number = Optional(str)
    created_logs_set = Set('Log', reverse='web_user_ref')
    logs_set = Set('Log', reverse='logged_web_user_ref')
    bank_accounts_set = Set('BankAccount')
    applied_sandiks_set = Set('Sandik')
    sandik_authority_types_set = Set('SandikAuthorityType')
    members_set = Set(Member)
    notifications_set = Set('Notification')
    sms_packages_set = Set('SmsPackage')

    @property
    def is_active(self):
        return self.is_active_ or self.is_admin()

    def get_id(self):
        return self.id

    def is_admin(self):
        return self.email_address == os.getenv("ADMIN_EMAIL_ADDRESS")

    @property
    def name_surname(self):
        return f"{self.name} {self.surname}"

    def my_sandiks(self):
        query1 = select(member.sandik_ref for member in self.members_set)
        query2 = select(sat.sandik_ref for sat in self.sandik_authority_types_set)
        return set(query1[:] + query2[:])

    def my_unread_notifications(self):
        return self.notifications_set.filter(lambda n: not bool(n.reading_time)).order_by(
            lambda n: desc(n.creation_time)
        )

    def get_sandik_authority(self, sandik):
        return self.sandik_authority_types_set.filter(sandik_ref=sandik).get()

    def has_permission(self, sandik, permission):
        if permission not in ["write", "read", "admin"]:
            raise Exception("Yanlış izin yetkisi girildi")

        if self.is_admin():
            return True

        authority = self.get_sandik_authority(sandik=sandik)
        if not authority:
            return False
        if permission == "admin" and authority.is_admin:
            return True
        if permission == "write" and (authority.can_write or authority.is_admin):
            return True
        if permission == "read" and (authority.can_read or authority.can_write or authority.is_admin):
            return True
        return False

    def get_primary_bank_account(self):
        return self.bank_accounts_set.select(is_primary=True).get()


class Log(db.Entity):
    id = PrimaryKey(int, auto=True)
    web_user_ref = Required(WebUser, reverse='created_logs_set')
    time = Required(datetime, default=lambda: datetime.now())
    type = Required(int)
    special_type = Optional(str)
    detail = Optional(str)
    logged_bank_account_ref = Optional('BankAccount')
    logged_retracted_ref = Optional('Retracted')
    logged_contribution_ref = Optional('Contribution')
    logged_installment_ref = Optional('Installment')
    logged_debt_ref = Optional('Debt')
    logged_sub_receipt_ref = Optional('SubReceipt')
    logged_piece_of_debt_ref = Optional('PieceOfDebt')
    logged_bank_transaction_ref = Optional(BankTransaction)
    logged_money_transaction_ref = Optional(MoneyTransaction)
    logged_share_ref = Optional(Share)
    logged_member_ref = Optional(Member)
    logged_sandik_ref = Optional('Sandik')
    logged_sms_package_ref = Optional('SmsPackage')
    logged_web_user_ref = Optional(WebUser, reverse='logs_set')
    logged_sandik_authority_type_ref = Optional('SandikAuthorityType')
    logged_trust_relationship_ref = Optional('TrustRelationship')

    class TYPE:
        CREATE = 1
        UPDATE = 2
        DELETE = 3
        CONFIRM = 4
        OTHER = 5

        @classmethod
        def print_attributes(cls, searched_value, class_in_search=None, parent_name=""):
            if class_in_search is None:
                class_in_search = cls
            for key, value in class_in_search.__dict__.items():
                if value == searched_value:
                    return parent_name + key
                if inspect.isclass(value):
                    ret = cls.print_attributes(class_in_search=value, searched_value=searched_value,
                                               parent_name=parent_name + key + ".")
                    if ret:
                        return ret
            return None

        class WEB_USER:
            first, last = 100, 199
            UPDATE = first + 2
            CONFIRM = first + 11
            BLOCK = first + 12
            REGISTER = first + 13

        class SANDIK:
            first, last = 200, 299
            UPDATE = first + 2
            APPLY_FOR_MEMBERSHIP = first + 11
            CONFIRM_MEMBERSHIP_APPLICATION = first + 12
            REJECT_MEMBERSHIP_APPLICATION = first + 13

        class TRUST_RELATIONSHIP:
            first, last = 300, 399
            CREATE = first + 1
            REJECT = first + 12
            ACCEPT = first + 13
            CANCEL = first + 14
            REMOVE = first + 15

        class SUB_RECEIPT:
            first, last = 400, 499
            CREATE = first + 1
            DELETE = first + 3

        class MONEY_TRANSACTION:
            first, last = 500, 599
            CREATE = first + 1
            DELETE = first + 3
            SIGN_FULLY_DISTRIBUTED = first + 11

        class DEBT:
            first, last = 600, 699
            CREATE = first + 1

        class INSTALLMENT:
            first, last = 700, 799
            CREATE = first + 1

        class PIECE_OF_DEBT:
            first, last = 800, 899
            CREATE = first + 1

        class CONTRIBUTION:
            first, last = 900, 999
            CREATE = first + 1
            DELETE = first + 3

        class BANK_ACCOUNT:
            first, last = 1000, 1099
            CREATE = first + 1
            UPDATE = first + 2
            DELETE = first + 3

        class SANDIK_AUTHORITY_TYPE:
            first, last = 1100, 1199
            CREATE = first + 1
            DELETE = first + 3
            ADD_AUTHORIZED = first + 11
            REMOVE_AUTHORIZED = first + 13

        class SHARE:
            first, last = 1200, 1299
            CREATE = first + 1
            UPDATE = first + 2

        class MEMBER:
            first, last = 1300, 1399
            CREATE = first + 1
            UPDATE = first + 2

        class SMS_PACKAGE:
            first, last = 1400, 1499
            CREATE = first + 1

        class LOG_LEVEL:
            first, last = 10000, 10099
            INFO = first + 11
            WARNING = first + 12
            ERROR = first + 13
            CRITICAL = first + 14


class Sandik(db.Entity):
    id = PrimaryKey(int, auto=True)
    name = Required(str)
    contribution_amount = Required(Decimal, default=0)
    is_active = Required(bool, default=True)
    date_of_opening = Required(date, default=lambda: date.today())
    applicant_web_users_set = Set(WebUser)
    detail = Optional(str)
    logs_set = Set(Log)
    bank_accounts_set = Set('BankAccount')
    members_set = Set(Member)
    sandik_authority_types_set = Set('SandikAuthorityType')
    sms_packages_set = Set('SmsPackage')
    type = Required(int)
    sandik_rules_set = Set('SandikRule')

    class TYPE:
        CLASSIC = 1
        WITH_TRUST_RELATIONSHIP = 2

        strings = {CLASSIC: "Klasik sistem", WITH_TRUST_RELATIONSHIP: "Güven bağlı sistem"}

    def is_type_with_trust_relationship(self):
        print("is_type_with_trust_relationship:", self.type == self.TYPE.WITH_TRUST_RELATIONSHIP)
        return self.type == self.TYPE.WITH_TRUST_RELATIONSHIP

    def is_type_classic(self):
        return self.type == self.TYPE.CLASSIC

    def type_str(self):
        return self.TYPE.strings.get(self.type, "UNKNOWN")

    def get_active_members(self):
        return self.members_set.filter(lambda m: m.is_active)

    def shares_count(self):
        return count(self.members_set.shares_set)

    def transactions_count(self):
        contribution_count = select(c for c in Contribution if c.share_ref.member_ref.sandik_ref == self).count()
        debt_count = select(d for d in Debt if d.share_ref.member_ref.sandik_ref == self).count()
        installment_count = select(i for i in Installment if i.share_ref.member_ref.sandik_ref == self).count()
        return contribution_count + debt_count + installment_count

    def final_status(self, t_type):
        if t_type == "contribution":
            return select(sr.amount for sr in SubReceipt if
                          sr.contribution_ref and sr.money_transaction_ref.member_ref.sandik_ref == self).sum()
        elif t_type == "debt":
            return select(sr.amount for sr in SubReceipt if
                          sr.debt_ref and sr.money_transaction_ref.member_ref.sandik_ref == self).sum()
        elif t_type == "installment":
            return select(sr.amount for sr in SubReceipt if
                          sr.installment_ref and sr.money_transaction_ref.member_ref.sandik_ref == self).sum()
        elif t_type == "total":
            revenue = select(mt.amount for mt in MoneyTransaction if
                             mt.member_ref.sandik_ref == self and mt.type == MoneyTransaction.TYPE.REVENUE).sum()
            expense = select(mt.amount for mt in MoneyTransaction if
                             mt.member_ref.sandik_ref == self and mt.type == MoneyTransaction.TYPE.EXPENSE).sum()
            return revenue - expense

    def has_application(self):
        return self.applicant_web_users_set.count() > 0

    def get_money_transactions(self):
        return select(mt for mt in MoneyTransaction if mt.member_ref.sandik_ref == self)

    def total_of_undistributed_amount(self):
        return select(member.total_of_undistributed_amount() for member in self.get_active_members()).sum()


class TrustRelationship(db.Entity):
    id = PrimaryKey(int, auto=True)
    status = Required(int)
    time = Required(datetime, default=lambda: datetime.now())
    logs_set = Set(Log)
    requester_member_ref = Required(Member, reverse='requested_trust_relationships_set')
    receiver_member_ref = Required(Member, reverse='received_trust_relationships_set')

    class STATUS:
        WAITING = 1
        REJECTED = 2
        ACCEPTED = 3
        CANCELLED = 4

    def other_member(self, whose):
        if isinstance(whose, Member):
            if whose not in [self.receiver_member_ref, self.requester_member_ref]:
                raise Exception("gönderilen sandık üyesi güven bağının taraflarından değil")
            return self.requester_member_ref if self.receiver_member_ref == whose else self.receiver_member_ref
        elif isinstance(whose, WebUser):
            if whose not in [self.receiver_member_ref.web_user_ref, self.requester_member_ref.web_user_ref]:
                raise Exception("gönderilen site kullanıcısı güven bağının taraflarından değil")
            return self.requester_member_ref if self.receiver_member_ref.web_user_ref == whose else self.receiver_member_ref
        else:
            raise Exception("whose 'Member' veya 'WebUser' türünde olmalı")

    def is_accepted(self):
        return self.status == TrustRelationship.STATUS.ACCEPTED

    def is_waiting(self):
        return self.status == TrustRelationship.STATUS.WAITING


class BankAccount(db.Entity):
    id = PrimaryKey(int, auto=True)
    title = Required(str)
    holder = Optional(str)
    iban = Required(str)
    logs_set = Set(Log)
    web_user_ref = Optional(WebUser)
    sandik_ref = Optional(Sandik)
    bank_transactions_set = Set(BankTransaction)
    is_primary = Required(bool)

    def get_iban_string(self):
        return f"TR{self.iban[0:2]} {self.iban[2:6]} {self.iban[6:10]} {self.iban[10:14]} {self.iban[14:18]} {self.iban[18:22]} {self.iban[22:24]}"

    def before_insert(self):
        # TODO test et: Aynı kullanıcının veya sandığın aynı anca sadece bir tane primary (öncelikli) banka hesabı
        #  olabilir
        if self.is_primary and BankAccount.get(is_primary=True,
                                               web_user_ref=self.web_user_ref, sandik_ref=self.sandik_ref):
            from sandik.general.exceptions import ThereIsAlreadyPrimaryBankAccount
            raise ThereIsAlreadyPrimaryBankAccount("Daha önce varsayılan (birincil) banka hesabı oluşturulmuş.")


class SandikAuthorityType(db.Entity):
    id = PrimaryKey(int, auto=True)
    name = Required(str)
    is_admin = Required(bool, default=False)
    can_read = Required(bool, default=False)
    can_write = Required(bool, default=False)
    logs_set = Set(Log)
    web_users_set = Set(WebUser)
    sandik_ref = Required(Sandik)
    # TODO Aynı sandıkta bir kullanıcının bir yetkisi olabilir
    # TODO before_update acaba Set'e eleman eklenirken de çalışıyor mu???


class Contribution(db.Entity):
    id = PrimaryKey(int, auto=True)
    amount = Required(Decimal)
    term = Required(str)
    is_fully_paid = Required(bool, default=False)
    logs_set = Set(Log)
    share_ref = Required(Share)
    sub_receipts_set = Set('SubReceipt')

    @property
    def member_ref(self):
        return self.share_ref.member_ref

    @property
    def sandik_ref(self):
        return self.member_ref.sandik_ref

    def get_amount(self):
        return abs(self.amount)

    def get_paid_amount(self):
        return select(sr.amount for sr in self.sub_receipts_set).sum()

    def get_unpaid_amount(self):
        return self.get_amount() - self.get_paid_amount()

    def recalculate_is_fully_paid(self):
        unpaid_amount = self.get_unpaid_amount()
        if unpaid_amount == 0:
            self.is_fully_paid = True
        elif unpaid_amount > 0:
            self.is_fully_paid = False
        else:
            print("recalculate_is_fully_paid:", unpaid_amount)
            rollback()
            from sandik.utils.exceptions import UnexpectedValue
            raise UnexpectedValue("ERRCODE: 0010, MSG: Site yöneticisi ile iletişime geçerek ERRCODE'u söyleyiniz.")


class Debt(db.Entity):
    id = PrimaryKey(int, auto=True)
    amount = Required(Decimal)
    installments_set = Set('Installment')
    number_of_installment = Required(int)
    starting_term = Required(str)
    due_term = Required(str)
    sub_receipt_ref = Required('SubReceipt')
    logs_set = Set(Log)
    share_ref = Required(Share)
    piece_of_debts_set = Set('PieceOfDebt')

    @property
    def member_ref(self):
        return self.share_ref.member_ref

    @property
    def sandik_ref(self):
        return self.member_ref.sandik_ref

    def get_paid_amount(self):
        return select(i.get_paid_amount() for i in self.installments_set).sum()

    def get_unpaid_amount(self):
        return self.amount - self.get_paid_amount()

    def update_pieces_of_debt(self):
        # TODO ilgili borç tamamen ödendiyse PieceOfDebt'leri sil
        # TODO ilgili borç tamamen ödenmediyse PieceOfDebt'leri güncelle
        paid_amount = self.get_paid_amount()
        undistributed_paid_amount = paid_amount
        for piece in self.piece_of_debts_set:
            piece_lot = math.ceil(paid_amount * (piece.amount / self.amount))

            temp_paid_amount = piece_lot if piece_lot <= undistributed_paid_amount else undistributed_paid_amount
            piece.set(paid_amount=temp_paid_amount)
            undistributed_paid_amount -= temp_paid_amount

        if undistributed_paid_amount != 0:
            raise Exception(f"ERRCODE: 0019, RA: {undistributed_paid_amount}, "
                            f"MSG: Beklenmedik bir hata ile karşılaşıldı. Düzeltilmesi için "
                            f"lütfen site yöneticisi ile iletişime geçerek ERRCODE'u ve RA'yı söyleyiniz.")


class Installment(db.Entity):
    id = PrimaryKey(int, auto=True)
    amount = Required(Decimal)
    term = Required(str)
    is_fully_paid = Required(bool, default=False)
    debt_ref = Required(Debt)
    sub_receipts_set = Set('SubReceipt')
    logs_set = Set(Log)

    @property
    def share_ref(self):
        return self.debt_ref.share_ref

    @property
    def member_ref(self):
        return self.share_ref.member_ref

    @property
    def sandik_ref(self):
        return self.member_ref.sandik_ref

    def get_paid_amount(self):
        return select(sr.amount for sr in self.sub_receipts_set).sum()

    def get_unpaid_amount(self):
        return self.amount - self.get_paid_amount()

    def recalculate_is_fully_paid(self):
        unpaid_amount = self.get_unpaid_amount()
        if unpaid_amount == 0:
            self.is_fully_paid = True
        elif unpaid_amount > 0:
            self.is_fully_paid = False
        else:
            print("Installment.recalculate_is_fully_paid:", unpaid_amount)
            rollback()
            from sandik.utils.exceptions import UnexpectedValue
            raise UnexpectedValue("ERRCODE: 0011, MSG: Site yöneticisi ile iletişime geçerek ERRCODE'u söyleyiniz.")


class SubReceipt(db.Entity):
    """TODO - Bir SubReceipt aynı anda Contribution, Debt veya Installment'ten biriyle ilişkili olmak zorundadır. Daha az veya daha fazlası olamaz."""
    id = PrimaryKey(int, auto=True)
    amount = Required(Decimal)
    is_auto = Required(bool)
    expense_retracted_ref = Optional('Retracted', reverse='expense_sub_receipt_ref')
    revenue_retracted_ref = Optional('Retracted', reverse='revenue_sub_receipt_ref')
    contribution_ref = Optional(Contribution)
    installment_ref = Optional(Installment)
    debt_ref = Optional(Debt)
    money_transaction_ref = Required(MoneyTransaction)
    logs_set = Set(Log)
    share_ref = Optional(Share)
    creation_time = Required(datetime, default=lambda: datetime.now())

    @property
    def member_ref(self):
        return self.money_transaction_ref.member_ref

    def before_insert(self):
        # TODO test et
        counter = 0
        for ref in [self.contribution_ref, self.installment_ref, self.debt_ref,
                    self.revenue_retracted_ref, self.expense_retracted_ref]:
            if ref:
                counter += 1
        if counter != 1:
            rollback()
            print("ERRCODE: 0012, MSG: Site yöneticisi ile iletişime geçerek ERRCODE'u söyleyiniz.")

    def after_insert(self):
        # TODO test et
        if self.contribution_ref:
            self.contribution_ref.recalculate_is_fully_paid()
            self.contribution_ref.share_ref.member_ref.balance += self.amount

        if self.installment_ref:
            self.installment_ref.recalculate_is_fully_paid()
            self.installment_ref.debt_ref.update_pieces_of_debt()

        # TODO test et: 4 işlem tipi için de dene
        self.money_transaction_ref.recalculate_is_fully_distributed()

    def before_delete(self):
        # if self.contribution_ref:
        #     contribution = self.contribution_ref
        #     self.contribution_ref = None
        #     contribution.recalculate_is_fully_paid()
        #     contribution.share_ref.member_ref.balance -= self.amount
        #
        # if self.installment_ref:
        #     installment = self.installment_ref
        #     self.installment_ref = None
        #     installment.recalculate_is_fully_paid()
        #     installment.debt_ref.update_pieces_of_debt()
        pass


class Notification(db.Entity):
    id = PrimaryKey(int, auto=True)
    web_user_ref = Optional(WebUser)
    title = Required(str)
    text = Required(str)
    url = Optional(str)
    creation_time = Required(datetime, default=lambda: datetime.now())
    reading_time = Optional(datetime)


class PieceOfDebt(db.Entity):
    id = PrimaryKey(int, auto=True)
    logs_set = Set(Log)
    member_ref = Required(Member)
    debt_ref = Required(Debt)
    amount = Required(Decimal)
    paid_amount = Required(Decimal, default=0)

    def get_unpaid_amount(self):
        return self.amount - self.paid_amount

    def before_insert(self):
        # TODO test et
        if self.member_ref.get_balance() < self.amount:
            raise Exception("ERRCODE: 0018, "
                            "MSG: Beklenmedik bir hata ile karşılaşıldı. "
                            "Düzeltilmesi için lütfen site yöneticisi ile iletişime geçerek ERRCODE'u söyleyiniz.")

    def after_insert(self):
        # TODO test et
        self.member_ref.balance -= self.amount

    def set(self, **kwargs):
        if kwargs.get("paid_amount"):
            # TODO test et
            new_balance = self.member_ref.balance + (kwargs.get("paid_amount") - self.paid_amount)
            self.member_ref.set(balance=new_balance)

        # TODO test et
        super().set(**kwargs)


class Retracted(db.Entity):
    id = PrimaryKey(int, auto=True)
    amount = Required(Decimal)
    logs_set = Set(Log)
    expense_sub_receipt_ref = Required(SubReceipt, reverse='expense_retracted_ref')
    revenue_sub_receipt_ref = Required(SubReceipt, reverse='revenue_retracted_ref')

    @property
    def member_ref(self):
        return self.expense_sub_receipt_ref.member_ref

    @property
    def sandik_ref(self):
        return self.member_ref.sandik_ref


class SmsPackage(db.Entity):
    id = PrimaryKey(int, auto=True)
    text = Required(str)
    header = Required(str)
    type = Required(int)
    status = Required(int, default=1)
    web_users_set = Set(WebUser)
    external_api_task_id = Optional(str)
    logs_set = Set(Log)
    sandik_ref = Optional(Sandik)

    class TYPE:
        class SANDIK:
            THERE_IS_UNCONFIRMED_TRUST_RELATIONSHIP_REQUEST = 101

        strings = {SANDIK.THERE_IS_UNCONFIRMED_TRUST_RELATIONSHIP_REQUEST: "Bekleyen güven bağı isteğiniz var"}

    class STATUS:
        SMS_PACKAGE_CREATED = 1

    DYNAMIC_FIELDS = ['{name_surname}']

    def is_n_to_n(self):
        for field in self.DYNAMIC_FIELDS:
            if field in self.text:
                return True
        return False


class SandikRule(db.Entity):
    id = PrimaryKey(int, auto=True)
    sandik_ref = Required(Sandik)
    type = Required(int)
    order = Required(int)
    formula = Required(str)

    class TYPE:
        MAX_AMOUNT_OF_DEBT = 1
        MAX_NUMBER_OF_INSTALLMENT = 2
        MAX_NUMBER_OF_SHARE = 3

        strings = {
            MAX_AMOUNT_OF_DEBT: "Alınabilecek en fazla borç miktarı",
            MAX_NUMBER_OF_INSTALLMENT: "Borç miktarına göre yapılabilecek en fazla taksit sayısı",
            MAX_NUMBER_OF_SHARE: "En fazla açılabilecek hisse sayısı",
        }


DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    db.bind(provider="postgres", dsn=DATABASE_URL)
else:
    db.bind(provider="sqlite", filename='database.sqlite', create_db=True)

db.generate_mapping(create_tables=True)


def get_updated_fields(new_values, db_object):
    ret = {}
    print("get_updated_fields .... new_values:", new_values)
    old_values = db_object.to_dict()
    print("get_updated_fields .... old_values:", old_values)
    for key, value in new_values.items():
        if key in old_values.keys() and value != old_values[key]:
            ret[key] = {"new": value, "old": old_values[key]}
    return ret


if __name__ == '__main__':
    with db_session:
        # Initialize operations
        pass

"""Testlerde tekrar eden üye/sandık/ödeme kurulumları için ince yardımcı fabrikalar.

Mümkün olduğunca gerçek `sandik/*/db.py` katmanındaki `create_*` fonksiyonlarını kullanır (ham
`Entity(...)` çağrısı yerine); böylece testler gerçek kodun ürettiği `Log` kayıtları vb. yan
etkilerle birlikte, uygulamanın kullandığı yola olabildiğince yakın kalır.

Yeni bir test senaryosu eklerken önce burada uygun bir fabrika olup olmadığına bakın; yoksa buraya
ekleyin ki bir sonraki test de kullanabilsin ("yavaş yavaş test havuzu" mantığı).
"""
import itertools
from decimal import Decimal

from sandik.auth import db as auth_db
from sandik.sandik import db as sandik_db
from sandik.transaction import db as transaction_db
from sandik.utils import period as period_utils
from sandik.utils.db_models import MoneyTransaction, Sandik, TrustRelationship, WebUser, Member, Share

_counter = itertools.count(1)


def make_web_user(created_by=None, **overrides) -> WebUser:
    n = next(_counter)
    kwargs = dict(email_address=f"test-user-{n}@example.com", password_hash="x",
                 name="Test", surname=f"Üye{n}", is_active_=True)
    kwargs.update(overrides)
    return auth_db.create_web_user(created_by=created_by, **kwargs)


def make_sandik(created_by, **overrides) -> Sandik:
    n = next(_counter)
    kwargs = dict(name=f"Test Sandık {n}", type=Sandik.TYPE.CLASSIC, contribution_amount=Decimal("100"))
    kwargs.update(overrides)
    return sandik_db.create_sandik(created_by=created_by, **kwargs)


def make_member(sandik, web_user=None, created_by=None, **overrides) -> Member:
    web_user = web_user or make_web_user(created_by=created_by)
    kwargs = dict(contribution_amount=sandik.contribution_amount)
    kwargs.update(overrides)
    return sandik_db.create_member(sandik=sandik, web_user=web_user, created_by=created_by, **kwargs)


def make_share(member, created_by, **overrides) -> Share:
    kwargs = dict(share_order_of_member=member.shares_set.count() + 1)
    kwargs.update(overrides)
    return sandik_db.create_share(member=member, created_by=created_by, **kwargs)


def make_member_with_share(sandik, web_user=None, created_by=None) -> Share:
    """En sık kullanılan durum: bir sandığa, tek hisseli bir üye ekler ve hisseyi döner."""
    member = make_member(sandik=sandik, web_user=web_user, created_by=created_by)
    return make_share(member=member, created_by=created_by)


def make_contribution(share, term, created_by, amount=None):
    return transaction_db.create_contribution(share=share, period=term, created_by=created_by, amount=amount)


def make_money_transaction(member, amount, created_by, type=MoneyTransaction.TYPE.REVENUE,
                           creation_type=MoneyTransaction.CREATION_TYPE.BY_MANUEL, **overrides) -> MoneyTransaction:
    return transaction_db.create_money_transaction(member_ref=member, created_by=created_by, amount=amount,
                                                    type=type, creation_type=creation_type, **overrides)


def make_sub_receipt(money_transaction, amount, created_by, **ref_kwargs):
    """`ref_kwargs` içinde tam olarak biri verilmelidir: contribution_ref / installment_ref / debt_ref."""
    return transaction_db.create_sub_receipt(money_transaction=money_transaction, amount=amount, is_auto=True,
                                             created_by=created_by, **ref_kwargs)


def pay_contribution_partially(share, term, paid_amount, created_by, contribution_amount=None):
    """Bir dönem için aidat oluşturur, bir MoneyTransaction ile kısmen (veya tam) öder.

    `paid_amount`, aidat tutarından büyükse fazlası MoneyTransaction'da işleme konmamış (undistributed)
    olarak kalır — "işleme konmamış para" senaryolarını kurmak için kullanılır.
    """
    contribution = make_contribution(share=share, term=term, created_by=created_by, amount=contribution_amount)
    mt = make_money_transaction(member=share.member_ref, amount=paid_amount, created_by=created_by)
    distributed = min(paid_amount, contribution.amount)
    if distributed > 0:
        make_sub_receipt(money_transaction=mt, amount=distributed, created_by=created_by,
                         contribution_ref=contribution)
    return contribution, mt


def make_debt(share, amount, created_by, number_of_installment, start_period=None, money_transaction=None):
    """Bir hisseye borç verir (para çıkışı + borç + taksitler).

    `create_debt` taksitleri ve — güven bağlı sandıkta — borç paylarını kendisi oluşturur, yani
    yuvarlama mantığının tamamı bu tek çağrının içindedir.
    """
    money_transaction = money_transaction or make_money_transaction(
        member=share.member_ref, amount=amount, created_by=created_by,
        type=MoneyTransaction.TYPE.EXPENSE)
    return transaction_db.create_debt(
        amount=amount, share=share, money_transaction=money_transaction, created_by=created_by,
        start_period=start_period or period_utils.current_period(),
        number_of_installment=number_of_installment)


def make_trust_relationship(requester_member, receiver_member, created_by):
    """İki üye arasında kabul edilmiş güven bağı kurar (güven bağlı sandık senaryoları için)."""
    return sandik_db.create_trust_relationship(
        requester_member=requester_member, receiver_member=receiver_member, created_by=created_by,
        status=TrustRelationship.STATUS.ACCEPTED)


def make_sandik_rule(sandik, created_by, type, value_formula, condition_formula="", order=1):
    """Sandık kuralı ekler (borç limiti, taksit sayısı, hisse sayısı formülleri)."""
    return sandik_db.create_sandik_rule(sandik=sandik, created_by=created_by, type=type, order=order,
                                        condition_formula=condition_formula, value_formula=value_formula)

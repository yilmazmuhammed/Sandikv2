import math

from dateutil.relativedelta import relativedelta

from sandik.sandik.exceptions import NoValidRuleFound
from sandik.utils import period as period_utils
from sandik.utils.db_models import Share, Member, SandikRule


def max_number_of_installment(sandik, amount, without_raise=False):
    for rule in sandik.sandik_rules_set.select(lambda r: r.type == SandikRule.TYPE.MAX_NUMBER_OF_INSTALLMENT):
        if rule.evaluate_condition_formula(amount=amount):
            return int(rule.evaluate_value_formula())
    else:
        if without_raise:
            return None
        raise NoValidRuleFound(f"\"{amount}₺\" borç için kaç taksit yapılacağını tespit etmek için geçerli kural bulunamadı!"
                               f"<br>Lütfen önce borç miktarı için kaç taksit yapılacağına dair sandık kuralı ekleyiniz.")


def get_start_period(sandik, debt_date):
    period_date = debt_date + relativedelta(months=1)
    return period_utils.date_to_period(period_date)


def remaining_debt_balance(sandik, whose, without_raise=False):
    if isinstance(whose, Share):
        for rule in sandik.sandik_rules_set.select(lambda r: r.type == SandikRule.TYPE.MAX_AMOUNT_OF_DEBT):
            if rule.evaluate_condition_formula(whose=whose):
                max_debt_of_share = rule.evaluate_value_formula(whose=whose)
                print(f"max_debt_of_share: {max_debt_of_share}")
                break
        else:
            if without_raise:
                return None
            raise NoValidRuleFound(f"Hissenin alabileceği borç miktarını tespit etmek için geçerli kural bulunamadı."
                                   f"<br>Lütfen önce açılabilecek en fazla hisse sayısı için sandık kuralı ekleyiniz."
                                   f"<br>Üye: {whose.name_surname}"
                                   f"<br>Hisse: {whose.id}"
                                   f"<br>Aidat miktarı: {whose.total_amount_of_paid_contribution()}")
        max_debt_balance = math.ceil(max_debt_of_share / 1000) * 1000
        max_debt_balance = max_debt_balance if max_debt_balance != 0 else 1000
        unpaid_installments_amount = whose.total_amount_unpaid_installments()
        return max_debt_balance - unpaid_installments_amount
    elif isinstance(whose, Member):
        return sum(remaining_debt_balance(sandik=sandik, whose=share) for share in whose.shares_set)
    else:
        raise Exception("whose 'Share' yada 'Member' olmalıdır")


def get_max_number_of_share(sandik, without_raise=False):
    for rule in sandik.sandik_rules_set.select(lambda r: r.type == SandikRule.TYPE.MAX_NUMBER_OF_SHARE):
        if rule.evaluate_condition_formula():
            return int(rule.evaluate_value_formula())
    else:
        if without_raise:
            return None
        raise NoValidRuleFound(f"Açılabilecek maksimum hisse sayısını tespit etmek için geçerli kural bulunamadı!"
                               f"<br>Lütfen önce açılabilecek en fazla hisse sayısı için sandık kuralı ekleyiniz.")

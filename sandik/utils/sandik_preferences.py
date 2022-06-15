import math

from dateutil.relativedelta import relativedelta

from sandik.sandik.exceptions import NoValidRuleFound
from sandik.utils import period as period_utils
from sandik.utils.db_models import Share, Member, SandikRule


def base_sandik_rule_function(sandik, rule_type, no_rule_msg, result_cast=None, **kwargs):
    for rule in sandik.sandik_rules_set.select(lambda r: r.type == rule_type):
        if rule.evaluate_condition_formula(**kwargs):
            if result_cast:
                return result_cast(rule.evaluate_value_formula(**kwargs))
            return rule.evaluate_value_formula(**kwargs)
    else:
        raise NoValidRuleFound(no_rule_msg)


def max_number_of_installment(sandik, amount):
    no_rule_msg = f"\"{amount}₺\" borç için kaç taksit yapılacağını tespit etmek için geçerli kural bulunamadı!" \
                  f"<br>Lütfen önce borç miktarı için kaç taksit yapılacağına dair sandık kuralı ekleyiniz."
    return base_sandik_rule_function(sandik=sandik, rule_type=SandikRule.TYPE.MAX_NUMBER_OF_INSTALLMENT,
                                     no_rule_msg=no_rule_msg, result_cast=int, amount=amount)


def get_start_period(sandik, debt_date):
    period_date = debt_date + relativedelta(months=1)
    return period_utils.date_to_period(period_date)


def remaining_debt_balance(sandik, whose):
    if isinstance(whose, Share):
        no_rule_msg = f"Hissenin alabileceği borç miktarını tespit etmek için geçerli kural bulunamadı." \
                      f"<br>Lütfen önce açılabilecek en fazla hisse sayısı için sandık kuralı ekleyiniz." \
                      f"<br>Üye: {whose.name_surname} <br>Hisse: {whose.id}" \
                      f"<br>Aidat miktarı: {whose.total_amount_of_paid_contribution()}"
        max_debt_of_share = base_sandik_rule_function(sandik=sandik, rule_type=SandikRule.TYPE.MAX_AMOUNT_OF_DEBT,
                                                      no_rule_msg=no_rule_msg, whose=whose)
        max_debt_balance = math.ceil(max_debt_of_share / 1000) * 1000
        max_debt_balance = max_debt_balance if max_debt_balance != 0 else 1000
        unpaid_installments_amount = whose.total_amount_unpaid_installments()
        return max_debt_balance - unpaid_installments_amount
    elif isinstance(whose, Member):
        return sum(remaining_debt_balance(sandik=sandik, whose=share) for share in whose.shares_set)
    else:
        raise Exception("whose 'Share' yada 'Member' olmalıdır")


def get_max_number_of_share(sandik):
    no_rule_msg = f"Açılabilecek maksimum hisse sayısını tespit etmek için geçerli kural bulunamadı!" \
                  f"<br>Lütfen önce açılabilecek hisse sayısı için sandık kuralı ekleyiniz."
    return base_sandik_rule_function(sandik=sandik, rule_type=SandikRule.TYPE.MAX_NUMBER_OF_SHARE,
                                     no_rule_msg=no_rule_msg, result_cast=int)

import math

from dateutil.relativedelta import relativedelta

from sandik.utils import period as period_utils
from sandik.utils.db_models import Share, Member


def max_number_of_installment(sandik, amount):
    if amount <= 0:
        return 0
    if 1 <= amount <= 2500:
        return 5
    elif 2501 <= amount <= 10000:
        return 10
    elif 10001 <= amount <= 22500:
        return 15
    elif 22500 <= amount <= 40000:
        return 20
    else:
        return 20


def get_start_period(sandik, debt_date):
    period_date = debt_date + relativedelta(months=1)
    return period_utils.date_to_period(period_date)


def remaining_debt_balance(sandik, whose):
    if isinstance(whose, Share):
        contribution_amount = whose.total_amount_of_paid_contribution()
        max_debt_balance = math.ceil(contribution_amount * 3 / 1000) * 1000
        max_debt_balance = max_debt_balance if max_debt_balance != 0 else 1000
        unpaid_installments_amount = whose.total_amount_unpaid_installments()
        return max_debt_balance - unpaid_installments_amount
    elif isinstance(whose, Member):
        return sum(remaining_debt_balance(sandik=sandik, whose=share) for share in whose.shares_set)
    else:
        raise Exception("whose 'Share' yada 'Member' olmalıdır")


def get_max_number_of_share(sandik):
    return 5

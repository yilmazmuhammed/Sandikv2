from datetime import date, datetime

from dateutil.relativedelta import relativedelta
from dateutil.rrule import MONTHLY, rrule

period_format_string = "%Y-%m"


class NotValidPeriod(Exception):
    pass


def date_to_period(period_date):
    return period_date.strftime(period_format_string)


def previous_period(prev_count=1):
    return get_period_by_difference(start_period=current_period(), diff_count=-prev_count)


def current_period():
    return date_to_period(date.today())


def next_period(next_count=1):
    return get_period_by_difference(start_period=current_period(), diff_count=next_count)


def is_valid_period(period):
    try:
        if not isinstance(period, str):
            raise NotValidPeriod(f"Period '{period}' is not valid: Period is not str)")
        if len(period) != 7:
            raise NotValidPeriod(f"Period '{period}' is not valid: Period len is not equal 7")
        period_to_date(period)
        return True
    except Exception:
        return False


def period_to_date(period):
    return datetime.strptime(period, period_format_string).date()


def get_periods_between_two_period(first_period: str, last_period: str):
    if not is_valid_period(first_period) or not is_valid_period(last_period):
        raise NotValidPeriod(f"Period '{first_period}' or '{last_period}' is not valid")

    if first_period > last_period:
        first_period, last_period = last_period, first_period

    first_month = period_to_date(first_period)
    last_month = period_to_date(last_period)
    periods = [date_to_period(dt.date()) for dt in rrule(MONTHLY, dtstart=first_month, until=last_month)]
    return periods


def get_period_by_difference(start_period, diff_count):
    start_date = period_to_date(start_period)
    finish_date = start_date + relativedelta(months=diff_count)
    return date_to_period(finish_date)


def get_last_installment_period(start_period, period_count):
    return get_period_by_difference(start_period=start_period, diff_count=period_count - 1)

import os
from datetime import date, datetime, time, timedelta
from json import JSONEncoder

from flask import g


class LayoutPI:
    website_name = "Sandık v2"
    short_website_name = "Sandık v2"

    def __init__(self, title, active_dropdown=None):
        self.title = title
        self.active_dropdown = active_dropdown
        g.now = tz_to_tr(datetime.now(), tz="UTC")


class CustomJSONEncoder(JSONEncoder):
    DATETIME_STR_FORMAT = os.getenv("DATETIME_STR_FORMAT", "%Y-%m-%d %H:%M:%S.%f")
    DATE_STR_FORMAT = os.getenv("DATE_STR_FORMAT", "%Y-%m-%d")
    TIME_STR_FORMAT = os.getenv("TIME_STR_FORMAT", "%H:%M")

    def default(self, obj):
        try:
            if isinstance(obj, datetime):
                return obj.strftime(self.DATETIME_STR_FORMAT)
            elif isinstance(obj, date):
                return obj.strftime(self.DATE_STR_FORMAT)
            elif isinstance(obj, time):
                return obj.strftime(self.TIME_STR_FORMAT)
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return JSONEncoder.default(self, obj)


def tz_to_tr(coming_time, tz="utc"):
    if tz.lower() == "utc":
        return coming_time + timedelta(hours=3)


def add_parameters_to_url(url, parameters):
    if "?" in url:
        url += "&"
    else:
        url += "?"
    for key, value in parameters.items():
        url += str(key) + "=" + str(value) + "&"
    url = url[:-1]
    return url


def set_parameters_of_url(url, parameters: dict):
    url_args = []
    if "?" in url:
        args_part = url[url.find("?") + 1:]
        url = url[:url.find("?")]
        url_args = [a.split("=") for a in args_part.split("&")]
    url += "?"

    for key, value in url_args:
        if key not in parameters.keys():
            url += f"{key}={value}&"

    for key, value in parameters.items():
        url += f"{key}={value}&"

    url = url[:-1]
    return url


def get_next_url(args, parameters=None, default_url=""):
    if parameters is None:
        parameters = {}
    next_url = args.get("next", default_url)
    if next_url:
        next_url = add_parameters_to_url(next_url, parameters)
    return next_url

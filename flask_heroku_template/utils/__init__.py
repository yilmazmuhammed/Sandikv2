from datetime import date

from flask.json import JSONEncoder


class CustomJSONEncoder(JSONEncoder):
    def default(self, obj):
        try:
            if isinstance(obj, date):
                return obj.isoformat()
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return JSONEncoder.default(self, obj)


class LayoutPI:
    def __init__(self, title):
        self.title = title
        self.website_name = "Website name"
        self.short_website_name = "Short website name"

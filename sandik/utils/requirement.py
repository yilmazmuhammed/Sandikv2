from functools import wraps

from flask import request, redirect, g

from sandik.utils import set_parameters_of_url


def paging_must_be_verified(default_page_num=1, default_page_size=50):
    def paging_must_be_verified_decorator(func):
        @wraps(func)
        def decorated_view(*args, **kwargs):
            should_redirected = False

            try:
                page = int(request.args.get("page", default_page_num))
                if page < 1:
                    raise ValueError("page, 1'den küçük olamaz!")
            except ValueError:
                page = default_page_num
                should_redirected = True

            try:
                size = int(request.args.get("size", default_page_size))
                if size < 1:
                    raise ValueError("size, 1'den küçük olamaz!")
            except ValueError:
                size = default_page_size
                should_redirected = True

            if should_redirected:
                return redirect(set_parameters_of_url(request.url, {"size": size, "page": page}))

            g.page_num, g.page_size = page, size
            return func(*args, **kwargs)

        return decorated_view

    return paging_must_be_verified_decorator

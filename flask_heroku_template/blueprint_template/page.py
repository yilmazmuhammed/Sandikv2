from flask import Blueprint, request, render_template, g

from flask_heroku_template.utils import LayoutPI

blueprint_template_page_bp = Blueprint(
    'blueprint_template_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@blueprint_template_page_bp.route('/example')
def example_page():
    # # Example for http://127.0.0.1:5000/blueprint_template/example?arg0=55&arg1=asd&arg1=qwe
    print("request.args:\t", request.args, "\n")
    for i in request.args:
        print("arg:\t\t", i)
        print("get:\t\t", request.args.get(i))
        print("getlist:\t", request.args.getlist(i))
        print()
    g.arg0 = request.args.get('arg0')
    g.args = request.args
    return render_template("blueprint_template/example_page.html", page_info=LayoutPI(title="Page title"))

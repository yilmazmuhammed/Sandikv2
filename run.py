import os

from dotenv import load_dotenv

project_folder = os.path.expanduser('~/Sandikv2')  # adjust as appropriate
load_dotenv(os.path.join(project_folder, '.env'))

from sandik.app import create_app

app = create_app()
if __name__ == '__main__':
    app.run(debug=True)

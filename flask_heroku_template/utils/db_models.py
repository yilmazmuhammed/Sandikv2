import os
from pony.orm import *

db = Database()


class FirstTable(db.Entity):
    id = PrimaryKey(int, auto=True)


DATABASE_URL = os.getenv("DATABASE_URL")
if os.getenv("DATABASE_URL"):
    db.bind(provider="postgres", dsn=DATABASE_URL)
else:
    db.bind(provider="sqlite", filename='database.sqlite', create_db=True)

db.generate_mapping(create_tables=True)

if __name__ == '__main__':
    with db_session:
        # Initialize operations
        pass

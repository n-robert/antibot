import os
import traceback
import psycopg2
import psycopg2.extras
import json
from dotenv import load_dotenv
from operator import itemgetter

load_dotenv()

# database_url = os.environ['DATABASE_URL']

host = os.environ['DATABASE_HOST']
port = os.environ['DATABASE_PORT']
database = os.environ['DATABASE_NAME']
user = os.environ['DATABASE_USER']
password = os.environ['DATABASE_PASSWORD']
tables = {
    'users': {
        'id': 'SERIAL NOT NULL PRIMARY KEY',
        'user_id': 'BIGINT NOT NULL',
        'chat_id': 'BIGINT NOT NULL',
        'status': 'VARCHAR (8) DEFAULT NULL',
        'joined_at': 'TIMESTAMP DEFAULT NULL',
        'left_at': 'TIMESTAMP DEFAULT NULL',
        'banned_at': 'TIMESTAMP DEFAULT NULL',
        'args': 'JSON DEFAULT NULL',
        '': 'UNIQUE (user_id, chat_id)',
    },
    'messages': {
        'id': 'SERIAL NOT NULL PRIMARY KEY',
        'message_id': 'BIGINT NOT NULL',
        'chat_id': 'BIGINT NOT NULL',
        'user_id': 'BIGINT NOT NULL',
        'type': 'VARCHAR (32) NOT NULL DEFAULT \'message\'',
        'payload': 'VARCHAR (256) DEFAULT NULL',
        'pinned': 'BOOLEAN NOT NULL DEFAULT FALSE',
        '': 'UNIQUE (user_id, chat_id)',
    },
}
conflicts = {
    'users': 'user_id, chat_id',
    'messages': 'user_id, chat_id',
}


def connect():
    # return psycopg2.connect(database_url)
    return psycopg2.connect(host=host, port=port, database=database, user=user, password=password)


def init():
    with connect() as con, con.cursor() as cur:
        for table, schema in tables.items():
            columns = ', '.join(list(map(
                lambda x, y: f'"{x}" {y}' if x else y,
                schema.keys(),
                schema.values()
            )))
            cur.execute(f'CREATE TABLE IF NOT EXISTS {table} ({columns})')


def fetchall(**kwargs):
    return fetch('all', **kwargs)


def fetchone(**kwargs):
    return fetch('one', **kwargs)


def fetch(rows, **kwargs):
    where = []
    if chat_id := kwargs.get('chat_id'):
        where.append(f'chat_id = {chat_id}')
    if user_id := kwargs.get('user_id'):
        where.append(f'user_id = {user_id}')
    if message_id := kwargs.get('message_id'):
        where.append(f'message_id = {message_id}')

    with connect() as con, con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        statement = f"SELECT * FROM {kwargs.get('table')}"
        statement += f" WHERE {' AND '.join(where)}" if where else ""
        statement += f" ORDER BY {kwargs.get('order_by')}" if kwargs.get('order_by') else ""
        statement += " DESC" if kwargs.get('desc') else ""
        statement += f" LIMIT {kwargs.get('limit')}" if kwargs.get('limit') else ""
        cur.execute(statement)

        try:
            if callable(func := getattr(cur, f'fetch{rows}')):
                return func()
        except BaseException:
            traceback.print_exc()


def upsert(table, data):
    result = True
    columns = []
    values = []
    set_clause = []
    conflict = conflicts.get(table)

    where = []
    if chat_id := data.get('chat_id'):
        where.append(f'{table}.chat_id = {chat_id}')
    if user_id := data.get('user_id'):
        where.append(f'{table}.user_id = {user_id}')

    if type(data) == dict and data.items():
        for column, value in data.items():
            if column not in tables[table]:
                continue

            if column == 'args':
                value = f"'{json.dumps(value)}'"
            elif hasattr(value, 'isnumeric') and value.isnumeric():
                value = int(value)
            elif isinstance(value, str):
                value = f"'{value}'"

            if value:
                columns.append(f"{column}")
                values.append(f"{value}")
                set_clause.append(f"{column} = {value}")

    try:
        with connect() as con, con.cursor() as cur:
            cur.execute(f"""
                INSERT INTO {table} ({', '.join(columns)}) 
                VALUES ({', '.join(values)}) 
                ON CONFLICT ({conflict}) 
                DO UPDATE 
                SET {', '.join(set_clause)} 
                WHERE {' AND '.join(where)}
            """)
    except BaseException:
        result = False
        traceback.print_exc()

    return result


def test(table='users'):
    with connect() as con, con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(f'SELECT * FROM {table}')
        rows = cur.fetchall()

        for row in rows:
            string = ''

            for key in row.keys():
                string += f'{key}: {row[key]},'

            print(string)

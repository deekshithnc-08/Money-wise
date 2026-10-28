"""Small DB-API adapter for remote libSQL; no local replicas or ephemeral storage."""
class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor
        self.names = [item[0] for item in cursor.description or ()]

    def fetchone(self):
        values = self.cursor.fetchone()
        return None if values is None else Row(zip(self.names, values))

    def fetchall(self):
        return [Row(zip(self.names, values)) for values in self.cursor.fetchall()]

    def __iter__(self):
        while True:
            row = self.fetchone()
            if row is None:
                return
            yield row


class RemoteConnection:
    def __init__(self, url, token):
        import libsql
        self.connection = libsql.connect(url, auth_token=token, timeout=15)
        self.connection.execute('PRAGMA foreign_keys=ON')

    def execute(self, sql, parameters=()):
        return Cursor(self.connection.execute(sql, parameters))

    def executescript(self, script):
        # The app's schema contains no SQL strings with embedded semicolons.
        # Execute separately so the driver propagates every schema error.
        for statement in script.split(';'):
            if statement.strip():
                self.connection.execute(statement)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()
        return False

import importlib.util
import os
import unittest
from unittest.mock import patch
import server
from database import RemoteConnection
import test_app


@unittest.skipUnless(importlib.util.find_spec('libsql'), 'Install requirements.txt to test libSQL adapter')
class LibSQLTests(test_app.AppTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter_patch = patch.object(server, 'db', lambda: RemoteConnection(server.DB, ''))
        cls.adapter_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.adapter_patch.stop()
        super().tearDownClass()


class VercelConfigurationTests(unittest.TestCase):
    def test_vercel_refuses_ephemeral_sqlite(self):
        with patch.dict(os.environ, {'VERCEL':'1','TURSO_DATABASE_URL':'','TURSO_AUTH_TOKEN':''}):
            with self.assertRaisesRegex(RuntimeError, 'Persistent Turso'):
                server.db()

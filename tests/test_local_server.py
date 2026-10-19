from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from deploy.local_server import ensure_database, load_local_environment, validate_local_database


class LocalServerTests(unittest.TestCase):
    def test_only_local_mysql_connections_are_allowed(self):
        for raw in ('', 'not-a-url', 'mysql+pymysql://user@db.example.com/peredacha',
                    'sqlite:///local.db',
                    'mysql+pymysql://user@127.0.0.1/bad-name',
                    'mysql+pymysql://user@localhost/peredacha?unix_socket=/other/mysql.sock'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_local_database(raw)
        self.assertEqual(validate_local_database('mysql+pymysql://user@127.0.0.1/peredacha').host, '127.0.0.1')

    def test_local_config_is_private_and_stable_on_repeated_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env.local'
            _, environment = load_local_environment(path)
            original = path.read_bytes()
            _, repeated = load_local_environment(path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(environment['SECRET_KEY'], repeated['SECRET_KEY'])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(environment['SYNC_ON_STARTUP'], 'false')
            self.assertEqual(environment['TRUSTED_PROXY_COUNT'], '0')
            self.assertEqual(environment['SESSION_COOKIE_SECURE'], 'false')
            self.assertNotIn('WTF_CSRF_ENABLED', environment)

    def test_existing_remote_config_is_rejected_without_modification(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env.local'
            path.write_text("DATABASE_URL=mysql+pymysql://user@remote.example/production\nSECRET_KEY=local\n")
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                load_local_environment(path)
            self.assertEqual(path.read_bytes(), original)

    def test_database_setup_never_drops_or_imports_existing_data(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        url = validate_local_database('mysql+pymysql://user@localhost/peredacha')
        with patch('deploy.local_server.connect_local', return_value=connection), patch('deploy.local_server.subprocess.run') as run:
            ensure_database(url)
        cursor.execute.assert_called_once_with('CREATE DATABASE IF NOT EXISTS `peredacha` CHARACTER SET utf8mb4')
        run.assert_not_called()

    def test_authentication_error_does_not_restart_database_service(self):
        import pymysql
        with patch('deploy.local_server.connect_local', side_effect=pymysql.err.OperationalError(1045, 'Access denied')), patch('deploy.local_server.subprocess.run') as run:
            with self.assertRaises(pymysql.err.OperationalError):
                ensure_database(validate_local_database('mysql+pymysql://user@localhost/peredacha'))
        run.assert_not_called()

    def test_stopped_database_is_started_and_retried(self):
        import pymysql
        connection = MagicMock()
        with patch('deploy.local_server.connect_local', side_effect=[pymysql.err.OperationalError(2002, 'Stopped'), connection]), patch('deploy.local_server.shutil.which', return_value='/brew'), patch('deploy.local_server.subprocess.run') as run:
            ensure_database(validate_local_database('mysql+pymysql://user@localhost/peredacha'))
        run.assert_called_once_with(['/brew', 'services', 'start', 'mariadb'], check=True)

    def test_missing_secret_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env.local'
            path.write_text('DATABASE_URL=mysql+pymysql://user@localhost/peredacha\n')
            with self.assertRaisesRegex(ValueError, 'SECRET_KEY'):
                load_local_environment(path)

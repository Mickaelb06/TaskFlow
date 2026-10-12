from django.test import SimpleTestCase

from .dburl import parse_database_url


class DatabaseUrlTests(SimpleTestCase):
    def test_adresse_complete(self):
        cfg = parse_database_url("postgresql://bob:p%40ss@db.internal:5433/taskflow")
        self.assertEqual(cfg["USER"], "bob")
        self.assertEqual(cfg["PASSWORD"], "p@ss")
        self.assertEqual(cfg["HOST"], "db.internal")
        self.assertEqual(cfg["PORT"], "5433")
        self.assertEqual(cfg["NAME"], "taskflow")

    def test_port_par_defaut(self):
        self.assertEqual(parse_database_url("postgres://u:p@h/base")["PORT"], "5432")

    def test_refuse_un_autre_moteur(self):
        with self.assertRaises(ValueError):
            parse_database_url("mysql://u:p@h/base")

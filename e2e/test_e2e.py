"""Tests de bout en bout dans un VRAI navigateur (Firefox headless piloté par Selenium).

Ils démarrent leur propre API (base SQLite temporaire, données de démonstration) et leur propre serveur de front,
puis agissent comme un utilisateur : connexion, calendrier (créer / glisser / redimensionner), messagerie (mentions,
notifications entre deux comptes), fuseaux horaires, suppression de compte. Lancer : `./test-e2e.sh`.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parent.parent
API_PORT, FRONT_PORT = 8010, 5180
API = f"http://localhost:{API_PORT}/api"
FRONT = f"http://localhost:{FRONT_PORT}"
PW = "demo-taskflow-2026"
FIREFOX = os.environ.get("FIREFOX_BIN", "/Applications/Firefox.app/Contents/MacOS/firefox")

_tmp = None
_procs = []
_httpd = None


def _free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def setUpModule():
    global _tmp, _httpd
    assert _free(API_PORT) and _free(FRONT_PORT), f"Les ports {API_PORT} et {FRONT_PORT} doivent être libres."
    _tmp = Path(tempfile.mkdtemp(prefix="taskflow-e2e-"))
    env = {**os.environ, "USE_SQLITE": "1", "SQLITE_PATH": str(_tmp / "e2e.sqlite3"), "MEDIA_ROOT": str(_tmp / "media"),
           "LOGIN_RATE": "1000/min", "REGISTER_RATE": "1000/hour", "CHAT_RATE": "1000/min", "ACCOUNT_RATE": "1000/hour",
           "DJANGO_DEBUG": "1", "DJANGO_SECRET_KEY": "e2e-secret-key-e2e-secret-key-e2e-secret"}
    py = ROOT / "backend" / ".venv" / "bin" / "python"
    for cmd in (["manage.py", "migrate", "-v0"], ["manage.py", "seed_demo"]):
        subprocess.run([str(py), *cmd], cwd=ROOT / "backend", env=env, check=True, capture_output=True)
    _procs.append(subprocess.Popen([str(py), "manage.py", "runserver", str(API_PORT), "--noreload"], cwd=ROOT / "backend", env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    front = _tmp / "front"
    shutil.copytree(ROOT / "frontend", front, ignore=shutil.ignore_patterns("tests", "__pycache__"))
    (front / "config.js").write_text(f'window.TASKFLOW_API = "{API}";\n')
    _httpd = ThreadingHTTPServer(("127.0.0.1", FRONT_PORT), partial(_NoCache, directory=str(front)))
    threading.Thread(target=_httpd.serve_forever, daemon=True).start()
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://localhost:{API_PORT}/health/", timeout=1)
            break
        except OSError:
            time.sleep(0.3)
    else:
        raise RuntimeError("L'API de test ne démarre pas")


def tearDownModule():
    for p in _procs:
        p.terminate()
    if _httpd:
        _httpd.shutdown()
    shutil.rmtree(_tmp, ignore_errors=True)


class _NoCache(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


def api(method, path, token=None, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def token(user):
    return api("POST", "/auth/token/", body={"username": user, "password": PW})["access"]


class Browser:
    """Un navigateur connecté en tant que `user`."""

    def __init__(self, user=None, password=PW, size=(1440, 900), tz=None):
        o = Options()
        o.add_argument("-headless")
        o.binary_location = FIREFOX
        o.set_preference("intl.accept_languages", "fr-FR")
        self.d = webdriver.Firefox(options=o)
        self.d.set_window_size(*size)
        self.w = WebDriverWait(self.d, 12)
        self.d.get(FRONT)
        if user:
            self.login(user, password)

    def login(self, user, password=PW):
        self.w.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#login-form")))
        form = self.d.find_element(By.ID, "login-form")
        form.find_element(By.NAME, "username").send_keys(user)
        form.find_element(By.NAME, "password").send_keys(password)
        form.find_element(By.CSS_SELECTOR, "button").click()
        self.w.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#sidebar .navitem")))

    def q(self, css, root=None):
        return (root or self.d).find_element(By.CSS_SELECTOR, css)

    def qs(self, css, root=None):
        return (root or self.d).find_elements(By.CSS_SELECTOR, css)

    def wait(self, css, timeout=12):
        return WebDriverWait(self.d, timeout).until(EC.visibility_of_element_located((By.CSS_SELECTOR, css)))

    def click(self, css):
        el = self.w.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css)))
        el.click()
        return el

    def go(self, action, wait_css):
        self.click(f'#sidebar [data-action="{action}"]')
        return self.wait(wait_css)

    def no_fatal(self):
        return not self.qs("#fatal")

    def text(self, css):
        return self.q(css).text

    def quit(self):
        self.d.quit()

    def token(self):
        return self.d.execute_script("return localStorage.getItem('access')")


class E2E(unittest.TestCase):
    br = None

    @classmethod
    def setUpClass(cls):
        cls.br = Browser("demo")

    @classmethod
    def tearDownClass(cls):
        cls.br.quit()

    def setUp(self):
        self.br.d.get(FRONT)
        self.br.wait("#sidebar .navitem")

    def tearDown(self):
        self.assertTrue(self.br.no_fatal(), "bandeau d'erreur JavaScript affiché")

    # ------------------------------------------------------------------ tableau de bord et barre latérale
    def test_01_dashboard_and_sidebar(self):
        b = self.br
        b.wait(".dash-hello")
        self.assertIn("Bonjour demo", b.text(".dash-hello h2"))
        self.assertGreaterEqual(len(b.qs("#sidebar svg.i")), 6, "icônes SVG de la barre latérale")
        for action in ("go-home", "go-calendar", "go-messages", "go-notifications", "go-admin", "account", "toggle-side"):
            self.assertTrue(b.qs(f'#sidebar [data-action="{action}"]'), action)
        self.assertEqual(b.text("#toolbar h1"), "Tableau de bord")  # pas « Tableau De Bord »
        self.assertEqual(len(b.qs("#sidebar .proj")), 2)

    def test_02_sidebar_collapses_and_expands(self):
        b = self.br
        width = lambda: b.q("#sidebar").size["width"]
        full = width()
        b.click('#sidebar [data-action="toggle-side"]')
        time.sleep(0.4)
        self.assertLess(width(), full / 2)
        b.click('#sidebar [data-action="toggle-side"]')
        time.sleep(0.4)
        self.assertGreater(width(), full * 0.9)

    def test_03_project_views_render(self):
        b = self.br
        b.click('#sidebar .proj[data-action="select-project"]:last-child')
        b.wait(".kpi")
        for view in ("gantt", "team", "list", "board", "dashboard"):
            b.click(f'#toolbar [data-view="{view}"]')
            time.sleep(0.4)
            self.assertTrue(b.no_fatal(), view)
            self.assertTrue(b.q("#view").text.strip(), f"vue {view} vide")

    # ------------------------------------------------------------------ calendrier
    def open_week(self):
        b = self.br
        b.go("go-calendar", ".cal")
        if not b.qs('#toolbar [data-mode="week"].on'):
            b.click('#toolbar [data-mode="week"]')
        b.wait(".ccol")
        return b

    def event_el(self, title):
        for el in self.br.qs(".cevent"):
            if title in el.text:
                return el
        self.fail(f"événement « {title} » introuvable à l'écran")

    def event_by_title(self, title):
        events = api("GET", "/events/", self.br.token())
        return next(e for e in events if e["title"] == title)

    def test_10_calendar_week_shows_events_tasks_and_now_line(self):
        b = self.open_week()
        self.assertEqual(len(b.qs(".ccol")), 7)
        titles = " ".join(e.text for e in b.qs(".cevent"))
        for t in ("Point quotidien", "Déjeuner", "Sport"):
            self.assertIn(t, titles)
        self.assertTrue(b.qs(".cevent.series"), "série marquée")
        self.assertTrue(b.qs(".cevent.pending"), "invitation en attente en pointillés")
        self.assertTrue(b.qs(".ctask"), "tâches à la journée")
        self.assertIn("Paris", b.text(".tzbtn"))

    def test_11_create_event_by_clicking_the_grid(self):
        b = self.open_week()
        col = b.qs(".ccol")[3]  # jeudi
        ActionChains(b.d).move_to_element_with_offset(col, 0, -150).click().perform()
        b.wait("#modal .modal-card")
        b.q('#modal input[name="title"]').send_keys("Rendez-vous E2E")
        b.q('#modal button[value="ok"]').click()
        b.w.until(lambda d: any("Rendez-vous E2E" in e.text for e in b.qs(".cevent")))
        self.assertEqual(self.event_by_title("Rendez-vous E2E")["timezone"], "Europe/Paris")

    def test_12_create_event_by_dragging_a_range(self):
        b = self.open_week()
        col = b.qs(".ccol")[1]
        ActionChains(b.d).move_to_element_with_offset(col, 0, -100).click_and_hold().move_by_offset(0, 96).release().perform()
        b.wait("#modal .modal-card")
        start, end = b.q('#modal input[name="st"]').get_attribute("value"), b.q('#modal input[name="et"]').get_attribute("value")
        length = (int(end[:2]) * 60 + int(end[3:])) - (int(start[:2]) * 60 + int(start[3:]))
        self.assertTrue(120 <= length <= 135, length)  # 96 px = 2 h, arrondi au quart d'heure qui englobe la zone balayée
        b.click('#modal button[value="cancel"]')

    def test_13_drag_an_event_to_another_day_and_time(self):
        b = self.open_week()
        before = self.event_by_title("Déjeuner")
        el = self.event_el("Déjeuner")
        col_w = b.qs(".ccol")[1].size["width"]
        ActionChains(b.d).move_to_element(el).click_and_hold().move_by_offset(col_w, 96).release().perform()
        b.w.until(lambda d: self.event_by_title("Déjeuner")["starts_at"] != before["starts_at"])
        after = self.event_by_title("Déjeuner")
        from datetime import datetime
        delta = datetime.fromisoformat(after["starts_at"]) - datetime.fromisoformat(before["starts_at"])
        self.assertEqual(delta.total_seconds(), 86400 + 2 * 3600)  # un jour plus tard, 2 h plus tard
        self.assertEqual(datetime.fromisoformat(after["ends_at"]) - datetime.fromisoformat(after["starts_at"]),
                         datetime.fromisoformat(before["ends_at"]) - datetime.fromisoformat(before["starts_at"]))  # durée conservée

    def test_14_resize_an_event(self):
        b = self.open_week()
        before = self.event_by_title("Sport")
        el = self.event_el("Sport")
        handle = b.q(".cevent-resize", el)
        ActionChains(b.d).move_to_element(handle).click_and_hold().move_by_offset(0, 48).release().perform()
        b.w.until(lambda d: self.event_by_title("Sport")["ends_at"] != before["ends_at"])
        after = self.event_by_title("Sport")
        from datetime import datetime
        self.assertEqual((datetime.fromisoformat(after["ends_at"]) - datetime.fromisoformat(before["ends_at"])).total_seconds(), 3600)
        self.assertEqual(after["starts_at"], before["starts_at"])  # le début ne bouge pas

    def test_15_a_simple_click_opens_the_event_without_moving_it(self):
        b = self.open_week()
        before = self.event_by_title("Atelier d'écriture du contenu")
        self.event_el("Atelier d'écriture").click()
        b.wait("#modal .modal-card")
        self.assertEqual(b.q('#modal input[name="title"]').get_attribute("value"), "Atelier d'écriture du contenu")
        b.click('#modal button[value="cancel"]')
        self.assertEqual(self.event_by_title("Atelier d'écriture du contenu")["starts_at"], before["starts_at"])

    def test_16_series_modal_and_skip_one_occurrence(self):
        b = self.open_week()
        series = next(e for e in b.qs(".cevent.series") if "Point quotidien" in e.text)
        count = len([e for e in b.qs(".cevent") if "Point quotidien" in e.text])
        series.click()
        b.wait("#modal .modal-card")
        self.assertIn("toute la série", b.text("#modal"))
        self.assertEqual(b.q('#modal select[name="recurrence"]').get_attribute("value"), "weekdays")
        b.click('#modal button[value="delete-one"]')
        b.w.until(lambda d: len([e for e in b.qs(".cevent") if "Point quotidien" in e.text]) == count - 1)

    def test_17_invitation_can_be_accepted_from_the_event(self):
        b = self.open_week()
        self.event_el("Démo au client").click()
        b.wait("#modal .rsvp")
        b.click('#modal [data-rsvp="accepted"]')
        b.w.until(lambda d: not b.qs("#modal[open]"))
        ev = self.event_by_title("Démo au client")
        self.assertEqual(ev["my_status"], "accepted")

    def test_18_changing_timezone_shifts_every_hour(self):
        b = self.open_week()
        def lunch():
            from selenium.common.exceptions import StaleElementReferenceException
            try:
                return next((e.text for e in b.qs(".cevent") if "Atelier d'écriture" in e.text), "")
            except StaleElementReferenceException:
                return ""
        self.assertIn("16:00", lunch())
        b.click('[data-action="tz-settings"]')
        b.wait('#modal select[name="tz"]')
        from selenium.webdriver.support.ui import Select
        Select(b.q('#modal select[name="tz"]')).select_by_value("Asia/Tokyo")
        b.q('#modal button[value="ok"]').click()
        b.w.until(lambda d: "Tokyo" in b.text(".tzbtn"))
        b.w.until(lambda d: "23:00" in lunch())  # 16 h à Paris (UTC+2) = 23 h à Tokyo (UTC+9)
        b.click('[data-action="tz-settings"]')  # remet Paris pour les tests suivants
        b.wait('#modal select[name="tz"]')
        Select(b.q('#modal select[name="tz"]')).select_by_value("Europe/Paris")
        b.q('#modal button[value="ok"]').click()
        b.w.until(lambda d: "Paris" in b.text(".tzbtn"))

    def test_19_month_view_and_navigation(self):
        b = self.open_week()
        b.click('#toolbar [data-mode="month"]')
        b.wait(".mcell")
        self.assertEqual(len(b.qs(".mcell")), 42)
        self.assertTrue(b.qs(".mevent"))
        title = b.text(".cal-title")
        b.click('#toolbar [data-action="cal-next"]')
        b.w.until(lambda d: b.text(".cal-title") != title)
        b.click('#toolbar [data-action="cal-today"]')
        b.click('#toolbar [data-mode="week"]')

    # ------------------------------------------------------------------ messagerie
    def open_conv(self, title, b=None):
        """Ouvre un fil par son titre. La liste se repeint pendant le chargement : on réessaie si l'élément a été remplacé."""
        from selenium.common.exceptions import StaleElementReferenceException
        b = b or self.br
        b.go("go-messages", ".chat")
        for _ in range(6):
            try:
                rows = b.qs('.crow[data-action="open-conv"]')
                row = next((r for r in rows if r.text.startswith(title)), None)
                if row is not None:
                    row.click()
                    b.w.until(lambda d: title in b.text(".thread-head h2"))
                    b.wait("#chat-input")
                    return b
            except StaleElementReferenceException:
                pass
            time.sleep(0.5)
        self.fail(f"fil « {title} » introuvable")

    def open_team_chat(self, b=None):
        return self.open_conv("Site web", b)

    def test_20_mention_autocomplete_and_send(self):
        b = self.open_team_chat()
        box = b.q("#chat-input")
        box.send_keys("Bonjour @l")
        b.wait("#mention-pop .mention-item")
        self.assertIn("lea", b.text("#mention-pop"))
        self.assertNotIn("demo", b.text("#mention-pop"))
        box.send_keys(Keys.ENTER)
        self.assertEqual(box.get_attribute("value"), "Bonjour @lea ")
        box.send_keys("peux-tu relire ? <img src=x onerror=window.__xss=1>", Keys.ENTER)
        b.w.until(lambda d: "peux-tu relire" in b.text("#chat-msgs"))
        last = b.qs(".cmsg")[-1]
        self.assertTrue(b.qs(".mention", last))
        self.assertIn("<img src=x", b.q(".cmsg-text", last).text)  # affiché comme du texte...
        self.assertFalse(b.qs(".cmsg-text img", last))              # ... jamais interprété
        self.assertIsNone(b.d.execute_script("return window.__xss || null"))
        self.assertEqual(box.get_attribute("value"), "")

    def test_21_other_user_is_notified_and_opens_the_thread(self):
        lea = Browser("lea")
        try:
            lea.w.until(lambda d: lea.qs("#sidebar .bell .ncount"))
            before = int(lea.text("#sidebar .bell .ncount"))
            self.open_team_chat()
            self.br.q("#chat-input").send_keys("Test notification @lea", Keys.ENTER)
            self.br.w.until(lambda d: "Test notification" in self.br.text("#chat-msgs"))
            WebDriverWait(lea.d, 30).until(lambda d: int(lea.qs("#sidebar .bell .ncount")[0].text or 0) > before)
            lea.click('#sidebar [data-action="go-notifications"]')
            lea.wait(".notif.unread")
            self.assertIn("demo", lea.text(".notifs"))
            lea.qs('.notif[data-action="open-notif"]')[0].click()
            lea.wait("#chat-input")
            self.assertIn("Test notification", lea.text("#chat-msgs"))
            self.assertTrue(lea.qs(".cmsg.tagged"), "message qui mentionne lea mis en évidence")
        finally:
            lea.quit()

    def test_22_task_reference_with_hash(self):
        b = self.open_team_chat()
        box = b.q("#chat-input")
        box.send_keys("voir #")
        b.wait("#mention-pop .mention-item")
        self.assertTrue(b.qs("#mention-pop .tnum"))
        box.send_keys(Keys.ENTER)
        self.assertRegex(box.get_attribute("value"), r"^voir #\d+ $")
        box.send_keys("pour demain", Keys.ENTER)
        b.w.until(lambda d: b.qs(".tchip"))
        chip = b.q(".tchip")
        chip.click()
        b.wait(".title-input")  # le panneau de la tâche s'ouvre

    def test_23_reaction_reply_edit_and_delete(self):
        b = self.open_team_chat()
        box = b.q("#chat-input")
        box.send_keys("Message à manipuler", Keys.ENTER)
        b.w.until(lambda d: "Message à manipuler" in b.text("#chat-msgs"))
        msg = b.qs(".cmsg")[-1]
        ActionChains(b.d).move_to_element(msg).perform()
        b.q('[data-action="react-pop"]', msg).click()
        b.w.until(lambda d: b.qs(".react-picker"))
        b.qs(".react-picker button")[0].click()
        b.w.until(lambda d: b.qs(".react.mine"))
        msg = b.qs(".cmsg")[-1]
        ActionChains(b.d).move_to_element(msg).perform()
        b.q('[data-action="edit-msg"]', msg).click()
        area = b.wait("#edit-input")
        area.clear()
        area.send_keys("Message modifié", Keys.ENTER)
        b.w.until(lambda d: "Message modifié" in b.text("#chat-msgs"))
        self.assertIn("(modifié)", b.text("#chat-msgs"))
        msg = b.qs(".cmsg")[-1]
        ActionChains(b.d).move_to_element(msg).perform()
        b.q('[data-action="reply"]', msg).click()
        b.wait("#reply-bar:not([hidden])")
        box.send_keys("Réponse", Keys.ENTER)
        b.w.until(lambda d: b.qs(".cmsg-quote"))
        msg = b.qs(".cmsg")[-1]
        ActionChains(b.d).move_to_element(msg).perform()
        b.q('[data-action="delete-message"]', msg).click()
        b.d.switch_to.alert.accept()
        b.w.until(lambda d: "Réponse" not in b.text("#chat-msgs"))

    def test_24_attachment_upload_and_download(self):
        b = self.open_team_chat()
        png = _tmp / "pixel.png"
        import base64
        png.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))
        b.d.execute_script("arguments[0].hidden = false; arguments[0].style.display='block'", b.q("#chat-file"))
        b.q("#chat-file").send_keys(str(png))
        b.wait(".file-chip")
        b.q("#chat-input").send_keys("avec image", Keys.ENTER)
        b.w.until(lambda d: b.qs(".att.img img"))
        b.w.until(lambda d: b.d.execute_script("return arguments[0].naturalWidth", b.qs(".att.img img")[-1]) > 0)  # chargée avec le jeton

    def test_25_search_messages(self):
        b = self.open_team_chat()
        b.q("#chat-search").send_keys("maquettes")
        b.wait('#chat-convs .crow.hit')
        self.assertIn("maquettes", b.text("#chat-convs").lower())
        b.qs("#chat-convs .crow.hit")[0].click()
        b.wait(".cmsg.flash, .cmsg")
        b.q("#chat-search").clear()

    def test_26_solo_notebook_has_no_mentions(self):
        b = self.open_conv("Perso")
        self.assertIn("Bloc-notes personnel", b.text(".thread-head"))
        b.q("#chat-input").send_keys("@")
        time.sleep(0.5)
        self.assertFalse(b.q("#mention-pop").is_displayed(), "aucune proposition dans un bloc-notes")
        b.q("#chat-input").clear()


    # ------------------------------------------------------------------ gestion de projet
    def open_project(self, name="Site web"):
        b = self.br
        row = next(r for r in b.qs('#sidebar .proj[data-action="select-project"]') if name in r.text)
        row.click()
        b.wait('#toolbar [data-view="dashboard"]')  # la vue affichée dépend de la dernière utilisée
        return b

    def has_text(self, css, text):
        """True si un élément correspondant à `css` contient `text` (insensible aux repeints du DOM)."""
        from selenium.common.exceptions import StaleElementReferenceException
        try:
            return any(text in e.text for e in self.br.qs(css))
        except StaleElementReferenceException:
            return False

    def project_id(self, name="Site web"):
        return next(p["id"] for p in api("GET", "/projects/", self.br.token()) if name in p["name"])

    def test_40_workload_heatmap_and_delay_simulation(self):
        b = self.open_project()
        b.click('#toolbar [data-view="workload"]')
        b.wait(".wl-grid")
        self.assertTrue(b.qs(".wl-cell"))
        b.w.until(lambda d: b.qs(".sim-row"))
        first = b.text(".sim-row")
        self.assertRegex(b.text(".sim"), r"\+\d+ j|absorbé")
        from selenium.webdriver.support.ui import Select
        Select(b.q('select[data-wl="delay"]')).select_by_value("10")
        b.w.until(lambda d: b.qs(".sim-row") and "10 jours" in b.q('select[data-wl="delay"] option:checked').text)
        Select(b.q('select[data-wl="weeks"]')).select_by_value("8")
        b.w.until(lambda d: len(b.qs(".wl-head")) == 9)  # colonne vide + 8 semaines
        b.click('#toolbar [data-view="dashboard"]')

    def test_41_timer_and_manual_time(self):
        b = self.open_project()
        b.click('#toolbar [data-view="list"]')
        b.wait(".task-row")
        row = next(r for r in b.qs(".task-row") if "Intégration" in r.text)
        row.click()
        b.wait("#time-body .time-total")
        b.click('#time-body [data-action="timer-start"]')
        b.wait("#timer-pill .timer-elapsed")
        self.assertIn("Intégration", b.text("#timer-pill"))
        time.sleep(2.2)
        self.assertRegex(b.text("#timer-pill .timer-elapsed"), r"^00:00:0[2-9]$")  # le compteur avance chaque seconde
        b.click('#time-body [data-action="timer-stop"]')
        b.w.until(lambda d: not b.q("#timer-pill").is_displayed())
        b.q('#time-form input[name="minutes"]').send_keys("30")
        b.q('#time-form input[name="note"]').send_keys("Intégration E2E")
        b.q("#time-form button").click()
        b.w.until(lambda d: "Intégration E2E" in b.text("#time-body"))
        task = next(t for t in api("GET", f"/projects/{self.project_id()}/tasks/", b.token()) if "Intégration" in t["title"])
        self.assertEqual(task["time_minutes"], 31)  # 1 minute de chrono (arrondi minimal) + 30 saisies
        b.click('#panel [data-action="close-panel"]')

    def test_42_timer_survives_a_page_reload(self):
        b = self.open_project()
        b.click('#toolbar [data-view="list"]')
        b.wait(".task-row")
        next(r for r in b.qs(".task-row") if "Collecte" in r.text).click()
        b.click('#time-body [data-action="timer-start"]')
        b.wait("#timer-pill .timer-elapsed")
        b.d.refresh()
        b.wait("#timer-pill .timer-elapsed")  # relu depuis le serveur : le chrono ne dépend pas de la page
        b.click('#timer-pill [data-action="timer-stop"]')
        b.w.until(lambda d: not b.q("#timer-pill").is_displayed())

    def test_43_create_a_project_from_a_template(self):
        b = self.br
        b.click('#sidebar [data-action="new-project"]')
        b.wait('#modal select[name="template"]')
        from selenium.webdriver.support.ui import Select
        b.w.until(lambda d: len(b.qs('#modal select[name="template"] option')) > 3)  # modèles chargés
        Select(b.q('#modal select[name="template"]')).select_by_value("builtin:sprint")
        self.assertEqual(b.q('#modal input[name="name"]').get_attribute("value"), "Sprint de 2 semaines")
        self.assertTrue(b.q("#start-label").is_displayed())
        b.q('#modal input[name="name"]').clear()
        b.q('#modal input[name="name"]').send_keys("Sprint E2E")
        b.q('#modal button[value="ok"]').click()
        b.w.until(lambda d: self.has_text("#sidebar .proj", "Sprint E2E"))
        projects = api("GET", "/projects/", b.token())
        pid = next(p["id"] for p in projects if p["name"] == "Sprint E2E")
        self.assertTrue(next(p for p in projects if p["id"] == pid)["skip_weekends"])
        tasks = api("GET", f"/projects/{pid}/tasks/", b.token())
        self.assertEqual(len(tasks), 6)
        self.assertTrue(all(__import__("datetime").date.fromisoformat(t["start_date"]).weekday() < 5 for t in tasks))  # jours ouvrés

    def test_44_completing_a_recurring_task_creates_the_next_one(self):
        b = self.open_project()
        pid = self.project_id()
        made = api("POST", f"/projects/{pid}/tasks/", b.token(), {"title": "Rapport hebdo E2E", "recurrence": "weekly", "start_date": "2026-10-05", "due_date": "2026-10-07"})
        b.d.refresh()
        b.wait("#sidebar .navitem")
        self.open_project()
        b.click('#toolbar [data-view="list"]')
        b.wait(".task-row")
        row = next(r for r in b.qs(".task-row") if "Rapport hebdo E2E" in r.text)
        b.q(".check", row).click()
        b.w.until(lambda d: len([t for t in api("GET", f"/projects/{pid}/tasks/", b.token()) if t["title"] == "Rapport hebdo E2E"]) == 2)
        tasks = [t for t in api("GET", f"/projects/{pid}/tasks/", b.token()) if t["title"] == "Rapport hebdo E2E"]
        nxt = next(t for t in tasks if t["status"] != "done")
        self.assertEqual((nxt["start_date"], nxt["due_date"], nxt["recurrence_of"]), ("2026-10-12", "2026-10-14", made["id"]))

    def test_45_working_days_setting_changes_how_dependents_move(self):
        b = self.br
        token = b.token()
        project = api("POST", "/projects/", token, {"name": "Jours ouvrés E2E"})
        pid = project["id"]
        a = api("POST", f"/projects/{pid}/tasks/", token, {"title": "A", "start_date": "2026-10-05", "due_date": "2026-10-07"})
        c = api("POST", f"/projects/{pid}/tasks/", token, {"title": "C", "start_date": "2026-10-08", "due_date": "2026-10-09", "dependencies": [a["id"]]})
        api("PATCH", f"/projects/{pid}/", token, {"skip_weekends": True})
        api("PATCH", f"/projects/{pid}/tasks/{a['id']}/", token, {"due_date": "2026-10-09"})
        moved = api("GET", f"/projects/{pid}/tasks/{c['id']}/", token)
        self.assertEqual((moved["start_date"], moved["due_date"]), ("2026-10-12", "2026-10-13"))  # lundi-mardi, pas le week-end
        b.d.refresh()
        b.wait("#sidebar .navitem")
        next(r for r in b.qs('#sidebar .proj[data-action="select-project"]') if "Jours ouvrés" in r.text).click()
        b.wait('#toolbar [data-view="dashboard"]')
        b.click('[data-action="edit-project"]')
        b.wait('#modal input[name="skip_weekends"]')
        self.assertTrue(b.q('#modal input[name="skip_weekends"]').is_selected())
        b.click('#modal button[value="cancel"]')

    # ------------------------------------------------------------------ thème, compte
    def test_30_dark_theme_toggle(self):
        b = self.br
        b.click('#sidebar [data-action="theme"]')
        self.assertEqual(b.d.execute_script("return document.documentElement.dataset.theme"), "dark")
        b.click('#sidebar [data-action="theme"]')
        self.assertEqual(b.d.execute_script("return document.documentElement.dataset.theme"), "light")

    def test_31_my_account_export_and_delete_a_fresh_account(self):
        b = Browser()
        try:
            b.click('[data-auth-tab="register"]')
            form = b.q("#register-form")
            form.find_element(By.NAME, "username").send_keys("jetable")
            form.find_element(By.NAME, "email").send_keys("jetable@example.com")
            form.find_element(By.NAME, "password").send_keys("Mot-de-passe-9x")
            form.find_element(By.CSS_SELECTOR, "button").click()
            b.wait("#sidebar .navitem")
            b.click('#sidebar [data-action="account"]')
            b.wait('#modal [data-account="delete"]')
            self.assertIn("jetable@example.com", b.text("#modal"))
            b.q('#modal input[name="password"]').send_keys("faux-mot-de-passe")
            b.q('#modal [data-account="delete"]').click()
            b.d.switch_to.alert.accept()
            b.w.until(lambda d: b.qs("#toast.show"))
            self.assertIn("incorrect", b.text("#toast").lower())  # mauvais mot de passe : rien n'est supprimé
            field = b.q('#modal input[name="password"]')
            field.clear()
            field.send_keys("Mot-de-passe-9x")
            b.q('#modal [data-account="delete"]').click()
            b.d.switch_to.alert.accept()
            b.wait("#login-form")  # retour à l'écran de connexion
            with self.assertRaises(Exception):
                api("POST", "/auth/token/", body={"username": "jetable", "password": "Mot-de-passe-9x"})
        finally:
            b.quit()

    def test_32_admin_overview(self):
        b = self.br
        b.click('#sidebar [data-action="go-admin"]')
        b.wait(".kpi")
        self.assertIn("Moteur de planification", b.text("#view"))
        self.assertNotIn("IA", b.text("#view"))

    def test_33_login_error_and_logout(self):
        b = Browser()
        try:
            b.wait("#login-form")
            form = b.q("#login-form")
            form.find_element(By.NAME, "username").send_keys("demo")
            form.find_element(By.NAME, "password").send_keys("mauvais")
            form.find_element(By.CSS_SELECTOR, "button").click()
            b.w.until(lambda d: b.qs("#toast.show"))
            self.assertTrue(b.q("#login-form").is_displayed())
        finally:
            b.quit()


if __name__ == "__main__":
    unittest.main(verbosity=2)

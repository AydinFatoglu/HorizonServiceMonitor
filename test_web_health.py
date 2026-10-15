import gc
import socket
import ssl
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch
from urllib.error import URLError

import HorizonServiceMonitor as h
import web_health as w


class ProbeHandler(BaseHTTPRequestHandler):
    paths = []

    def do_GET(self):
        self.paths.append(self.path)
        if self.path in ('/admin/redirect', '/admin/outside', '/admin/html'):
            self.send_response(302)
            target = {'/admin/redirect': '/admin/login', '/admin/outside': 'https://example.invalid/admin/', '/admin/html': '/portal/'}[self.path]
            self.send_header('Location', target)
        else:
            self.send_response(200 if self.path in ('/admin/', '/admin/login') else 503 if self.path == '/admin/unavailable' else 404)
        self.end_headers()

    def log_message(self, *args):
        pass


class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), ProbeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_get_200_and_non_200(self):
        for path, code in (('/admin/', 200), ('/admin/unavailable', 503), ('/admin/missing', 404)):
            with self.subTest(path=path):
                result = w.check_admin_web(self.base + path)
                self.assertEqual((result['kind'], result['code']), ('http', code))
                self.assertGreaterEqual(result['seconds'], 0)

    def test_local_admin_redirect_is_followed(self):
        result = w.check_admin_web(self.base + '/admin/redirect')
        self.assertEqual(result['code'], 200)
        self.assertTrue(result['url'].endswith('/admin/login'))

    def test_external_and_html_access_redirects_not_healthy(self):
        for path in ('/admin/outside', '/admin/html'):
            with self.subTest(path=path):
                result = w.check_admin_web(self.base + path)
                self.assertEqual(result['code'], 302)
                self.assertIn('Redirect outside', result['detail'])
        self.assertNotIn('/portal/', ProbeHandler.paths)

    def test_proxy_settings_do_not_route_loopback_through_proxy(self):
        with patch.dict('os.environ', {'HTTP_PROXY': 'http://127.0.0.1:1', 'http_proxy': 'http://127.0.0.1:1', 'NO_PROXY': '', 'no_proxy': ''}):
            self.assertEqual(w.check_admin_web(self.base + '/admin/')['code'], 200)

    def test_refused_connection(self):
        opener = Mock()
        opener.open.side_effect = URLError(ConnectionRefusedError('Connection refused'))
        with patch.object(w, 'build_opener', return_value=opener):
            result = w.check_admin_web()
        self.assertEqual(result['kind'], 'connection_error')
        self.assertIsNone(result['code'])

    def test_timeout_and_loopback_https_context(self):
        opener = Mock()
        opener.open.side_effect = URLError(socket.timeout('timed out'))
        with patch.object(w, 'build_opener', return_value=opener) as build:
            result = w.check_admin_web()
            self.assertEqual(result['kind'], 'timeout')
            args, kwargs = opener.open.call_args
            self.assertEqual(args[0].full_url, 'https://127.0.0.1/admin/')
            self.assertEqual(args[0].method, 'GET')
            self.assertEqual(kwargs['timeout'], 10)
            https_handler = next(item for item in build.call_args.args if isinstance(item, w.HTTPSHandler))
            self.assertFalse(https_handler._context.check_hostname)
            self.assertEqual(https_handler._context.verify_mode, ssl.CERT_NONE)

    def test_other_hosts_and_paths_rejected_before_network(self):
        with patch.object(w, 'build_opener') as build:
            for url in ('https://example.com/admin/', 'https://localhost/admin/', 'https://127.0.0.1/portal/', 'https://user:pass@127.0.0.1/admin/'):
                self.assertEqual(w.check_admin_web(url)['kind'], 'connection_error')
            build.assert_not_called()


class WebGuiTests(unittest.TestCase):
    def setUp(self):
        self.root = h.tk.Tk()
        self.root.withdraw()
        self.monitor = None
        self.panel = None

    def tearDown(self):
        if self.panel is not None:
            self.panel.close()
        if self.monitor is not None and not self.monitor.closed:
            self.monitor.stop_dispatch()
            if self.monitor.after_id is not None:
                self.root.after_cancel(self.monitor.after_id)
        self.root.destroy()
        gc.collect()

    def pump(self, predicate):
        deadline = time.monotonic() + 4
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertTrue(predicate())

    def test_probe_does_not_block_gui_or_service_refresh_and_translates(self):
        gate = threading.Event()
        def slow_probe():
            gate.wait(3)
            return {'kind': 'http', 'code': 200, 'seconds': .01, 'detail': ''}
        with patch.object(h, 'check_admin_web', side_effect=slow_probe) as probe, patch.object(h, 'run_ps', return_value=[]):
            monitor = h.Monitor(self.root)
            panel = monitor.web_health
            self.monitor, self.panel = monitor, panel
            self.pump(lambda: not monitor.busy)
            self.assertTrue(panel.busy)
            self.assertIsNotNone(monitor.after_id)
            self.assertEqual(h.REFRESH_MS, 30_000)
            panel.refresh()
            self.assertEqual(probe.call_count, 1)
            monitor.language.set('en')
            self.assertEqual(panel.info.get(), 'Checking the admin console...')
            gate.set()
            self.pump(lambda: not panel.busy)
            self.assertIn('reachable — HTTP 200', panel.info.get())
            self.assertEqual(str(panel.status_label['foreground']), '#16803d')
            scheduled = panel.after_id
            self.assertEqual(w.WEB_REFRESH_MS, 45_000)
            after_script = self.root.tk.call('after', 'info', scheduled)[0]
            self.assertTrue(after_script)
            monitor.language.set('tr')
            self.assertIn('erişilebilir — HTTP 200', panel.info.get())
            self.assertEqual(panel.after_id, scheduled)
            self.assertEqual(probe.call_count, 1)
            monitor.stop_dispatch()
            self.root.after_cancel(monitor.after_id)

    def test_status_messages_failure_recovery_and_cleanup(self):
        with patch.object(h, 'check_admin_web', return_value={'kind': 'http', 'code': 503, 'seconds': 0, 'detail': ''}):
            panel = h.WebHealthPanel(self.root, self.root)
            self.panel = panel
            self.pump(lambda: not panel.busy)
            for kind, code, expected in (('http', 503, 'HTTP 503'), ('http', 401, 'HTTP 401'), ('timeout', None, 'zaman aşımına'), ('connection_error', None, 'bağlanılamadı'), ('http', 200, 'erişilebilir — HTTP 200')):
                # Cancel the previous scheduled check, as refresh does in use.
                panel.frame.after_cancel(panel.after_id)
                panel.render({'kind': kind, 'code': code, 'seconds': .1, 'detail': ''})
                self.assertIn(expected, panel.info.get())
            panel.close()
            panel.safe_after(lambda: self.fail('Closed panel updated'))
            self.assertTrue(panel.closed)


if __name__ == '__main__':
    unittest.main(verbosity=2)

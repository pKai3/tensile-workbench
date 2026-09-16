from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
import unittest
from unittest.mock import Mock, patch
import webbrowser

from workbench_server import WorkbenchVoila


class BrowserLaunchTests(unittest.TestCase):
    def app(self, token='synthetic-test-token', generated=True, **kwargs):
        app = WorkbenchVoila(ip='127.0.0.1', port=8919, **kwargs)
        app.identity_provider = SimpleNamespace(token=token, token_generated=generated)
        return app

    def test_generated_token_is_in_automatic_browser_url(self):
        app = self.app()
        self.assertEqual(app.browser_url(), 'http://127.0.0.1:8919/?token=synthetic-test-token')

    def test_configured_token_is_not_replaced_with_redacted_display_token(self):
        app = self.app('synthetic +/?&%#', generated=False)
        self.assertIn('token=...', app.display_url)
        self.assertEqual(parse_qs(urlsplit(app.browser_url()).query),
                         {'token': ['synthetic +/?&%#']})

    def test_actual_port_and_base_path_are_used_once(self):
        app = self.app(base_url='/workbench/')
        app.port = 8921  # Represents Voilà selecting another available port.
        self.assertEqual(app.browser_url(), 'http://127.0.0.1:8921/workbench/?token=synthetic-test-token')

    def test_wrapper_does_not_create_or_change_tokens(self):
        app = self.app(token='')
        self.assertEqual(app.browser_url(), 'http://127.0.0.1:8919/')
        self.assertEqual(app.identity_provider.token, '')

    def test_browser_receives_token_and_runs_in_background(self):
        app = self.app(browser='test-browser', webbrowser_open_new=1)
        browser = Mock()
        with patch('workbench_server.webbrowser.get', return_value=browser) as get, \
             patch('workbench_server.threading.Thread') as thread:
            app.launch_browser()
        get.assert_called_once_with('test-browser')
        self.assertTrue(thread.call_args.kwargs['daemon'])
        thread.return_value.start.assert_called_once_with()
        thread.call_args.kwargs['target']()
        browser.open.assert_called_once_with(app.browser_url(), new=1)

    def test_unavailable_browser_gives_fallback_without_aborting_server(self):
        app = self.app()
        with patch('workbench_server.webbrowser.get', side_effect=webbrowser.Error('unavailable')), \
             patch.object(app.log, 'warning') as warning, \
             patch('workbench_server.threading.Thread') as thread:
            app.launch_browser()
        self.assertIn('URL printed', warning.call_args.args[0])
        thread.assert_not_called()

    def test_browser_failure_does_not_log_token(self):
        app = self.app()
        browser = Mock()
        browser.open.side_effect = RuntimeError(app.browser_url())
        with patch('workbench_server.webbrowser.get', return_value=browser), \
             patch('workbench_server.threading.Thread') as thread, \
             patch.object(app.log, 'warning') as warning:
            app.launch_browser()
            thread.call_args.kwargs['target']()
        self.assertIn('URL printed', warning.call_args.args[0])
        self.assertNotIn('synthetic-test-token', str(warning.call_args))


if __name__ == '__main__':
    unittest.main()

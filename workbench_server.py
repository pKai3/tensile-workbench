"""Local Voilà server with an authenticated automatic browser link.

Voilà 0.5's browser redirect uses connection_url, which omits the login token.
Keep its normal authentication and port selection; correct only browser opening.
"""
import threading
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import webbrowser

from voila.app import Voila


class WorkbenchVoila(Voila):
    def browser_url(self):
        # Called after listen() selects an available port. display_url is unsuitable:
        # Voilà deliberately redacts explicitly configured tokens there as "...".
        parts = urlsplit(self.connection_url)
        query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                 if key != 'token']
        token = self.identity_provider.token
        if token:
            query.append(('token', token))
        return urlunsplit(parts._replace(query=urlencode(query)))

    def launch_browser(self):
        # The parent honours --no-browser before calling this method.
        try:
            browser = webbrowser.get(self.browser or None)
        except webbrowser.Error:
            self.log.warning('No browser found. Open the URL printed by the launcher.')
            return
        url = self.browser_url()

        def open_page():
            try:
                opened = browser.open(url, new=self.webbrowser_open_new)
            except Exception:
                # Browser errors can contain the URL. Do not log token-bearing errors.
                opened = False
            if not opened:
                self.log.warning('Could not open the browser. Open the URL printed by the launcher.')

        threading.Thread(target=open_page, name='workbench-browser', daemon=True).start()


if __name__ == '__main__':
    WorkbenchVoila.launch_instance()

"""Compact help: hover for a tooltip, click or press Enter to keep it open."""
from html import escape
from html.parser import HTMLParser


def help_html(label, body):
    """Body is trusted application markup; escape user values before passing it."""
    class Text(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    parser = Text()
    parser.feed(body)
    tooltip = ' '.join(' '.join(parser.parts).split())
    return ('<details class="tw-help"><summary title="' + escape(tooltip, quote=True)
            + '" aria-label="Help: ' + escape(label, quote=True) + '">ⓘ ' + escape(label)
            + '</summary><div class="tw-help-content">' + body + '</div></details>')

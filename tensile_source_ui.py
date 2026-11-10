"""Project-source editor and folder browser adapted from TEM's workflow."""
from copy import deepcopy
from html import escape
from pathlib import Path

from tensile_popup import SettingsPopup
from tensile_sources import browse, new_source


class SourceEditor:
    def __init__(self, w, root, sources, primary_field, output_field):
        self.w, self.root, self.primary_field = w, root, primary_field
        self.rows = []
        self.list = w.VBox(layout=w.Layout(width='100%'))
        self.popup = SettingsPopup(w, width='800px')
        self.add = w.Button(description='Add project', icon='plus', layout=w.Layout(width='auto', align_self='flex-start'),
            tooltip='Add an independent source folder. Its groups can be combined with other projects in any analysis.')
        self.add.on_click(lambda _: self._add(new_source()))
        self.ui = w.VBox([w.HTML('<b>Projects</b>'), self.list, self.add,
            w.HTML('<b>Main output folder</b>'), self._path(output_field), self.popup.ui])
        output_field.description = ''
        self.load(sources)

    def load(self, sources):
        for row in self.rows:
            for field in row['fields'].values():
                if field is not self.primary_field:
                    field.close()
            row['ui'].close()
        self.rows = []
        for source in sources:
            self._add(source)

    def _path(self, field):
        field.layout.width = '100%'
        field.layout.min_width = '120px'
        field.layout.flex = '1 1 auto'
        button = self.w.Button(icon='folder-open', description='Browse',
            layout=self.w.Layout(width='96px', min_width='96px', flex='0 0 auto'),
            tooltip='Choose a folder on this computer.')
        button.on_click(lambda _: self.choose(field))
        return self.w.HBox([field, button], layout=self.w.Layout(width='100%', align_items='center'))

    def _add(self, source):
        w = self.w
        source = deepcopy(source)
        name = w.Text(value=source['name'], placeholder='Project name', continuous_update=False)
        path = self.primary_field if source.get('legacy') else w.Text(value=source['path'], continuous_update=False)
        path.description = ''
        path.value = source['path']
        output = w.Text(value=source.get('output', ''), placeholder='Use main output folder', continuous_update=False)
        remove = w.Button(description='Remove', icon='times', layout=w.Layout(width='auto'),
            tooltip='Stop watching this project. Source files and saved analyses/overrides are kept.')
        name.tooltip = 'Project label. Renaming an added project prompts review before its saved settings are transferred.'
        path.tooltip = 'Source folder. Relink this path if the project has moved; files are never copied or modified.'
        output.tooltip = 'Optional output for analyses using only this project. Analyses spanning projects use the main output.'
        status = w.HTML()
        fields = dict(name=name, path=path, output=output)
        row = dict(source=source, fields=fields, status=status)
        paths = w.HBox([
            w.VBox([w.HTML('<small>Source folder</small>'), self._path(path)],
                   layout=w.Layout(flex='1 1 360px', min_width='0')),
            w.VBox([w.HTML('<small>Project output (optional)</small>'), self._path(output)],
                   layout=w.Layout(flex='1 1 360px', min_width='0'))],
            layout=w.Layout(width='100%', flex_flow='row wrap', grid_gap='12px'))
        row['ui'] = w.VBox([w.HBox([name, remove], layout=w.Layout(justify_content='space-between')), paths, status],
            layout=w.Layout(border='1px solid var(--tw-border,#ccd4de)', padding='12px', margin='4px 0'))
        def refresh(_=None):
            from tensile_startup import resolve_folder
            try:
                exists = resolve_folder(path.value, self.root).is_dir()
                status.value = ('<small>Available</small>' if exists else
                    '<small>Unavailable · saved work is retained. Choose the folder when it is available.</small>')
            except ValueError:
                status.value = '<small>Choose a source folder.</small>'
        path.observe(refresh, names='value')
        refresh()
        remove.on_click(lambda _: self._remove(row))
        self.rows.append(row)
        self._draw()

    def _remove(self, row):
        self.rows.remove(row)
        self._draw()

    def _draw(self):
        self.list.children = tuple(row['ui'] for row in self.rows)

    def values(self):
        return [{**row['source'], **{key: field.value.strip() for key, field in row['fields'].items()}}
                for row in self.rows]

    def choose(self, target):
        w = self.w
        location = w.Text(value=target.value or str(Path.home()), continuous_update=False,
                          layout=w.Layout(width='100%'), placeholder='Folder path')
        items = w.Select(options=[], rows=12, layout=w.Layout(width='100%'))
        message = w.HTML()
        up = w.Button(description='Up', icon='arrow-up')
        home = w.Button(description='Home', icon='home')
        go = w.Button(description='Go', icon='arrow-right')
        enter = w.Button(description='Open folder', icon='folder-open')
        use = w.Button(description='Use this folder', icon='check', button_style='primary')
        cancel = w.Button(description='Cancel', icon='times')
        current = [None]
        def load(value):
            try:
                path, children = browse(value, self.root)
                current[0] = path
                location.value = str(path)
                items.options = children
                message.value = '<small>' + escape(str(path)) + '</small>'
                use.disabled = False
            except (OSError, ValueError) as error:
                current[0] = None
                use.disabled = True
                message.value = escape(str(error))
        go.on_click(lambda _: load(location.value))
        enter.on_click(lambda _: load(items.value) if items.value else None)
        up.on_click(lambda _: load((current[0] or Path(location.value)).parent))
        home.on_click(lambda _: load(Path.home()))
        def selected(_):
            if current[0] is not None:
                target.value = str(current[0])
                self.popup.close()
        use.on_click(selected)
        cancel.on_click(lambda _: self.popup.close())
        self.popup.open('Choose folder', [w.HBox([up, home]), w.HBox([location, go]),
            items, enter, message, w.HBox([use, cancel])])
        load(location.value)

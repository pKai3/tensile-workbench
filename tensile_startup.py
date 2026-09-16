"""First-run folder selection, kept separate from shared graph definitions."""
from html import escape
import json
import os
from pathlib import Path
import tempfile

SETTINGS_NAME = '.tensile-paths.json'
DEFAULT_FOLDERS = {'data_directory': './data', 'output_directory': './output'}
DEFAULT_SAMPLE_DATA = {'sample_data_directory': './examples/data', 'show_sample_data': True}


def local_settings(root):
    path = Path(root) / SETTINGS_NAME
    if not path.exists():
        return {}
    document = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(document, dict) or document.get('schema_version') != 1:
        raise ValueError('Unrecognised folder-settings version.')
    return document


def sample_data_settings(root):
    try:
        settings = {**DEFAULT_SAMPLE_DATA, **local_settings(root)}
    except (ValueError, TypeError):
        # Explicit folder confirmation must still be able to repair this file.
        settings = dict(DEFAULT_SAMPLE_DATA)
    if not isinstance(settings['show_sample_data'], bool):
        settings['show_sample_data'] = DEFAULT_SAMPLE_DATA['show_sample_data']
    if not isinstance(settings['sample_data_directory'], str) or not settings['sample_data_directory'].strip():
        settings['sample_data_directory'] = DEFAULT_SAMPLE_DATA['sample_data_directory']
    return {key: settings[key] for key in DEFAULT_SAMPLE_DATA}


def resolve_folder(value, root):
    text = str(value).strip()
    if not text:
        raise ValueError('Enter both a data folder and an output folder.')
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        text = text[1:-1]
    path = Path(os.path.expandvars(text)).expanduser()
    return (path if path.is_absolute() else Path(root) / path).resolve()


def validate_folders(values, root, create=False):
    paths = {key: resolve_folder(values[key], root) for key in DEFAULT_FOLDERS}
    if paths['data_directory'] == paths['output_directory']:
        raise ValueError('Choose separate data and output folders.')
    for label, path in paths.items():
        if path.exists() and not path.is_dir():
            raise ValueError(f'{label.replace("_", " ").capitalize()} is a file, not a folder: {path}')
        parent = path
        while not parent.exists():
            parent = parent.parent
        if not parent.is_dir():
            raise ValueError(f'A parent path is not a folder: {parent}')
        if not create and not path.is_dir():
            raise FileNotFoundError(f'Folder is unavailable. Choose another location or save to create it: {path}')
    if create:
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
    if not os.access(paths['data_directory'], os.R_OK | os.X_OK):
        raise PermissionError('The data folder is not readable.')
    if not os.access(paths['output_directory'], os.W_OK | os.X_OK):
        raise PermissionError('The output folder is not writable.')
    return paths


def save_folders(root, values):
    # Preserve the hidden sample source and its visibility when changing folders.
    try:
        existing = local_settings(root)
    except (ValueError, TypeError):
        existing = {}  # Explicit folder confirmation can repair invalid settings.
    content = {**DEFAULT_SAMPLE_DATA, **existing, 'schema_version': 1,
               **{key: str(values[key]).strip() for key in DEFAULT_FOLDERS}}
    _save_local_settings(root, content)


def save_sample_data_visibility(root, visible):
    """Update only the sample preference; never replace chosen folder paths."""
    content = {**DEFAULT_FOLDERS, **DEFAULT_SAMPLE_DATA, **local_settings(root),
               'schema_version': 1, 'show_sample_data': bool(visible)}
    _save_local_settings(root, content)


def _save_local_settings(root, content):
    root = Path(root)
    handle, temporary = tempfile.mkstemp(prefix='.tensile-paths-', suffix='.tmp', dir=root)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(content, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / SETTINGS_NAME)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


class WorkbenchLauncher:
    """Ask before reading data on first run; keep folder settings editable later."""

    def __init__(self, project_dir=None, factory=None):
        import ipywidgets as w
        self.root = Path(project_dir or Path(__file__).parent).expanduser().resolve()
        self.factory = factory
        self.app = None
        self.w = w
        values = dict(DEFAULT_FOLDERS)
        saved, problem = False, None
        settings = self.root / SETTINGS_NAME
        if settings.exists():
            try:
                document = json.loads(settings.read_text(encoding='utf-8'))
                if document.get('schema_version') != 1:
                    raise ValueError('Unrecognised folder-settings version.')
                for key in DEFAULT_FOLDERS:
                    if not isinstance(document.get(key), str) or not document[key].strip():
                        raise ValueError('Saved folder settings are incomplete.')
                    values[key] = document[key]
                saved = True
            except Exception as error:
                problem = f'Could not read saved folders: {error}'
        self.fields = {
            key: w.Text(value=values[key], description=label, continuous_update=False,
                        style={'description_width': '110px'}, layout=w.Layout(width='98%'))
            for key, label in (('data_directory', 'Data folder:'), ('output_directory', 'Output folder:'))
        }
        self.save_button = w.Button(description='Save folders and open', button_style='primary',
                                    layout=w.Layout(width='190px'))
        self.defaults_button = w.Button(description='Use ./data and ./output', layout=w.Layout(width='210px'))
        self.message = w.HTML()
        self.locations = w.HTML()
        self.body = w.VBox()
        content = w.VBox([
            w.HTML('<p>Choose where to read tensile data and save results. Paste folder paths below. '
                   'Absolute paths can be anywhere you can access. Relative paths start from '
                   '<code>' + escape(str(self.root)) + '</code>, not the terminal\'s current folder. '
                   'Saving creates missing folders; it never moves or copies data files.</p>'),
            *self.fields.values(),
            w.HBox([self.save_button, self.defaults_button], layout=w.Layout(flex_flow='row wrap')),
            w.HTML('<small>Bundled sample data is available separately. Use Show sample data '
                   'beside the sample-group selector; your data-folder path stays unchanged.</small>'),
            self.locations, self.message,
        ])
        self.folders = w.Accordion(children=[content], selected_index=0)
        self.folders.set_title(0, 'Folders · first-run setup' if not saved else 'Folders · data and output locations')
        self.ui = w.VBox([self.folders, self.body], layout=w.Layout(width='100%'))
        self.save_button.on_click(self._save)
        self.defaults_button.on_click(self._defaults)
        for field in self.fields.values():
            field.observe(self._preview, names='value')
        self._preview()
        if problem:
            self.message.value = '<b>' + escape(problem) + '</b> Choose folders and save to continue.'
        elif saved:
            try:
                paths = validate_folders(values, self.root)
                self._open(paths)
                self.folders.selected_index = None
            except Exception as error:
                self.message.value = '<b>Folder setup needed:</b> ' + escape(str(error))
        else:
            self.message.value = 'First run: confirm both folders to open the workbench. No data has been loaded yet.'

    def _values(self):
        return {key: field.value for key, field in self.fields.items()}

    def _preview(self, _=None):
        try:
            paths = {key: resolve_folder(field.value, self.root) for key, field in self.fields.items()}
            self.locations.value = '<small>Resolved data: <code>' + escape(str(paths['data_directory'])) + \
                '</code><br>Resolved output: <code>' + escape(str(paths['output_directory'])) + '</code></small>'
        except Exception as error:
            self.locations.value = '<small>' + escape(str(error)) + '</small>'

    def _defaults(self, _=None):
        for key, value in DEFAULT_FOLDERS.items():
            self.fields[key].value = value
        self.message.value = 'Defaults selected. Save folders to apply them.'

    def _open(self, paths, save_values=None):
        factory = self.factory
        if factory is None:
            from tensile_workbench import TensileWorkbench
            factory = TensileWorkbench
        candidate = factory(self.root, data_dir=paths['data_directory'], output_dir=paths['output_directory'])
        try:
            if save_values is not None:
                save_folders(self.root, save_values)
        except Exception:
            candidate.ui.close()
            raise
        previous = self.app
        self.app = candidate
        self.body.children = (candidate.ui,)
        if previous is not None:
            previous.ui.close()

    def _save(self, _=None):
        self.save_button.disabled = True
        try:
            if self.app is not None and not self.app.save_current():
                raise RuntimeError('Resolve the graph-save warning before changing folders.')
            values = self._values()
            paths = validate_folders(values, self.root, create=True)
            self._open(paths, save_values=values)
            self.folders.set_title(0, 'Folders · data and output locations')
            self.folders.selected_index = None
            self.message.value = 'Folders saved for this installation. Expand Folders to change them at any time.'
        except Exception as error:
            self.message.value = '<b>Could not apply folders:</b> ' + escape(str(error))
        finally:
            self.save_button.disabled = False

    def show(self):
        from IPython.display import display
        display(self.ui)
        return self


def launch(project_dir=None):
    return WorkbenchLauncher(project_dir)

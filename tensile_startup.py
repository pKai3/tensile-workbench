"""First-run folder selection, kept separate from shared analysis definitions."""
from html import escape
import json
import os
from pathlib import Path
from tensile_activity import BusyOverlay, busy
from tensile_page_layout import ContentWidth
from tensile_backup_ui import BackupPanel
from workbench_backups import (BackupVault, PROJECT_NAME, RecoveryRequired, atomic_bytes,
                               backup_warning, read_optional, recovery_problem, settings_lock, validate_paths)

SETTINGS_NAME = '.tensile-paths.json'
DEFAULT_FOLDERS = {'data_directory': './data', 'output_directory': './output'}
DEFAULT_SAMPLE_DATA = {'sample_data_directory': './examples/data', 'show_sample_data': True}


def local_settings(root):
    path = Path(root) / SETTINGS_NAME
    if not path.exists():
        if BackupVault(path).has_history():
            raise RecoveryRequired('Folder preferences are missing, but saved history exists. Use Backups & restore.')
        return {}
    return validate_paths(path.read_bytes())


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
    # Explicit confirmation may repair invalid preferences, after preserving them.
    changes = {key: str(values[key]).strip() for key in DEFAULT_FOLDERS}
    if 'sources' in values:
        changes['sources'] = values['sources']
    return _save_local_settings(root, changes, repair=True)


def save_sample_data_visibility(root, visible):
    """Update only the sample preference; never replace chosen folder paths."""
    return _save_local_settings(root, {'show_sample_data': bool(visible)})


def _save_local_settings(root, changes, *, repair=False):
    root = Path(root)
    path = root / SETTINGS_NAME
    vault = BackupVault(path)
    with settings_lock(path):
        raw = read_optional(path)
        try:
            existing = local_settings(root)
        except (ValueError, TypeError):
            if not repair:
                raise
            vault.capture(raw, reason='pre-restore', force=True)
            existing = {}
        content = {**DEFAULT_FOLDERS, **DEFAULT_SAMPLE_DATA, **existing, **changes, 'schema_version': 1}
        encoded = (json.dumps(content, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
        validate_paths(encoded)
        if raw and 'sources' in changes and existing.get('sources') != changes['sources']:
            vault.capture(raw, reason='pre-migration', force=True)
        vault.try_capture(raw)
        if raw != encoded:
            atomic_bytes(path, encoded)
        return vault.try_capture(encoded)


class WorkbenchLauncher:
    """Ask before reading data on first run; keep folder settings editable later."""

    def __init__(self, project_dir=None, factory=None):
        import ipywidgets as w
        self.root = Path(project_dir or Path(__file__).parent).expanduser().resolve()
        self.factory = factory
        self.activity = BusyOverlay()
        self.app = None
        self.w = w
        values = dict(DEFAULT_FOLDERS)
        saved, problem = False, None
        settings = self.root / SETTINGS_NAME
        if settings.exists():
            try:
                document = validate_paths(settings.read_bytes())
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
        self.save_button.icon, self.save_button.tooltip = 'folder-open', 'Save these folder paths and open the workbench. Missing folders are created; existing data is not moved.'
        self.defaults_button.icon, self.defaults_button.tooltip = 'undo', 'Fill in the data and output folders inside this installation. Save folders and open to apply.'
        for button in (self.save_button, self.defaults_button):
            button.layout.width = 'auto'
        self.fields['data_directory'].tooltip = 'Folder containing sample groups. Nested folders are supported.'
        self.fields['output_directory'].tooltip = 'Destination for exported plots and Excel files.'
        self.message = w.HTML()
        self.locations = w.HTML(layout=w.Layout(display='none'))
        self.body = w.VBox()
        self.backups = BackupPanel(self.root, before_backup=self._before_backup, after_restore=self._after_restore)
        from tensile_sources import default_source
        from tensile_source_ui import SourceEditor
        configured_sources = document.get('sources') if saved else None
        self.sources = SourceEditor(w, self.root, configured_sources or [default_source(values['data_directory'])],
                                    self.fields['data_directory'], self.fields['output_directory'])
        content = w.VBox([
            self.sources.ui,
            w.HBox([self.save_button, self.defaults_button], layout=w.Layout(flex_flow='row wrap')),
            self.locations, self.message,
        ])
        self.folders = w.Accordion(children=[content], selected_index=0)
        self.folders.set_title(0, 'Projects · first-run setup' if not saved else 'Projects · source and output folders')
        self.ui = w.VBox([self.activity, ContentWidth(), self.folders, self.backups.ui, self.body], layout=w.Layout(
            width='var(--tw-content-width, 1600px)', max_width='100%', min_width='0'))
        self.ui.add_class('tw-launcher')
        self.save_button.on_click(self._save)
        self.defaults_button.on_click(self._defaults)
        for field in self.fields.values():
            field.observe(self._preview, names='value')
        self._preview()
        recovery = recovery_problem(settings)
        project_recovery = recovery_problem(self.root / PROJECT_NAME)
        if problem:
            self.message.value = '<b>' + escape(problem) + '</b> Restore a backup, or explicitly choose and save folders again.'
        if recovery or project_recovery:
            if saved and not recovery:
                self.folders.selected_index = None
            self.backups.show_recovery(recovery or project_recovery, SETTINGS_NAME if recovery else PROJECT_NAME)
        elif problem:
            pass
        elif saved:
            try:
                paths = self._paths(values, configured_sources)
                self._open(paths)
                self.folders.selected_index = None
            except Exception as error:
                self.message.value = '<b>Folder setup needed:</b> ' + escape(str(error))
        else:
            self.message.value = 'First run: confirm both folders to open the workbench. No data has been loaded yet.'

    def _before_backup(self):
        return self.app is None or self.app.save_current()

    @busy('Reopening restored settings…')
    def _after_restore(self, _path):
        # Never flush the old widgets back over a deliberately restored file.
        if self.app is not None:
            self.app._paused = True
            self._close_app(self.app)
        self.app = None
        self.body.children = ()
        for name in (PROJECT_NAME, SETTINGS_NAME):
            problem = recovery_problem(self.root / name)
            if problem:
                self.backups.show_recovery(problem, name)
                return
        values = {**DEFAULT_FOLDERS, **local_settings(self.root)}
        for key in self.fields:
            self.fields[key].value = values[key]
        from tensile_sources import default_source
        self.sources.load(values.get('sources') or [default_source(values['data_directory'])])
        if not (self.root / SETTINGS_NAME).exists():
            self.folders.selected_index = 0
            self.message.value = 'Project restored. Confirm the data and output folders to continue.'
            return
        try:
            paths = self._paths(values, values.get('sources'))
        except Exception as error:
            self.folders.selected_index = 0
            self.message.value = '<b>Settings restored. Confirm folders to continue:</b> ' + escape(str(error))
            return
        self._open(paths)
        self.folders.selected_index = None
        self.message.value = 'Reopened from restored settings.'

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
        from tensile_sources import default_source
        self.sources.load([default_source(DEFAULT_FOLDERS['data_directory'])])
        for key, value in DEFAULT_FOLDERS.items():
            self.fields[key].value = value
        self.message.value = 'Defaults selected. Save folders to apply them.'

    def _paths(self, values, sources=None, *, create=False):
        if not sources:
            return validate_folders(values, self.root, create=create)
        from tensile_sources import resolve_sources
        resolved = resolve_sources(sources, self.root, output=values['output_directory'], create=create)
        return dict(data_directory=Path(resolved[0]['path']),
                    output_directory=resolve_folder(values['output_directory'], self.root), sources=resolved)

    @staticmethod
    def _close_app(app):
        if hasattr(app, 'close'):
            app.close()
        else:
            app.ui.close()

    @busy('Opening Tensile Workbench…')
    def _open(self, paths, save_values=None):
        problem = recovery_problem(self.root / PROJECT_NAME)
        if problem:
            self.backups.show_recovery(problem)
            raise RecoveryRequired(problem)
        factory = self.factory
        kwargs = {}
        if factory is None:
            from tensile_workbench import TensileWorkbench
            factory = TensileWorkbench
            kwargs['activity'] = self.activity
            kwargs['sources'] = paths.get('sources')
        try:
            candidate = factory(self.root, data_dir=paths['data_directory'], output_dir=paths['output_directory'], **kwargs)
        except RecoveryRequired as error:
            self.backups.show_recovery(str(error))
            raise
        try:
            if save_values is not None:
                save_folders(self.root, save_values)
            else:
                BackupVault(self.root / SETTINGS_NAME).try_capture(read_optional(self.root / SETTINGS_NAME), reason='opened')
        except Exception:
            self._close_app(candidate)
            raise
        previous = self.app
        self.app = candidate
        self.body.children = (candidate.ui,)
        if previous is not None:
            self._close_app(previous)
        warnings = [(name, backup_warning(self.root / name)) for name in (PROJECT_NAME, SETTINGS_NAME)]
        warnings = [(name, warning) for name, warning in warnings if warning]
        if warnings:
            self.backups.show_recovery(' · '.join(f'{name}: {warning}' for name, warning in warnings),
                                       warnings[0][0], heading='Backup warning · settings are saved')

    @busy('Applying folders and loading data…')
    def _save(self, _=None):
        self.save_button.disabled = True
        try:
            if self.app is not None and not self.app.save_current():
                raise RuntimeError('Resolve the analysis-save warning before changing folders.')
            values = self._values()
            sources = self.sources.values()
            from tensile_sources import validate_sources
            validate_sources(sources)
            # Preserve first-run creation for the original ./data workflow.
            if len(sources) == 1 and sources[0].get('legacy'):
                validate_folders(values, self.root, create=True)
            paths = self._paths(values, sources, create=True)
            values.update(sources=sources, data_directory=sources[0]['path'])
            self._open(paths, save_values=values)
            self.folders.set_title(0, 'Projects · source and output folders')
            self.folders.selected_index = None
            self.message.value = 'Projects saved. Source files have not been moved or changed.'
            if backup_warning(self.root / SETTINGS_NAME):
                self.message.value += '<br><b>' + escape(backup_warning(self.root / SETTINGS_NAME)) + '</b>'
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

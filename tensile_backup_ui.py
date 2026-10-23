"""Settings-only backup/recovery controls; never load or overwrite research data."""
from datetime import datetime
from html import escape
from pathlib import Path

import ipywidgets as w

from workbench_backups import (BackupVault, PROJECT_NAME, PATHS_NAME, backup_warning,
                               digest, read_optional, validate_settings)


class BackupPanel:
    def __init__(self, root, *, before_backup=None, after_restore=None):
        self.root = Path(root).resolve()
        self.before_backup = before_backup
        self.after_restore = after_restore
        self.pending = None
        self.file = w.Dropdown(options=[('Project · graphs, variables and specimen overrides', PROJECT_NAME),
                                        ('Folders · data/output locations and sample visibility', PATHS_NAME)],
                               layout=w.Layout(width='560px', max_width='100%'))
        self.snapshots = w.Select(rows=7, layout=w.Layout(width='780px', max_width='100%'))
        self.backup_now = w.Button(description='Back up now', layout=w.Layout(width='140px'))
        self.refresh_button = w.Button(description='Refresh list', layout=w.Layout(width='130px'))
        self.restore_button = w.Button(description='Restore selected…', layout=w.Layout(width='170px'), disabled=True)
        self.confirm_button = w.Button(description='Confirm restore', button_style='danger', layout=w.Layout(width='150px'))
        self.cancel_button = w.Button(description='Cancel', layout=w.Layout(width='100px'))
        self.confirm_message = w.HTML()
        self.confirmation = w.VBox([self.confirm_message, w.HBox([self.confirm_button, self.cancel_button])],
                                   layout=w.Layout(display='none'))
        self.message = w.HTML()
        self.location = w.HTML()
        self.content = w.VBox([
            w.HTML('<p>Automatic history covers settings only—not data or exported plots. '
                   'Keeps the 20 latest changed versions and 30 daily checkpoints. '
                   'Manual, pre-migration and pre-restore copies are kept until you remove them yourself. '
                   'Back up now saves both settings files; Restore changes only the selected file. '
                   'Unsaved editor drafts are not backed up.</p>'),
            self.file, self.snapshots,
            w.HBox([self.backup_now, self.refresh_button, self.restore_button], layout=w.Layout(flex_flow='row wrap')),
            self.confirmation, self.message, self.location,
        ])
        self.ui = w.Accordion(children=[self.content], selected_index=None,
                              layout=w.Layout(width='100%', min_width='0'))
        self.ui.set_title(0, 'Backups & restore')
        self.file.observe(self.refresh, names='value')
        self.snapshots.observe(self._selected, names='value')
        self.ui.observe(self._expanded, names='selected_index')
        self.refresh_button.on_click(self.refresh)
        self.backup_now.on_click(self._backup)
        self.restore_button.on_click(self._ask_restore)
        self.confirm_button.on_click(self._confirm)
        self.cancel_button.on_click(self._cancel)
        self._entries = {}

    def _vault(self):
        return BackupVault(self.root / self.file.value)

    def _expanded(self, change):
        if change['new'] == 0:
            self.refresh()

    def refresh(self, _=None):
        self._cancel()
        vault = self._vault()
        options, damaged = [], 0
        self._entries = {}
        try:
            for entry in vault.entries():
                if not entry['valid']:
                    damaged += 1
                    continue
                when = datetime.fromisoformat(entry['created']).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
                count = f' · {entry["graphs"]} graphs' if entry['graphs'] is not None else ''
                if entry.get('revision') is not None:
                    count += f' · r{entry["revision"]}'
                label = f'{when}{count} · {entry["reason"].replace("-", " ")}'
                key = str(entry['path'])
                self._entries[key] = label
                options.append((label, key))
            if self.file.value == PROJECT_NAME:
                previous = vault.path.with_suffix('.previous.json')
                raw = read_optional(previous)
                if raw is not None:
                    try:
                        project = validate_settings(vault.path, raw)
                        when = datetime.fromtimestamp(previous.stat().st_mtime).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
                        label = f'{when} · {len(project["graphs"])} graphs · previous-save fallback'
                        self._entries[str(previous)] = label
                        options.append((label, str(previous)))
                    except Exception:
                        damaged += 1
            self.snapshots.options = options
            self.snapshots.value = None
            self.restore_button.disabled = True
            text = f'{len(options)} available backups.' if options else 'No usable backups yet for this settings file.'
            if damaged:
                text += f' {damaged} damaged or incompatible ' + ('copy is' if damaged == 1 else 'copies are') \
                    + ' preserved but cannot be restored.'
            warning = backup_warning(vault.path)
            self.message.value = escape(text) + ('<br><b>' + escape(warning) + '</b>' if warning else '')
        except Exception as error:
            self.snapshots.options = []
            self.restore_button.disabled = True
            self.message.value = '<b>Could not read backup history:</b> ' + escape(str(error))
        self.location.value = '<small style="overflow-wrap:anywhere">Backup folder: <code>' + escape(str(vault.directory)) + '</code></small>'

    def _selected(self, _=None):
        self._cancel()
        self.restore_button.disabled = self.snapshots.value not in self._entries

    def _cancel(self, _=None):
        self.pending = None
        self.confirmation.layout.display = 'none'

    def _backup(self, _=None):
        self.backup_now.disabled = True
        try:
            if self.before_backup is not None and self.before_backup() is False:
                raise RuntimeError('Resolve the save warning before making a manual backup.')
            saved, failures = [], []
            for name in (PROJECT_NAME, PATHS_NAME):
                path = self.root / name
                try:
                    raw = read_optional(path)
                    if raw is None:
                        continue
                    validate_settings(path, raw)
                    warning = BackupVault(path).try_capture(raw, reason='manual')
                    if warning:
                        raise OSError(warning)
                    saved.append(name)
                except Exception as error:
                    failures.append(f'{name}: {error}')
            self.refresh()
            self.message.value = (escape('Backed up: ' + ', '.join(saved)) if saved else 'No settings files were backed up.')
            if failures:
                self.message.value += '<br><b>' + escape(' · '.join(failures)) + '</b>'
        except Exception as error:
            self.message.value = '<b>Backup not completed:</b> ' + escape(str(error))
        finally:
            self.backup_now.disabled = False

    def _snapshot_bytes(self, vault, path):
        path = Path(path)
        if path == vault.path.with_suffix('.previous.json'):
            return path.read_bytes()
        return vault.read(path)[1]

    def _ask_restore(self, _=None):
        key = self.snapshots.value
        if key not in self._entries:
            return
        try:
            vault = self._vault()
            raw = self._snapshot_bytes(vault, key)
            validate_settings(vault.path, raw)
            self.pending = (vault, key, digest(read_optional(vault.path)), digest(raw))
            self.confirm_message.value = ('<b>Replace ' + escape(vault.path.name) + ' with this backup?</b><br>'
                + escape(self._entries[key]) + '<br>The current file will be preserved first, including a damaged original. '
                'The workbench will reopen from the restored settings. Unsaved editor drafts will be discarded. '
                'Research data and exported results are not changed.')
            self.confirmation.layout.display = ''
        except Exception as error:
            self._cancel()
            self.message.value = '<b>Cannot restore this backup:</b> ' + escape(str(error))

    def _confirm(self, _=None):
        if self.pending is None:
            return
        vault, key, current_hash, snapshot_hash = self.pending
        self.confirm_button.disabled = True
        try:
            vault.restore(key, expected_current=current_hash, expected_snapshot=snapshot_hash)
        except Exception as error:
            self.message.value = '<b>Restore not completed:</b> ' + escape(str(error))
            self._cancel()
        else:
            self.refresh()
            self.message.value = 'Restored ' + escape(vault.path.name) + '. The prior file is preserved in backup history.'
            try:
                if self.after_restore is not None:
                    self.after_restore(vault.path)
            except Exception as error:
                self.message.value += '<br><b>Settings restored, but the workbench could not reopen:</b> ' + escape(str(error))
        finally:
            self.confirm_button.disabled = False

    def show_recovery(self, message, name=PROJECT_NAME, *, heading='Recovery needed'):
        self.file.value = name
        self.ui.selected_index = 0
        self.refresh()
        self.message.value = '<b>' + escape(heading) + ':</b> ' + escape(message) + '<br>' + self.message.value

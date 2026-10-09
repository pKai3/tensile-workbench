"""Per-group approval UI for content-verified data relocations."""
from copy import deepcopy
from html import escape

from tensile_moves import scan_moves, migrate_settings, references, forget_group
from tensile_activity import busy


class MoveReview:
    def __init__(self, widgets, store, session, *, before_apply, after_apply, reload_data, after_forget=None):
        self.w, self.store, self.session = widgets, store, session
        self.before_apply, self.after_apply = before_apply, after_apply
        self.after_forget = after_forget or after_apply
        self._pending_forget = None
        self._owned = []
        self.summary = widgets.HTML()
        self.message = widgets.HTML()
        self.rows = widgets.VBox(layout=widgets.Layout(width='100%'))
        self.check = widgets.Button(description='Check for moved groups', layout=widgets.Layout(width='auto'))
        self.check.on_click(lambda _: reload_data())
        self.forget_message = widgets.HTML()
        self.confirm_forget = widgets.Button(description='Confirm forget', button_style='danger')
        self.cancel_forget = widgets.Button(description='Cancel')
        self.confirm_forget.on_click(lambda _: self._forget())
        self.cancel_forget.on_click(lambda _: self._cancel_forget())
        self.confirmation = widgets.VBox([self.forget_message,
            widgets.HBox([self.confirm_forget, self.cancel_forget])], layout=widgets.Layout(display='none'))
        self.ui = widgets.VBox([
            widgets.HBox([self.summary, self.check], layout=widgets.Layout(
                flex_flow='row wrap', align_items='center', gap='8px')),
            self.message, self.confirmation, self.rows], layout=widgets.Layout(width='100%'))

    @busy('Checking for moved sample groups…')
    def refresh(self):
        self._cancel_forget()
        self.check.disabled = True
        self.summary.value = 'Checking data-folder identities…'
        try:
            tracking, proposals, warnings = scan_moves(
                self.store.data, self.session.data_dir, self.session.files)
            project = deepcopy(self.store.data)
            project['data_move_tracking'] = tracking
            if project != self.store.data:
                self.store.save(project)
                self.session.set_project(self.store.data)
            self._draw(proposals, warnings)
            self.message.value = ''
        except Exception as error:
            self.summary.value = '<b>Move check unavailable.</b>'
            self.message.value = escape(str(error)) + ' No relocation settings were applied.'
            self._clear_rows()
        finally:
            self.check.disabled = False

    def _clear_rows(self):
        self.rows.children = ()
        for widget in reversed(self._owned):
            widget.close()
        self._owned = []

    def _draw(self, proposals, warnings):
        self._clear_rows()
        known, _ = references(self.store.data)
        known.update(self.store.data.get('data_move_tracking', {}).get('groups', {}))
        missing = sorted(known - self.session.files.keys(), key=len, reverse=True)
        notices = [(warning, next((g for g in missing if warning.startswith(g + ':')), None))
                   for warning in warnings]
        count = len(proposals)
        self.summary.value = (f'<b>{count} moved group(s) need your OK.</b> No settings migrated yet.' if count
                              else 'Move protection: no pending migrations.' if not notices
                              else '<b>Move protection: review needed.</b> No settings migrated.')
        children = []
        for proposal in proposals:
            old, new = escape(proposal['old']), escape(proposal['new'])
            pairs = ''.join('<li>' + escape(a) + ' → ' + escape(b) + '</li>'
                            for a, b in proposal['mapping'].items())
            detail = (f'<b>{old} → {new}</b><br>{len(proposal["mapping"])} unchanged CSV file(s) matched. '
                      'Review this group before transferring graph selections, specimen overrides/exclusions, '
                      'data-use modes, labels, colours, gauges and other group settings.')
            if proposal['partial_evidence']:
                detail += '<br><b>Partial evidence:</b> matched saved override fingerprints; no older full-group inventory exists.'
            if proposal['unresolved']:
                detail += '<br><b>Not migrated (no verified file match):</b> ' + escape(', '.join(proposal['unresolved']))
            detail += '<details><summary>Review matched file paths</summary><ul>' + pairs + '</ul></details>'
            if proposal['blocked']:
                detail += '<br><b>Blocked:</b> ' + escape(proposal['blocked'])
            text = self.w.HTML(detail)
            button = self.w.Button(description='OK, migrate settings', button_style='warning',
                                   disabled=bool(proposal['blocked']), layout=self.w.Layout(width='auto', align_self='flex-start'))
            button.on_click(lambda _, p=proposal, b=button: self._approve(p, b))
            row = self.w.VBox([text, button], layout=self.w.Layout(
                width='100%', border='1px solid #dfb45c', padding='10px', margin='4px 0'))
            self._owned.extend([text, button, row])
            children.append(row)
        for warning, group in notices:
            notice = self.w.HTML(escape(warning))
            controls = [notice]
            if group is not None:
                forget = self.w.Button(description='Forget group',
                    tooltip='Clear this removed group’s saved references and tracking; asks for confirmation',
                    layout=self.w.Layout(width='auto', align_self='flex-start'))
                forget.on_click(lambda _, g=group: self._ask_forget(g))
                controls.append(forget)
                self._owned.append(forget)
            row = self.w.VBox(controls, layout=self.w.Layout(width='100%', margin='4px 0'))
            children.append(row)
            self._owned.extend([notice, row])
        self.rows.children = tuple(children)

    def _ask_forget(self, group):
        self._pending_forget = group
        self.forget_message.value = ('<b>Forget ' + escape(group) + '?</b> This removes its saved graph selections, '
            'labels, specimen overrides/exclusions and tracking/history. No forgotten-group log is kept. '
            'Source files and exports are untouched; specimen settings belonging to other available groups are kept.')
        self.confirmation.layout.display = ''

    def _cancel_forget(self):
        self._pending_forget = None
        self.confirmation.layout.display = 'none'

    @busy('Clearing removed-group settings…')
    def _forget(self):
        group = self._pending_forget
        if group is None:
            return
        try:
            if not self.before_apply():
                return
            self.session.reload_data()
            project = forget_group(self.store.data, group, live_groups=self.session.files)
            self.store.save(project)
            self.session.set_project(self.store.data)
        except Exception as error:
            self.message.value = '<b>Group not forgotten:</b> ' + escape(str(error))
            return
        self._cancel_forget()
        try:
            self.after_forget()
            self.refresh()
            self.message.value = 'Forgot ' + escape(group) + '. Its saved references and tracking were cleared. No source files deleted.'
        except Exception as error:
            self.message.value = '<b>Group forgotten.</b> Reload the workbench to refresh the view: ' + escape(str(error))

    @busy('Verifying move and migrating settings…')
    def _approve(self, proposal, button):
        button.disabled = self.check.disabled = True
        try:
            if not self.before_apply():
                raise ValueError('Resolve the graph-save warning before approving a move.')
            # Rediscover and verify at approval, not just against stale UI/cache.
            self.session.reload_data()
            tracking, proposals, _ = scan_moves(self.store.data, self.session.data_dir,
                self.session.files, force_groups=(proposal['new'],))
            fresh = next((p for p in proposals if p['old'] == proposal['old']), None)
            if (not fresh or fresh['blocked'] or any(fresh[k] != proposal[k]
                    for k in ('new', 'mapping', 'target', 'unresolved', 'partial_evidence'))):
                raise ValueError('Files or settings changed, or the match is now ambiguous. '
                                 'Check for moved groups again and review the new proposal.')
            project = deepcopy(self.store.data)
            project['data_move_tracking'] = tracking
            project = migrate_settings(project, fresh)
            self.store.save(project)  # Existing lock, conflict check and atomic backup.
            self.session.set_project(self.store.data)
        except Exception as error:
            self.message.value = '<b>Move not applied:</b> ' + escape(str(error))
        else:
            try:
                self.after_apply()
                self.refresh()
                self.message.value = 'Approved: ' + escape(proposal['old']) + ' → ' + escape(proposal['new']) + '. Source files were not changed.'
            except Exception as error:
                self.message.value = '<b>Migration saved.</b> Reload the workbench to refresh the view: ' + escape(str(error))
        finally:
            if button.comm is not None:
                button.disabled = bool(proposal['blocked'])
            self.check.disabled = False

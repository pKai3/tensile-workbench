"""Standalone, persistent multi-plot Tensile Workbench.

Importing this module does not read data or write outputs. Launch with the
companion notebook. Export is a separate, explicit button action.
"""

from collections import OrderedDict
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime
from html import escape
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from time import perf_counter
from workbench_project import ProjectStore, ProjectConflict, validate_project
from tensile_plot_view import DualPlotView, GroupCheckboxes
from tensile_instron import InstronSummaries
from tensile_tables import property_tables, PropertyTablesView, specimen_review_mask
from tensile_properties import specimen_calculation
from tensile_fracture import (endpoint_available, validate_failure_override, manual_failure_endpoint,
                              automatic_fracture_endpoint, fracture_curve)
from tensile_gauge import gauge_record, group_policy, group_basis_label, migrate_group_gauges, validate_group_policy
from tensile_exports import export_results, export_curves
from tensile_group_plot import GROUP_FAMILY, GROUP_DEFAULTS, ordered_groups, render_group_properties, validate_group_display
from tensile_colors import DEFAULT_PALETTE, PALETTE_OPTIONS, group_color_map, palette_preview, validate_palette
from tensile_fit import fit_policy, validate_override, validate_threshold
from tensile_selection import (is_included, selection_state, migrate_specimen_selections,
                               specimen_id, SAMPLE_GROUP_PREFIX, SAMPLE_ID_PREFIX,
                               DATA_MODES, record_mode, property_allowed, curve_allowed, validate_data_mode)
from tensile_startup import sample_data_settings, save_sample_data_visibility, resolve_folder
import hashlib
import io
import json
import platform
import re
import uuid

NEW_GRAPH_ACTION = '__create_new_graph__'


def upgrade_legacy_demo_graph(project, data_dir, sample_data_dir):
    """Upgrade only the shipped demo graph; never reinterpret personal groups."""
    project = deepcopy(project)
    demo_names = {'Demo_Ductile', 'Demo_Balanced', 'Demo_Strong'}
    for graph in project['graphs']:
        groups = graph['settings']['groups']
        if graph['id'] != 'demo-comparison' or not groups or not set(groups) <= demo_names:
            continue
        if any((data_dir / group).is_dir() for group in groups) and data_dir != sample_data_dir:
            continue  # An actual research group always keeps its own identity.
        rename = {group: SAMPLE_GROUP_PREFIX + group for group in groups}
        graph['settings']['groups'] = [rename[group] for group in groups]
        for key in ('name_overrides', 'color_overrides', 'youngs_modulus_overrides', 'representative_overrides', 'gauge_reconstruction'):
            if key in graph['definition']:
                graph['definition'][key] = {rename.get(k, k): v for k, v in graph['definition'][key].items()}
        exclusions = graph['definition'].get('specimen_exclusions')
        if exclusions is not None:
            graph['definition']['specimen_exclusions'] = {
                SAMPLE_ID_PREFIX + k if k.split('/')[0] in rename else k: v for k, v in exclusions.items()}
        for mapping in (project.get('specimen_exclusions', {}), project.get('specimen_data_modes', {}),
                        graph['definition'].get('specimen_inclusion_overrides', {})):
            for ident in list(mapping):
                if ident.split('/')[0] in rename:
                    mapping[SAMPLE_ID_PREFIX + ident] = mapping.pop(ident)
        for group, replacement in rename.items():
            if group in project.get('display_names', {}):
                project['display_names'][replacement] = project['display_names'][group]
    return project


def graph_menu_options(graphs):
    """Keep saved order, distinguish unnamed drafts, and put creation last."""
    named, drafts = [], []
    for graph in graphs:
        match = re.fullmatch(r'New graph( \d+)?', graph['name'], re.IGNORECASE)
        if match and not graph['settings'].get('groups'):
            drafts.append(('Untitled graph' + (match.group(1) or '') + ' (draft)', graph['id']))
        else:
            named.append((graph['name'], graph['id']))
    return named + drafts + [('＋ Create new graph…', NEW_GRAPH_ACTION)]


FAMILIES = [
    ("Landmark-derived work hardening", "work_hardening_landmark"),
    ("Original work hardening", "work_hardening"),
    ("Compare both work-hardening methods", "work_hardening_comparison"),
    ("Landmark tensile average", "landmark"),
    ("Pointwise tensile average", "pointwise"),
    ("Compare both tensile averages", "comparison"),
    ("Representative tensile curves", "representative"),
    ("0.2% YS vs elongation", "ys_vs_el"),
    ("UTS vs elongation", "uts_vs_el"),
    ("YS, UTS and elongation by sample", GROUP_FAMILY),
]

PROPERTY_FAMILIES = ('ys_vs_el', 'uts_vs_el')
PROPERTY_DEFAULTS = {'property_error_bars': True,
                     **{family + suffix: None for family in PROPERTY_FAMILIES
                        for suffix in ('_xlim', '_ylim')}}
AXIS_DEFAULTS = {'tensile_xlim': [0, 30], 'tensile_ylim': [0, 1000],
                 'properties_by_group_ylim': [0, 1000], 'properties_by_group_el_ylim': [0, 30],
                 'wh_xlim': [0, 7], 'wh_ylim': [0, 4500],
                 **{family + suffix: limits for family in PROPERTY_FAMILIES
                    for suffix, limits in (('_xlim', [0, 30]), ('_ylim', [0, 1000]))}}

# These settings change the viewer, not the calculations or figure contents.
VIEW_ONLY_SETTINGS = ('columns', 'plot_width', 'renderer', 'live_update', 'export_tables')


class PreviewSession:
    """Headless calculation layer, also usable without Jupyter widgets."""

    def __init__(self, project_dir=None, project=None, data_dir=None, output_dir=None):
        self.project_dir = Path(project_dir or Path(__file__).parent).expanduser().resolve()
        self._output_override = output_dir
        engine_path = self.project_dir / "tensile_core.py"
        if not engine_path.is_file():
            raise FileNotFoundError(f"The standalone calculation library is missing: {engine_path}")
        spec = spec_from_file_location("_tensile_preview_" + uuid.uuid4().hex, engine_path)
        self.engine = module_from_spec(spec)
        spec.loader.exec_module(self.engine)
        self.engine_path = engine_path
        self.engine_sha256 = hashlib.sha256(engine_path.read_bytes()).hexdigest()
        self.project = deepcopy(project) if project is not None else json.loads((self.project_dir / "tensile_workbench_defaults.json").read_text())
        validate_project(self.project)
        configured = Path(data_dir or self.project.get("data_directory", "data")).expanduser()
        self.data_dir = (configured if configured.is_absolute() else self.project_dir / configured).resolve()
        sample_settings = sample_data_settings(self.project_dir)
        self.sample_data_dir = resolve_folder(sample_settings['sample_data_directory'], self.project_dir)
        self.show_sample_data = sample_settings['show_sample_data']
        self.set_project(self.project)
        self._records = {}
        self._models = OrderedDict()
        self._previews = OrderedDict()
        self.reload_data()

    def reload_data(self):
        if not self.data_dir.is_dir():
            raise FileNotFoundError(f"Tensile data directory not found: {self.data_dir}")
        # This is the existing script's scoped data-folder discovery, not a
        # search of the user's home or thesis directories.
        # Separate namespaces prevent samples ever merging with a research group
        # of the same name. A real directory name cannot contain the '/' prefix.
        research = self.engine.find_sample_groups(self.data_dir) if self.data_dir != self.sample_data_dir else {}
        samples = (self.engine.find_sample_groups(self.sample_data_dir)
                   if self.show_sample_data and self.sample_data_dir.is_dir() else {})
        files = {**research, **{SAMPLE_GROUP_PREFIX + group: paths for group, paths in samples.items()}}
        roots = {group: self.data_dir for group in research}
        roots.update({SAMPLE_GROUP_PREFIX + group: self.sample_data_dir for group in samples})
        directories = {group: self.data_dir / group for group in research}
        directories.update({SAMPLE_GROUP_PREFIX + group: self.sample_data_dir / group for group in samples})
        self.files, self.source_roots = files, roots
        self._records.clear()
        self._models.clear()
        self._previews.clear()
        self._property_frames = {}
        self.instron = InstronSummaries(self.data_dir, directories)
        import itertools
        palette = itertools.cycle(self.engine.plt.rcParams["axes.prop_cycle"].by_key()["color"])
        # Adding sample groups must not change the colours of research groups.
        self.colors = {g: next(palette) for g in [*sorted(research), *sorted(set(files) - set(research))]}

    def color_map(self, state, spec):
        return group_color_map(self.colors, state.get('color_palette', DEFAULT_PALETTE),
                               spec.get('color_overrides', {}))

    def hidden_sample_group(self, group):
        return group.startswith(SAMPLE_GROUP_PREFIX) and not self.show_sample_data

    def visible_groups(self, groups):
        return [group for group in groups if not self.hidden_sample_group(group)]

    def set_project(self, project):
        previous_policy = fit_policy(self.project)
        previous_selections = self.selection_signature()
        project = migrate_specimen_selections(migrate_group_gauges(project))
        self.project = deepcopy(project)
        self.graphs = [{**g["definition"], "name": g["name"]} for g in project["graphs"]]
        self.engine.NAME_LOOKUP = deepcopy(project.get("display_names", {}))
        if previous_policy != fit_policy(project) and hasattr(self, '_records'):
            for records in self._records.values():
                for record in records:
                    self._bind_fit_context(record)
                    record.pop('_property_cache', None)
            self._property_frames.clear()
            self._models.clear()
            self._previews.clear()
        if previous_selections != self.selection_signature() and hasattr(self, '_records'):
            self._property_frames.clear()
            self._models.clear()
            self._previews.clear()

    def _bind_fit_context(self, record):
        record['_fit_override'] = deepcopy(self.project.get('specimen_fit_overrides', {}).get(specimen_id(record)))
        record['_failure_override'] = deepcopy(self.project.get('specimen_failure_overrides', {}).get(specimen_id(record)))
        record['_fit_r2_threshold'] = self.project.get('yield_r2_warning', .98)

    def fit_signature(self):
        return json.dumps(fit_policy(self.project), sort_keys=True)

    def selection_signature(self):
        return json.dumps([self.project.get('specimen_exclusions', {}),
            self.project.get('specimen_data_modes', {}),
            {g['id']: g['definition'].get('specimen_inclusion_overrides', {})
             for g in self.project['graphs']}], sort_keys=True)

    def selection_provenance(self, state, spec):
        ids = {specimen_id(r) for group in self.visible_groups(state['groups']) for r in self._load(group)}
        return {'global_exclusions': {k: v for k, v in self.project.get('specimen_exclusions', {}).items() if k in ids},
                'global_data_modes': {k: v for k, v in self.project.get('specimen_data_modes', {}).items() if k in ids},
                'graph_overrides': {k: v for k, v in spec.get('specimen_inclusion_overrides', {}).items() if k in ids}}

    def fit_provenance(self, state):
        ids = {specimen_id(r) for group in self.visible_groups(state['groups']) for r in self._load(group)}
        return {'yield_r2_warning': self.project.get('yield_r2_warning', .98),
                'specimen_fit_overrides': {k: v for k, v in self.project.get('specimen_fit_overrides', {}).items() if k in ids},
                'specimen_fit_history': [event for event in self.project.get('specimen_fit_history', []) if event['specimen_id'] in ids],
                'specimen_failure_overrides': {k: v for k, v in self.project.get('specimen_failure_overrides', {}).items() if k in ids},
                'specimen_failure_history': [event for event in self.project.get('specimen_failure_history', []) if event['specimen_id'] in ids]}

    def output_root(self):
        """Local folder choice overrides the graph template without changing it."""
        from tensile_startup import resolve_folder
        configured = self._output_override if self._output_override is not None else self.project.get('output_directory', './output')
        return resolve_folder(configured, self.project_dir)

    def defaults(self, graph_index=0):
        result = deepcopy(self.project["graphs"][graph_index]["settings"])
        for key, value in {**PROPERTY_DEFAULTS, **GROUP_DEFAULTS}.items():
            result.setdefault(key, deepcopy(value))
        result["graph_index"] = graph_index
        result["family"] = result["families"][0] if result["families"] else "landmark"
        return result

    def _load(self, group):
        if group not in self._records:
            if group not in self.files:
                raise ValueError(f"Unknown group: {group}")
            records = []
            for source in self.files[group]:
                result = self.engine.load_and_prepare_curve(source, return_metadata=True)
                if result is None:
                    print(f"[SKIP] No usable stress–strain data: {source.name}")
                    continue
                strain, stress, acquisition, indices = result
                records.append({
                    "sample": source.stem, "source_file": str(source),
                    "specimen_id": ((SAMPLE_ID_PREFIX if group.startswith(SAMPLE_GROUP_PREFIX) else '')
                                    + source.relative_to(self.source_roots[group]).as_posix()),
                    "strain_pct": strain, "stress_mpa": stress,
                    "raw_strain_pct": strain, "raw_stress_mpa": stress,
                    "_acquisition": acquisition, "_measurement_indices": indices,
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                })
            for record in records:
                # Operator/location label is not the Instron export-row suffix.
                # Preserve sample/source IDs for matching, settings and audit.
                record['specimen_label'] = self.instron.match(group, record)['label']
                self._bind_fit_context(record)
                properties = self.engine.specimen_properties(record)
                record['failure_elongation_pct'] = properties['Failure elongation (%)']
            self._records[group] = records
        return self._records[group]

    def included_records(self, groups, spec):
        """The single selection gate for every plot family and average export."""
        return {group: selected for group in self.visible_groups(groups)
                if (selected := [self.selected_record(row, spec) for row in self._load(group)
                                 if is_included(row, spec, self.project)])}

    def selected_record(self, row, spec):
        selection = selection_state(row, spec, self.project)
        return {**row, '_data_mode': selection['mode'], '_selection': selection}

    def group_review_records(self, group, spec):
        fractions = spec.get('landmark_yield_fit_fractions', self.engine.LANDMARK_YIELD_FIT_FRACTIONS)
        return [{**self.selected_record(row, spec),
                 '_review_properties': self.engine.specimen_properties(row, fractions,
                     self.engine.LANDMARK_YIELD_R2_WARNING, apply_policy=False)} for row in self._load(group)]

    def scatter_omission_warning(self, state, spec):
        omitted = [f"{group} / {r.get('specimen_label') or r['sample']}"
                   for group, rows in self.included_records(state['groups'], spec).items() for r in rows
                   if not property_allowed(record_mode(r), 'el')]
        if not omitted:
            return ''
        return ('Omitted from strength–EL pairs because elongation is excluded: ' + '; '.join(omitted) +
                '. Eligible strength results still contribute to the group statistics and landmark anchors. '
                'Scatter means use paired specimens only, so they may differ from the summary means.')

    def property_tables(self, state, spec):
        """Available without selecting, rendering or successfully fitting a plot."""
        key = json.dumps([state['groups'], spec.get('landmark_yield_fit_fractions', self.engine.LANDMARK_YIELD_FIT_FRACTIONS),
                          self.project.get('specimen_data_modes', {}),
                          self.project.get('specimen_exclusions', {}), spec.get('specimen_inclusion_overrides', {}),
                          spec.get('specimen_exclusions', {}),
                          {g: group_policy(state, spec, g) for g in state['groups']}], sort_keys=True)
        if key not in self._property_frames:
            records = self.analysis_records(state, spec, include_excluded=True)
            self._property_frames[key] = property_tables(records, spec, self.engine, self.instron, self.project)
            if len(self._property_frames) > 16:
                self._property_frames.pop(next(iter(self._property_frames)))
        return self._property_frames[key]

    def analysis_records(self, state, spec, include_excluded=False, measured=False, require_curves=True):
        records = ({g: [self.selected_record(row, spec) for row in self._load(g)] for g in self.visible_groups(state['groups'])}
                   if include_excluded else self.included_records(state['groups'], spec))
        if measured:
            return records
        result = {}
        for g, rows in records.items():
            policy = group_policy(state, spec, g)
            result[g] = [gauge_record(r, self.instron.match(g, r), policy['enabled'] and curve_allowed(r),
                                      policy['target_gauge_mm']) for r in rows]
        if not include_excluded and require_curves:
            errors = [f"{g}/{r['sample']}: {r['_gauge']['Gauge correction status']}"
                      for g, rows in result.items() for r in rows
                      if curve_allowed(r) and group_policy(state, spec, g)['enabled'] and r['_gauge']['Gauge correction status'] != 'Applied']
            errors.extend(f"{g}/{r['sample']}: CSV fracture not detected — {r['_fracture']['reason']}"
                          for g, rows in result.items() for r in rows
                          if curve_allowed(r) and not group_policy(state, spec, g)['enabled'] and not endpoint_available(r['_fracture']))
            if errors:
                raise ValueError('Specimen review required; none have been automatically excluded. ' + '; '.join(errors))
            for g, rows in result.items():
                if group_policy(state, spec, g)['enabled']:
                    target = group_policy(state, spec, g)['target_gauge_mm']
                    print(f'[GAUGE] {g}: reconstructed post-peak strain at target gauge {target:.2f} mm; '
                          f'{sum(curve_allowed(r) for r in rows)} eligible specimens, each using its own AVE dot spacing.')
                    for r in rows:
                        if r['_gauge']['Gauge model warning']:
                            print(f"[GAUGE WARNING] {g}/{r['sample']}: {r['_gauge']['Gauge model warning']}")
        return result

    def export_properties(self, state, spec):
        """Explicit table-only export; does not calculate average curves."""
        frames = self.property_tables(state, spec)
        if frames['tensile_samples'].empty:
            raise ValueError('No specimen data to export.')
        base = self.output_root()
        destination = base / self.engine.safe_filename(spec['name']) / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_tables')
        destination.mkdir(parents=True, exist_ok=False)
        export_results(frames, destination / (self.engine.safe_filename(spec['name']) + '_results.xlsx'),
                       {'graph': spec, 'settings': state, 'fit_policy': self.fit_provenance(state),
                        'specimen_selection': self.selection_provenance(state, spec),
                        'engine_sha256': self.engine_sha256})
        (destination / 'settings.json').write_text(json.dumps({'graph_definition': spec, 'settings': state,
            'specimen_fit_policy': self.fit_provenance(state),
            'specimen_selection': self.selection_provenance(state, spec),
            'engine_sha256_at_load': self.engine_sha256,
            'note': 'Individual specimen properties only. Instron comparisons use CSV summaries; see the Audit sheet for source hashes.'}, indent=2))
        return destination

    def specimen_inspection(self, state, spec, ident):
        """Inspect only a currently selected group's loaded record; no file-path lookup.

        Excluded records remain reviewable. Hard-ignored files and hidden sample
        groups never reach this method's candidate list.
        """
        fractions = spec.get('landmark_yield_fit_fractions', self.engine.LANDMARK_YIELD_FIT_FRACTIONS)
        for group in self.visible_groups(state['groups']):
            for record in self._load(group):
                if specimen_id(record) == ident:
                    reference = self.instron.match(group, record)
                    policy = group_policy(state, spec, group)
                    selection = selection_state(record, spec, self.project)
                    return {'group': group, 'sample': record['sample'], 'specimen_id': ident,
                            'source_file': record['source_file'], 'source_sha256': record.get('source_sha256', ''),
                            'included': selection['included'], 'selection_scope': selection['scope'],
                            'data_use': DATA_MODES[selection['mode']], 'data_mode': selection['mode'],
                            'exclusion_reason': selection['reason'],
                            'record': record,
                            'calculation': specimen_calculation(record, fractions, self.engine.LANDMARK_YIELD_R2_WARNING),
                            'reference': reference, 'gauge_policy': policy,
                            'gauge_preview': gauge_record(record, reference, True, policy['target_gauge_mm'])}
        raise ValueError('Specimen is no longer available in this graph. Refresh the tables.')

    def _wh_settings(self, state, spec):
        overrides = spec.get("youngs_modulus_overrides", {}) if state["respect_modulus_overrides"] else {}
        return {
            "youngs_modulus_mpa": state["modulus_gpa"] * 1000,
            "youngs_modulus_overrides": {g: value for g, value in overrides.items() if g in state["groups"]},
            "min_plastic_strain_percent": state["min_plastic_strain"],
            "num_points": state["wh_points"],
            "wh_filter_settings": {
                "despike_enabled": state["despike"],
                "despike_window_percent": state["despike_window"],
                "despike_sigma": state["despike_sigma"],
                "median_filter_enabled": state["median"],
                "median_filter_window_percent": state["median_window"],
                "smooth_enabled": state["smooth"],
                "smooth_window_percent": state["smooth_window"],
                "poly_order": state["poly_order"],
            },
        }

    @staticmethod
    def _validate(state):
        validate_palette(state.get('color_palette', DEFAULT_PALETTE))
        validate_group_display(state)
        if not state["groups"]:
            raise ValueError("Select at least one sample group.")
        if state["family"] not in dict((value, label) for label, value in FAMILIES):
            raise ValueError("Unknown plot family.")
        for key, minimum in (("landmark_points", 3), ("pointwise_points", 10), ("wh_points", 10)):
            value = state[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{key} must be an integer of at least {minimum}.")
        import math
        for key in ("modulus_gpa", "despike_window", "despike_sigma", "median_window", "smooth_window", "tail_window"):
            if not math.isfinite(state[key]) or state[key] <= 0:
                raise ValueError(f"{key} must be finite and positive.")
        for key in ("min_plastic_strain", "tail_setback"):
            if not math.isfinite(state[key]) or state[key] < 0:
                raise ValueError(f"{key} must be finite and nonnegative.")
        if state["poly_order"] not in (1, 2, 3, 4, 5):
            raise ValueError("Polynomial order must be 1–5.")
        for key in AXIS_DEFAULTS:
            pair = state.get(key)
            if pair is not None and (len(pair) != 2 or not all(math.isfinite(v) for v in pair) or pair[0] >= pair[1]):
                raise ValueError(f"{key}: lower limit must be smaller than upper limit.")

    def render(self, state):
        """Cache unaffected plots when another control or panel changes."""
        self._validate(state)
        key_state = deepcopy(state)
        for key in ("families", "show_both_versions", "graph_index", *VIEW_ONLY_SETTINGS):
            key_state.pop(key, None)
        family = state["family"]
        for key in PROPERTY_DEFAULTS:
            if family not in PROPERTY_FAMILIES or (key != 'property_error_bars' and not key.startswith(family + '_')):
                key_state.pop(key, None)
        if family != GROUP_FAMILY:
            for key in GROUP_DEFAULTS:
                key_state.pop(key, None)
        if family in (*PROPERTY_FAMILIES, GROUP_FAMILY):
            for key in ('landmark_points', 'pointwise_points', 'landmark_error_bars',
                        'tail_enabled', 'tail_window', 'tail_setback', 'tensile_xlim', 'tensile_ylim'):
                key_state.pop(key, None)
        if not family.startswith("work_hardening"):
            for key in ("wh_points", "modulus_gpa", "respect_modulus_overrides", "min_plastic_strain", "despike", "despike_window", "despike_sigma", "median", "median_window", "smooth", "smooth_window", "poly_order", "wh_xlim", "wh_ylim"):
                key_state.pop(key, None)
        else:
            for key in ("pointwise_points", "tail_enabled", "tail_window", "tail_setback", "landmark_error_bars", "tensile_xlim", "tensile_ylim"):
                key_state.pop(key, None)
            if family == "work_hardening":
                key_state.pop("landmark_points", None)
        key = json.dumps([key_state, self.graphs[state["graph_index"]], self.project.get("display_names", {}),
                          self.selection_signature()], sort_keys=True)
        if key not in self._previews:
            self._previews[key] = self._render_uncached(state)
            if len(self._previews) > 12:
                self._previews.popitem(last=False)
        self._previews.move_to_end(key)
        spec = deepcopy(self.graphs[state["graph_index"]])
        spec["tensile_mean_tail"] = {**self.engine.TENSILE_MEAN_TAIL, **spec.get("tensile_mean_tail", {}),
            "enabled": state["tail_enabled"], "fit_window_percent": state["tail_window"], "setback_percent": state["tail_setback"]}
        return {**self._previews[key], "state": deepcopy(state), "graph_spec": spec,
                'selection_signature': self.selection_signature(),
                'fit_signature': self.fit_signature(), 'specimen_fit_policy': self.fit_provenance(state)}

    def _render_uncached(self, state):
        """Compute one preview in memory. Never invoke main() or any exporters."""
        self._validate(state)
        e = self.engine
        spec = deepcopy(self.graphs[state["graph_index"]])
        spec["tensile_mean_tail"] = {
            **e.TENSILE_MEAN_TAIL, **spec.get("tensile_mean_tail", {}),
            "enabled": state["tail_enabled"], "fit_window_percent": state["tail_window"],
            "setback_percent": state["tail_setback"],
        }
        stream = io.StringIO()
        start = perf_counter()
        before = set(e.plt.get_fignums())
        with redirect_stdout(stream), redirect_stderr(stream):
            try:
                family = state['family']
                records = self.analysis_records(state, spec, measured=family.startswith('work_hardening'),
                    require_curves=family not in (*PROPERTY_FAMILIES, GROUP_FAMILY))
                if not records:
                    raise ValueError('No included usable specimens. Change Data use on the Specimens tab.')
                empty = [g for g in state['groups'] if g not in records]
                if empty:
                    print('[SELECTION] No included usable specimens; omitted groups: ' + ', '.join(empty))
                shape_records = {g: eligible for g, rows in records.items()
                    if (eligible := [r for r in rows if curve_allowed(r, prepeak=family.startswith('work_hardening'))])}
                curves = {g: [(r["strain_pct"], r["stress_mpa"]) for r in rows] for g, rows in shape_records.items()}
                if family in (*PROPERTY_FAMILIES, GROUP_FAMILY):
                    xlim, ylim = state.get(family + '_xlim'), state.get(family + '_ylim')
                else:
                    auto_x, auto_y = e.compute_axes(curves)
                    is_wh = family.startswith('work_hardening')
                    xlim = state['wh_xlim'] if is_wh else state['tensile_xlim'] or auto_x
                    ylim = state['wh_ylim'] if is_wh else state['tensile_ylim'] or auto_y
                models = None
                if family not in ("work_hardening", "representative", *PROPERTY_FAMILIES, GROUP_FAMILY):
                    key = json.dumps([spec, {g: [specimen_id(r) for r in rows] for g, rows in records.items()},
                        state["landmark_points"], state["pointwise_points"],
                        family.startswith('work_hardening')], sort_keys=True)
                    if key not in self._models:
                        model_log = io.StringIO()
                        with redirect_stdout(model_log):
                            result = e.prepare_average_curves(spec, records,
                                landmark_points_per_stage=state["landmark_points"],
                                pointwise_points=state["pointwise_points"],
                                prepeak_only=family.startswith('work_hardening'))
                        self._models[key] = (result, model_log.getvalue())
                        if len(self._models) > 8:
                            self._models.popitem(last=False)
                    self._models.move_to_end(key)
                    result, model_log = self._models[key]
                    models = result[0]
                    print(model_log, end="")
                variant = "with_individuals" if state["show_individuals"] else "without_individuals"
                title_keys = {
                    "landmark": (f"tensile_landmark_{variant}", "tensile_landmark_aligned"),
                    "pointwise": (f"tensile_pointwise_{variant}", "tensile_with_individuals" if state["show_individuals"] else "tensile_averages_only"),
                    "comparison": (f"tensile_comparison_{variant}", "tensile_comparison"),
                    "representative": (f"tensile_representative_{variant}", "tensile_representative"),
                    "work_hardening": (f"work_hardening_{variant}", "work_hardening_with_individuals" if state["show_individuals"] else "work_hardening_averages_only"),
                    "work_hardening_landmark": (f"work_hardening_landmark_{variant}", "work_hardening_landmark"),
                    **{kind: (f'{kind}_{variant}', kind) for kind in (*PROPERTY_FAMILIES, GROUP_FAMILY)},
                }
                titles = spec.get("titles", {})
                title = next((titles[k] for k in title_keys.get(family, ()) if k in titles),
                             dict((value, label) for label, value in FAMILIES)[family])
                title = spec.get("workbench_titles", {}).get(family) or title
                common = dict(out_path=Path("preview.png"), color_map=self.color_map(state, spec),
                              show_individual=state["show_individuals"], xlim=xlim, ylim=ylim,
                              title=title, name_overrides=spec.get('name_overrides', {}), preview=True)
                wh = {**self._wh_settings(state, spec),
                      'specimen_labels': {g: e.scatter_specimen_labels(rows) for g, rows in shape_records.items()}}
                if family == GROUP_FAMILY:
                    fig = render_group_properties(e, records, state,
                        fit_fractions=spec.get('landmark_yield_fit_fractions', e.LANDMARK_YIELD_FIT_FRACTIONS),
                        **common)
                elif family in PROPERTY_FAMILIES:
                    fig = e.render_strength_elongation_plot(records, family=family,
                        error_bars=state.get('property_error_bars', True),
                        fit_fractions=spec.get('landmark_yield_fit_fractions', e.LANDMARK_YIELD_FIT_FRACTIONS),
                        **common)
                elif family in ("landmark", "pointwise", "comparison"):
                    fig = e.render_average_plot(models, shape_records, family=family,
                        landmark_error_bars=state["landmark_error_bars"], **common)
                elif family == "representative":
                    fig = e.render_representative_tensile_plot(shape_records,
                        representative_overrides=spec.get("representative_overrides", {}), **common)
                elif family == "work_hardening":
                    fig = e.render_work_hardening_plot(curves, **common, **wh)
                elif family == "work_hardening_landmark":
                    fig = e.render_landmark_work_hardening_plot(models, curves, **common, **wh)
                else:
                    fig = self._compare_wh(models, curves, common, wh)
                if fig is None:
                    raise ValueError("No valid curves for this preview. " + stream.getvalue())
                # Vector previews remain sharp at gallery and enlarged sizes.
                # PNG exports retain the independent 600-DPI setting.
                buffer = io.BytesIO()
                fig.savefig(buffer, format="svg")
                source_rows = [{"group": g, "sample": r["sample"], "file": r["source_file"],
                                "sha256_at_load": r["source_sha256"]} for g, rows in records.items() for r in rows]
                return {"figure": fig, "svg": buffer.getvalue(), "state": deepcopy(state),
                        "graph_spec": spec, "sources": source_rows, "log": stream.getvalue(),
                        "seconds": perf_counter() - start, "n_samples": len(source_rows),
                        "export_records": records if family in (*PROPERTY_FAMILIES, GROUP_FAMILY) else shape_records,
                        "export_models": models}
            finally:
                # Avoid duplicate notebook displays and accumulating open figures.
                # Figure objects remain usable for an explicit later PNG export.
                for number in set(e.plt.get_fignums()) - before:
                    e.plt.close(number)

    def _compare_wh(self, models, curves, common, wh):
        e = self.engine
        first = e.render_work_hardening_plot(curves, **common, **wh)
        second = e.render_landmark_work_hardening_plot(models, curves,
            **{**common, "show_individual": False}, **wh)
        if first is None or second is None:
            raise ValueError("WH comparison needs valid curves from both methods.")
        ax = first.axes[0]
        for line in ax.lines:
            if not line.get_label().startswith("_"):
                line.set_label(line.get_label() + " · original")
        for line in second.axes[0].lines:
            if not line.get_label().startswith("_"):
                ax.plot(line.get_xdata(), line.get_ydata(), color=line.get_color(),
                        lw=line.get_linewidth(), ls="--", label=line.get_label() + " · landmark")
        if common["xlim"] is None:
            ax.set_xlim(min(ax.get_xlim()[0], second.axes[0].get_xlim()[0]),
                        max(ax.get_xlim()[1], second.axes[0].get_xlim()[1]))
        if common["ylim"] is None:
            ax.set_ylim(min(ax.get_ylim()[0], second.axes[0].get_ylim()[0]),
                        max(ax.get_ylim()[1], second.axes[0].get_ylim()[1]))
        ax.legend()
        print('[PLOT INFO] Solid: mean specimen WH; dashed: derivative of landmark mean. '
              'Faint lines, if enabled: original specimen WH.')
        first.tight_layout()
        first._export_wh = getattr(first, '_export_wh', []) + getattr(second, '_export_wh', [])
        return first

    def export(self, results, include_tables=False):
        """Explicit multi-plot snapshot; no original batch directories touched."""
        if not results:
            raise ValueError("There are no valid previews to export.")
        if any(r.get('fit_signature') != self.fit_signature() for r in results):
            raise ValueError('Specimen fit or EL settings changed. Update plots before exporting.')
        if any(r.get('selection_signature') != self.selection_signature() for r in results):
            raise ValueError('Specimen inclusion changed. Update plots before exporting.')
        result = results[0]
        graph = self.engine.safe_filename(result["graph_spec"]["name"])
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:6]
        destination = self.output_root() / graph / stamp
        destination.mkdir(parents=True, exist_ok=False)
        state = result["state"]
        metadata = {
            'specimen_fit_policy': result['specimen_fit_policy'],
            "format": "tensile-workbench-v18", "created": datetime.now().astimezone().isoformat(),
            "settings": state, "graph_definition": result["graph_spec"],
            "effective_wh_settings": self._wh_settings(state, result["graph_spec"]),
            "sources": result["sources"], "python": platform.python_version(),
            "engine": self.engine_path.name,
            "engine_sha256_at_load": self.engine_sha256,
            "project": self.project,
            "views": [r["state"] for r in results],
            "note": "Interactive preview snapshot. No batch outputs were regenerated. Source hashes describe data cached at load time.",
        }
        try:
            for view in results:
                view_state = view["state"]
                variant = "with_individuals" if view_state["show_individuals"] else "without_individuals"
                family_number = {"pointwise": "01", "landmark": "02", "comparison": "03", "representative": "04", "work_hardening": "05", "work_hardening_landmark": "06", "work_hardening_comparison": "07", "ys_vs_el": "08", "uts_vs_el": "09", GROUP_FAMILY: "10"}[view_state["family"]]
                plot = destination / f"{graph}_{family_number}_{view_state['family']}_{variant}.png"
                view["figure"].savefig(plot, dpi=self.engine.PLOT_DPI)
            (destination / "settings.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            (destination / "calculation_log.txt").write_text("\n\n".join(r["log"] for r in results), encoding="utf-8")
            if include_tables:
                self._export_tables(destination, results)
        except Exception as error:
            raise RuntimeError(f"Export incomplete in {destination}: {error}") from error
        return destination

    def _export_tables(self, destination, results):
        """Consolidated properties plus only the datasets in exported views."""
        result = results[0]
        state, spec = result['state'], result['graph_spec']
        graph = self.engine.safe_filename(spec['name'])
        export_results(self.property_tables(state, spec), destination / f'{graph}_results.xlsx',
                       {'graph': spec, 'views': [r['state'] for r in results],
                        'specimen_selection': self.selection_provenance(state, spec),
                        'fit_policy': self.fit_provenance(state), 'engine_sha256': self.engine_sha256})
        export_curves(results, self.engine, destination / f'{graph}_curves.xlsx')


class TensileWorkbench:
    """Graph editor and multi-plot board. Definitions autosave independently of previews."""

    def __init__(self, project_dir=None, project_path=None, data_dir=None, output_dir=None):
        import ipywidgets as w
        self.w = w
        self.project_dir = Path(project_dir or Path(__file__).parent).expanduser().resolve()
        self.store = ProjectStore(project_path or self.project_dir / "tensile_workbench.project.json",
                                  self.project_dir / "tensile_workbench_defaults.json")
        self.session = PreviewSession(self.project_dir, self.store.data, data_dir, output_dir)
        upgraded = migrate_specimen_selections(migrate_group_gauges(
            upgrade_legacy_demo_graph(self.store.data, self.session.data_dir, self.session.sample_data_dir)))
        if upgraded != self.store.data:
            self.store.save(upgraded)
            self.session.set_project(self.store.data)
        self._paused, self._busy = True, False
        self._results, self._signature = [], None
        self._pending_delete = None
        self.controls, self.axes, self.title_inputs = {}, {}, {}
        self.graph = w.Dropdown(description="Graph:", layout=w.Layout(width="98%"))
        self.name = w.Text(description="Name:", continuous_update=False, layout=w.Layout(width="98%"))
        self.new_button = w.Button(description="New graph")
        self.duplicate_button = w.Button(description="Duplicate graph")
        self.delete_button = w.Button(description='Delete graph', button_style='danger')
        self.undo_delete_button = w.Button(description='Undo delete', disabled=True)
        self.delete_message = w.HTML()
        self.confirm_delete_button = w.Button(description='Confirm delete', button_style='danger')
        self.cancel_delete_button = w.Button(description='Cancel')
        self.delete_confirmation = w.VBox([self.delete_message,
            self._row([self.confirm_delete_button, self.cancel_delete_button])], layout=w.Layout(display='none'))
        self.saved_button = w.Button(description="Reload saved graphs", layout=w.Layout(width='auto'))
        self.save_status = w.HTML()
        self.status = w.HTML()
        self.controls["groups"] = w.SelectMultiple(description="Groups:", rows=6, layout=w.Layout(width="98%"))
        self.group_picker = GroupCheckboxes(w, self.controls["groups"], self.store.data.get('display_names', {}))
        self.sample_data_toggle = w.Checkbox(value=self.session.show_sample_data, description='Show sample data',
            indent=False, tooltip='Show or hide bundled synthetic groups alongside your own data',
            layout=w.Layout(width='auto'))
        self.sample_data_note = w.HTML()
        self.group_picker.ui.children = (self.group_picker.ui.children[0],
            self._row([self.sample_data_toggle, self.sample_data_note]), *self.group_picker.ui.children[1:])
        self.family_boxes = {family: w.Checkbox(description=label, indent=False, layout=w.Layout(width="auto")) for label, family in FAMILIES}
        self._check("show_individuals", "Show individual specimens")
        self._check("show_both_versions", "Display both with/without-individuals versions")
        self._check("landmark_error_bars", "Landmark ±1 SD bars")
        self._check("property_error_bars", "Group mean ±1 SD bars · strength–EL plots")
        self._check('properties_by_group_error_bars', 'Group mean ±1 SD bars')
        self.controls['properties_by_group_line_style'] = w.Dropdown(
            description='Connecting lines:', options=[('Straight / solid', 'solid'), ('Dash', 'dash'),
                                                       ('Dot', 'dot'), ('None · markers only', 'none')],
            value='solid', style={'description_width': 'initial'}, layout=w.Layout(width='330px'))
        for key, label in (('ys', 'YS colour'), ('uts', 'UTS colour'), ('el', 'EL colour')):
            name = f'properties_by_group_{key}_color'
            self.controls[name] = w.ColorPicker(description=label, value=GROUP_DEFAULTS[name])
        self._group_order = []
        self._group_labels, self.group_label_fields = {}, {}
        self.group_labels_box = w.VBox(layout=w.Layout(width='100%'))
        self.group_order_select = w.Select(options=[], rows=6, layout=w.Layout(width='98%'))
        self.group_order_up = w.Button(description='Move left ↑', layout=w.Layout(width='auto'))
        self.group_order_down = w.Button(description='Move right ↓', layout=w.Layout(width='auto'))
        self.group_order_up.on_click(lambda _: self._move_group_order(-1))
        self.group_order_down.on_click(lambda _: self._move_group_order(1))
        self.group_order_select.observe(lambda _: self._sync_order_buttons(), names='value')
        self._check("live_update", "Live preview (may be very slow)")
        self.controls["live_update"].tooltip = "Automatically update plots when settings change, including on slider release."
        self._check("export_tables", "Include Excel tables when exporting")
        self.controls["columns"] = w.Dropdown(options=[("Stacked", 1), ("Up to 2 columns", 2), ("Up to 3 columns", 3), ("Automatic grid", 0)],
                                              description="Layout:", layout=w.Layout(width="270px"))
        self.controls["plot_width"] = w.IntSlider(value=640, min=320, max=1600, step=40,
            description="Plot width (px)", continuous_update=False, style={"description_width": "initial"}, layout=w.Layout(width="360px"))
        self.controls["renderer"] = w.Dropdown(options=[("Static plots", "static"), ("Interactive Plotly", "plotly")],
            value="static", description="Plot display:", style={"description_width": "initial"}, layout=w.Layout(width="350px"))
        sliders = (
            ("landmark_points", "Landmark points/stage", 50, 2000, 50, True),
            ("pointwise_points", "Pointwise tensile points", 100, 2000, 100, True),
            ("wh_points", "WH grid points", 100, 4000, 100, True),
            ("modulus_gpa", "WH modulus (GPa)", 20, 250, 1, False),
            ("min_plastic_strain", "Minimum plastic strain (%)", 0, 2, .01, False),
            ("despike_window", "Hampel window (pp)", .01, 3, .01, False),
            ("despike_sigma", "Hampel robust SD cutoff", 1, 10, .25, False),
            ("median_window", "Median window (pp)", .01, 3, .01, False),
            ("smooth_window", "Polynomial window (pp)", .01, 3, .01, False),
            ("tail_window", "Tail fit window (pp)", .1, 10, .1, False),
            ("tail_setback", "Tail setback (pp)", 0, 2, .01, False),
        )
        for key, label, low, high, step, integer in sliders:
            cls = w.IntSlider if integer else w.FloatSlider
            kwargs = {} if integer else {"readout_format": ".2f"}
            self.controls[key] = cls(description=label, min=low, max=high, step=step, value=low,
                continuous_update=False, style={"description_width": "initial"}, layout=w.Layout(width="98%"), **kwargs)
        for key, label in (("respect_modulus_overrides", "Respect per-group modulus overrides"),
                           ("despike", "Hampel despiking"), ("median", "Rolling median"),
                           ("smooth", "Local-polynomial derivative"), ("tail_enabled", "Pointwise fitted tail (tensile only)")):
            self._check(key, label)
        self.controls["poly_order"] = w.Dropdown(options=[1,2,3,4,5], description="Order:")
        for key, title in (("tensile_xlim", "Tensile strain (%)"), ("tensile_ylim", "Tensile stress (MPa)"),
                           ("wh_xlim", "WH plastic strain (%)"), ("wh_ylim", "WH rate (MPa)"),
                           ("ys_vs_el_xlim", "Elongation at failure (%)"), ("ys_vs_el_ylim", "0.2% YS (MPa)"),
                           ("uts_vs_el_xlim", "Elongation at failure (%)"), ("uts_vs_el_ylim", "UTS (MPa)"),
                           ('properties_by_group_ylim', 'Left axis · strength (MPa)'),
                           ('properties_by_group_el_ylim', 'Right axis · elongation at failure (%)')):
            auto = w.Checkbox(description="Automatic", indent=False)
            lo, hi = w.FloatText(description="Min:", continuous_update=False), w.FloatText(description="Max:", continuous_update=False)
            row = w.VBox([w.HTML("<b>" + title + "</b>"), auto, self._row([lo, hi])])
            self.axes[key] = (auto, lo, hi, row)
        for label, family in FAMILIES:
            self.title_inputs[family] = w.Text(description=label, continuous_update=False,
                style={"description_width": "initial"}, layout=w.Layout(width="98%"))
        self.override_group = w.Dropdown(description="Group:", layout=w.Layout(width="98%"))
        self.controls['color_palette'] = w.Dropdown(description='Palette:', options=PALETTE_OPTIONS,
            value=DEFAULT_PALETTE, layout=w.Layout(width='98%'))
        self.palette_swatches = w.HTML()
        self.override_name = w.Text(description="Legend label:", continuous_update=False,
                                    style={"description_width": "initial"}, layout=w.Layout(width="98%"))
        self.override_color_enabled = w.Checkbox(description='Override colour for this graph', indent=False)
        self.override_color = w.ColorPicker(description='Colour:', value='#1f77b4', concise=False)
        self.override_e_enabled = w.Checkbox(description="Use a group-specific WH modulus", indent=False)
        self.override_e = w.BoundedFloatText(value=115, min=1, max=1000, description="E (GPa):")
        self.override_rep = w.Dropdown(description="Representative:", style={"description_width": "initial"}, layout=w.Layout(width="98%"))
        self.override_button = w.Button(description="Apply group overrides")
        self._gauge_rows, self._gauge_graph_id, self._gauge_sync = {}, None, False
        self.gauge_grid = w.GridBox(layout=w.Layout(
            grid_template_columns='minmax(140px, 1fr) 140px 110px', grid_gap='2px 12px',
            align_items='center', width='100%', min_width='420px', max_width='700px'))
        self.gauge_message = w.HTML()
        from tensile_inspector import gauge_model_help
        self.gauge_panel = w.Accordion(children=[w.VBox([
            w.Box([self.gauge_grid], layout=w.Layout(width='100%', overflow='auto')),
            self.gauge_message,
            w.HTML('Changes save automatically. Enter a target, then tick Reconstruct to apply it to that group. '
                   'Each specimen uses its own AVE Strain 1 gauge length. Leave Reconstruct unticked to preview the '
                   'overlay in the specimen inspector. Longer targets are allowed with a model warning; '
                   'all reconstructed results remain derived estimates.'),
            w.HTML(gauge_model_help(expanded=True))])], selected_index=None)
        self.gauge_panel.set_title(0, 'Gauge reconstruction · per sample group')
        self.update_button = w.Button(description="Update plots", button_style="primary")
        self.reload_button = w.Button(description="Reload data")
        self.export_button = w.Button(description="Export plot set", tooltip="Export all generated plots in this set, including when one is enlarged.", disabled=True)
        self.viewer = DualPlotView(w, self.controls["columns"], self.controls["plot_width"], self.controls["renderer"])
        self.board = self.viewer.board
        self.details = w.Textarea(disabled=True, layout=w.Layout(width="98%", height="180px"))
        self.tables = PropertyTablesView(w, on_selection=self._specimen_changed,
                                        inspect_loader=self._inspect_specimen, on_fit_apply=self._apply_specimen_fit,
                                        on_threshold=self._change_fit_threshold, on_failure_apply=self._apply_specimen_failure,
                                        group_loader=lambda group: self.session.group_review_records(group, self._current()['definition']))
        self.fit_warning = w.HTML(layout=w.Layout(width='100%'))
        self.review_fits = w.Button(description='Review specimens', layout=w.Layout(width='145px', flex='0 0 145px'), disabled=True)
        self.review_fits.on_click(self._review_fits)
        self.fit_review_bar = w.VBox([
            self._row([self.tables.threshold, self.tables.threshold_status]),
            w.HBox([self.fit_warning, self.review_fits], layout=w.Layout(width='100%'))
        ], layout=w.Layout(width='100%'))
        self.tables_update_button = w.Button(description='Update tables')
        self.tables_reload_button = w.Button(description='Reload data',
            tooltip='Reread CSVs and summary files, refresh tables, and clear old plots. No page refresh needed.')
        self.table_export_button = w.Button(description='Export tables only', disabled=True)
        self.properties_panel = w.Accordion(children=[w.VBox([
            self._row([self.tables_reload_button, self.tables_update_button, self.table_export_button]), self.tables.ui
        ])], selected_index=None, layout=w.Layout(width='100%'))
        self.properties_panel.set_title(0, 'Specimen properties · tables and calculation inspector')
        general = w.Accordion(children=[w.VBox([self.controls['color_palette'], self.palette_swatches,
                             self.override_group, self.override_name,
                             self.override_color_enabled, self.override_color, self.override_button])], selected_index=None)
        general.set_title(0, "Labels and colours · this graph, all plot types")
        self.plot_settings = {}
        self.plot_selectors = {}
        for label, family in FAMILIES:
            self.title_inputs[family].description = "Title:"
            local = [self.title_inputs[family]]
            wh = family.startswith("work_hardening")
            property_plot = family in PROPERTY_FAMILIES
            axes_prefix = family if property_plot else ("wh" if wh else "tensile")
            axis_keys = ([GROUP_FAMILY + '_ylim', GROUP_FAMILY + '_el_ylim'] if family == GROUP_FAMILY
                         else [axes_prefix + suffix for suffix in ('_xlim', '_ylim')])
            axes = w.Accordion(children=[w.VBox([self.axes[key][3] for key in axis_keys])], selected_index=None)
            axes.set_title(0, 'Axes · this plot' if property_plot or family == GROUP_FAMILY else "Axes · linked across " + ("WH plots" if wh else "tensile plots"))
            local.append(axes)
            if family == GROUP_FAMILY:
                label_settings = w.Accordion(children=[w.VBox([
                    w.HTML('Short x-axis labels for this plot only. Leave blank to use the usual display name. '
                           'Line breaks are allowed. Other plots and tables keep their existing names.'),
                    self.group_labels_box])], selected_index=None)
                label_settings.set_title(0, 'X-axis labels · this plot only')
                local += [w.HTML('<b>Sample order</b> · top to bottom = left to right. Select a group, then move it.'),
                          self.group_order_select, self._row([self.group_order_up, self.group_order_down]),
                          self.controls['properties_by_group_line_style'], label_settings,
                          self.controls['properties_by_group_error_bars'],
                          self._row([self.controls[f'properties_by_group_{key}_color'] for key in ('ys', 'uts', 'el')]),
                          w.HTML('Lines connect group means. YS and UTS use the left axis; EL uses the right. '
                                 'Each property uses its available included specimens. EL follows the group’s gauge reconstruction setting. '
                                 'Show individuals adds faint specimen points. Colours here identify properties, not groups.')]
            if property_plot:
                local += [self.controls['property_error_bars'],
                          w.HTML('EL uses Calc (CSV-detected fracture) or Reconstruct when gauge reconstruction is enabled. '
                                 'Group means use calculated specimen properties, not an average curve. '
                                 'Show individuals adds specimen points; SD bars show specimen scatter, not confidence intervals.')]
            if family in ("landmark", "comparison", "work_hardening_landmark", "work_hardening_comparison"):
                local.append(self.controls["landmark_points"])
            if family in ("landmark", "comparison"):
                local.append(self.controls["landmark_error_bars"])
            if family in ("pointwise", "comparison"):
                local.append(self.controls["pointwise_points"])
                tail = w.Accordion(children=[self._controls_box("tail_enabled", "tail_window", "tail_setback")], selected_index=None)
                tail.set_title(0, "Pointwise fitted tail")
                local.append(tail)
            if wh:
                local += [self.controls[k] for k in ("wh_points", "modulus_gpa", "respect_modulus_overrides", "min_plastic_strain")]
                filters = w.Accordion(children=[w.VBox([
                    w.HTML("Filter windows are full widths in plastic-strain percentage points. WH settings are linked across the three WH views."),
                    *[self.controls[k] for k in ("despike", "despike_window", "despike_sigma", "median", "median_window", "smooth", "smooth_window", "poly_order")]
                ])], selected_index=None)
                filters.set_title(0, "WH filters")
                modulus = w.Accordion(children=[w.VBox([self.override_group, self.override_e_enabled, self.override_e, self.override_button])], selected_index=None)
                modulus.set_title(0, "Per-group WH modulus")
                local += [filters, modulus]
            if family == "representative":
                local += [self.override_group, self.override_rep, self.override_button]
            settings = w.Accordion(children=[w.VBox(local)], selected_index=None)
            settings.set_title(0, "Settings")
            self.plot_settings[family] = settings
            self.plot_selectors[family] = w.VBox([self.family_boxes[family], settings], layout=w.Layout(width="100%", min_width="0"))
        self.plot_options = w.VBox(list(self.plot_selectors.values()), layout=w.Layout(width="100%", max_width="980px", gap="8px"))
        log = w.Accordion(children=[self.details], selected_index=None)
        log.set_title(0, "Calculation details and warnings")
        self.ui = w.VBox([
            w.HTML("<h2>Analysis workspace</h2><p>Choose a graph and its sample groups. Changes save automatically; export when you are ready.</p>"),
            self.graph, self._row([self.duplicate_button, self.delete_button, self.undo_delete_button, self.saved_button]),
            self.delete_confirmation, self.name,
            self.save_status, self.group_picker.ui,
            w.HTML("Tick the exact sample groups to include, regardless of their naming format."),
            self.gauge_panel,
            self.fit_review_bar, self.properties_panel,
            w.HTML("<h3>Plot views</h3>"), self.controls["renderer"],
            self._row([self.controls["show_individuals"], self.controls["show_both_versions"]]),
            w.HTML("Choose plots below. Each selector has its own settings. Shared averaging parameters and axis ranges stay linked between related plots."),
            self.plot_options,
            self._row([self.update_button, self.reload_button, self.controls["live_update"]]),
            self.status, general, self.viewer.ui,
            self._row([self.export_button, self.controls["export_tables"]]), log,
        ], layout=w.Layout(width="100%"))
        self._refresh_graph_options()
        self._apply_graph(self.store.data["selected_graph"])
        self.sample_data_toggle.observe(self._sample_data_changed, names='value')
        self.graph.observe(self._graph_changed, names="value")
        self.name.observe(self._changed, names="value")
        for key, widget in self.controls.items():
            widget.observe(self._palette_changed if key == 'color_palette' else
                           self._view_changed if key in VIEW_ONLY_SETTINGS else self._changed, names="value")
        for widget in list(self.family_boxes.values()) + list(self.title_inputs.values()):
            widget.observe(self._changed, names="value")
        for auto, lo, hi, _ in self.axes.values():
            for widget in (auto, lo, hi):
                widget.observe(self._changed, names="value")
        self.new_button.on_click(lambda _: self.new_graph())
        self.duplicate_button.on_click(lambda _: self.new_graph(duplicate=True))
        self.delete_button.on_click(self._ask_delete_graph)
        self.confirm_delete_button.on_click(self._confirm_delete_graph)
        self.cancel_delete_button.on_click(self._cancel_delete_graph)
        self.undo_delete_button.on_click(self._undo_delete_graph)
        self.saved_button.on_click(self.reload_definitions)
        self.override_group.observe(self._load_overrides, names="value")
        self.override_button.on_click(self._apply_overrides)
        self.update_button.on_click(lambda _: self.update())
        self.reload_button.on_click(self._reload_data)
        self.tables_reload_button.on_click(lambda _: self._reload_data(plots=False))
        self.export_button.on_click(self._export)
        self.tables_update_button.on_click(self._update_tables)
        self.table_export_button.on_click(self._export_properties)
        self._paused = False
        self._show_saved()
        if not self.session.files:
            self.tables.clear('No tensile sample groups found in the selected data folder.')
            self.status.value = 'Add tensile CSV files in sample-group subfolders, then click Reload data, or choose another location under Folders.'
            return
        self._refresh_properties()
        if self.controls["live_update"].value:
            self.update()
        else:
            self.status.value = "Saved definitions restored. Click <b>Update plots</b> when ready."

    def _row(self, children):
        return self.w.HBox(children, layout=self.w.Layout(flex_flow="row wrap", gap="6px"))

    def _check(self, key, label):
        self.controls[key] = self.w.Checkbox(description=label, indent=False, layout=self.w.Layout(width="auto"))

    def _controls_box(self, *keys):
        return self.w.VBox([self.controls[k] for k in keys])

    def _index(self, ident=None):
        ident = ident or self.graph.value
        return next(i for i, graph in enumerate(self.store.data["graphs"]) if graph["id"] == ident)

    def _current(self):
        return self.store.data["graphs"][self._index()]

    def _refresh_graph_options(self):
        old, self._paused = self._paused, True
        try:
            self.graph.options = graph_menu_options(self.store.data['graphs'])
            self.graph.value = self.store.data['selected_graph']
        finally:
            self._paused = old

    def _show_saved(self):
        detail = 'Revision ' + str(self.store.data['revision']) + ' · ' + self.store.path.name
        self.save_status.value = '<span title="' + escape(detail, quote=True) + '">✓ Changes saved automatically</span>'
        deleted = self.store.data.get('deleted_graphs', [])
        self.undo_delete_button.disabled = not deleted
        self.undo_delete_button.tooltip = ('Restore ' + deleted[-1]['graph']['name']) if deleted else 'No deleted graphs to restore'

    def state(self):
        state = {key: control.value for key, control in self.controls.items()}
        state["groups"] = list(state["groups"])
        state['properties_by_group_order'] = list(self._group_order)
        state['properties_by_group_labels'] = dict(self._group_labels)
        state["families"] = [family for family, box in self.family_boxes.items() if box.value]
        for key, (auto, lo, hi, _) in self.axes.items():
            state[key] = None if auto.value else [lo.value, hi.value]
        return state

    def _apply_graph(self, ident):
        self._cancel_delete_graph()
        old, self._paused = self._paused, True
        try:
            self.graph.value = ident
            graph = self._current()
            state = graph["settings"]
            self.name.value = graph["name"]
            # Preserve missing groups rather than silently dropping them on save.
            choices = sorted(set(self.session.files) | set(self.session.visible_groups(state["groups"])))
            def group_label(group):
                label = (group[len(SAMPLE_GROUP_PREFIX):].removeprefix('Demo_') + ' (sample)'
                         if group.startswith(SAMPLE_GROUP_PREFIX) else group)
                return label if group in self.session.files else label + ' (unavailable)'
            self.controls["groups"].options = [(group_label(g), g) for g in choices]
            for key, control in self.controls.items():
                value = state.get(key, {"color_palette": DEFAULT_PALETTE, "export_tables": False, "live_update": False, "plot_width": 640, "renderer": "static", **PROPERTY_DEFAULTS, **GROUP_DEFAULTS}.get(key, control.value))
                if key == "groups":
                    value = tuple(self.session.visible_groups(value))
                if isinstance(control, (self.w.IntSlider, self.w.FloatSlider)):
                    control.min = min(control.min, value)
                    control.max = max(control.max, value)
                control.value = value
            for family, box in self.family_boxes.items():
                box.value = family in state["families"]
            self._group_order = list(state.get('properties_by_group_order', []))
            self._group_labels = dict(state.get('properties_by_group_labels', {}))
            self._sync_group_order(force_labels=True)
            for key, (auto, lo, hi, _) in self.axes.items():
                pair = state.get(key)
                auto.value = pair is None
                lo.value, hi.value = pair or AXIS_DEFAULTS[key]
            legacy = graph["definition"].get("titles", {})
            title_keys = {"landmark": "tensile_landmark_aligned", "pointwise": "tensile_averages_only", "comparison": "tensile_comparison", "representative": "tensile_representative", "work_hardening": "work_hardening_averages_only", "work_hardening_landmark": "work_hardening_landmark"}
            for family, control in self.title_inputs.items():
                control.value = graph["definition"].get("workbench_titles", {}).get(family, legacy.get(title_keys.get(family), ""))
            self.override_group.options = self.session.visible_groups(state["groups"])
            self._sync_gauge_rows(force=True)
            self._sample_data_note()
            self._load_overrides()
            self._sync_disabled()
            self._results, self._signature = [], None
            self.viewer.clear()
            self.tables.clear()
            self.table_export_button.disabled = True
            self.export_button.disabled = True
        finally:
            self._paused = old

    def _sync_disabled(self):
        self.palette_swatches.value = palette_preview(self.controls['color_palette'].value,
            self.session.engine.plt.rcParams['axes.prop_cycle'].by_key()['color'])
        for auto, lo, hi, _ in self.axes.values():
            lo.disabled = hi.disabled = auto.value
        active_wh = any(box.value and family.startswith("work_hardening") for family, box in self.family_boxes.items())
        for parent, children in (("despike", ("despike_window", "despike_sigma")), ("median", ("median_window",)), ("smooth", ("smooth_window", "poly_order"))):
            self.controls[parent].disabled = not active_wh
            for key in children:
                self.controls[key].disabled = not active_wh or not self.controls[parent].value
        self.controls["show_individuals"].disabled = self.controls["show_both_versions"].value
        self.viewer.apply_layout()
        for family, settings in self.plot_settings.items():
            settings.layout.display = "" if self.family_boxes[family].value else "none"

    def _sync_order_buttons(self):
        options = list(self.group_order_select.options)
        value = self.group_order_select.value
        index = options.index(value) if value in options else -1
        self.group_order_up.disabled = index <= 0
        self.group_order_down.disabled = index < 0 or index >= len(options) - 1

    def _sync_group_order(self, *, force_labels=False):
        groups = list(self.controls['groups'].value)
        self._group_order += [g for g in groups if g not in self._group_order]
        selected = self.group_order_select.value
        self.group_order_select.options = ordered_groups(groups, self._group_order)
        if selected in self.group_order_select.options:
            self.group_order_select.value = selected
        self._sync_order_buttons()
        self._sync_group_labels(force=force_labels)

    def _sync_group_labels(self, *, force=False):
        groups = list(self.group_order_select.options)
        if not force and groups == list(self.group_label_fields):
            return
        old_rows = self.group_labels_box.children
        self.group_labels_box.children = ()
        for row in old_rows:
            for child in row.children:
                child.close()
            row.close()
        self.group_label_fields = {}
        rows = []
        for group in groups:
            field = self.w.Textarea(value=self._group_labels.get(group, ''), rows=2,
                placeholder='Automatic display name', continuous_update=False,
                layout=self.w.Layout(width='70%', min_width='160px'))
            field.observe(lambda change, group=group: self._group_label_changed(group, change['new']), names='value')
            self.group_label_fields[group] = field
            name = self.w.HTML(escape(group), layout=self.w.Layout(width='28%', min_width='100px'))
            rows.append(self._row([name, field]))
        self.group_labels_box.children = tuple(rows)

    def _group_label_changed(self, group, label):
        if self._paused:
            return
        if label.strip():
            self._group_labels[group] = label.strip()
        else:
            self._group_labels.pop(group, None)
        self._changed()

    def _move_group_order(self, direction):
        visible = list(self.group_order_select.options)
        selected = self.group_order_select.value
        if selected not in visible:
            return
        index = visible.index(selected)
        other = index + direction
        if not 0 <= other < len(visible):
            return
        a, b = self._group_order.index(selected), self._group_order.index(visible[other])
        self._group_order[a], self._group_order[b] = self._group_order[b], self._group_order[a]
        self._sync_group_order()
        self._changed()

    def save_current(self):
        """Validate then autosave; never discard a conflicting external edit."""
        try:
            state = self.state()
            check = {**state, "groups": state["groups"] or ["draft"], "family": state["families"][0] if state["families"] else "landmark"}
            self.session._validate(check)
            # Preserve legacy gauge choices before replacing settings with the
            # current controls (which no longer contain graph-wide gauge fields).
            project = migrate_group_gauges(self.store.data)
            graph = project["graphs"][self._index()]
            graph["name"] = self.name.value.strip()
            # Hiding samples is not a graph edit. Keep their previous selections
            # while saving changes to the visible research groups/settings.
            hidden = [g for g in graph['settings']['groups'] if self.session.hidden_sample_group(g)]
            if hidden:
                previous_order = graph['settings']['groups']
                selected = set(state['groups']) | set(hidden)
                groups = [g for g in previous_order if g in selected]
                groups += [g for g in state['groups'] if g not in groups]
                graph["settings"] = {**state, 'groups': groups}
            else:
                graph["settings"] = state
            graph["definition"]["name"] = graph["name"]
            graph["definition"]["workbench_titles"] = {family: field.value.strip() for family, field in self.title_inputs.items()}
            project["selected_graph"] = graph["id"]
            if project != self.store.data:
                self.store.save(project)
                self.session.set_project(self.store.data)
                old, self._paused = self._paused, True
                try:
                    self._refresh_graph_options()
                finally:
                    self._paused = old
            self._show_saved()
            if tuple(self.override_group.options) != tuple(state["groups"]):
                self.override_group.options = state["groups"]
            self._sync_gauge_rows()
            return True
        except Exception as error:
            self.save_status.value = "<b>Not saved:</b> " + escape(str(error))
            self.export_button.disabled = True
            return False

    def _changed(self, _=None):
        if self._paused:
            return
        self._sync_group_order()
        self._cancel_delete_graph()
        self._sync_disabled()
        self.export_button.disabled = True
        if not self.save_current():
            return
        self._refresh_properties()
        if self.controls["live_update"].value:
            self.update(save=False)
        else:
            self.status.value = "Settings saved. Click <b>Update plots</b>; displayed plots may reflect previous settings."

    def _palette_changed(self, change):
        if self._paused:
            return
        self._changed(change)
        # Refresh the automatic colour without discarding any pending manual override.
        if self.override_group.value is not None and not self.override_color_enabled.value:
            from matplotlib.colors import to_hex
            colors = self.session.color_map(self.state(), {})
            self.override_color.value = to_hex(colors.get(self.override_group.value, '#1f77b4'))

    def _view_changed(self, change=None):
        """Layout, display width and export preferences do not invalidate curves."""
        if self._paused:
            return
        self.viewer.apply_layout()
        if not self.save_current():
            return
        for result in self._results:
            for key in VIEW_ONLY_SETTINGS:
                result["state"][key] = self.controls[key].value
        ready = bool(self._results) and self._signature == self._current_signature()
        self.export_button.disabled = not ready
        if change and change.get('owner') is self.controls['live_update'] and change['new'] and not ready:
            self.update(save=False)

    def _graph_changed(self, change):
        if self._paused:
            return
        if change['new'] == NEW_GRAPH_ACTION:
            # Restore a real graph before save_current/_index reads the selector.
            old, self._paused = self._paused, True
            try:
                self.graph.value = change['old']
            finally:
                self._paused = old
            self.new_graph()
            return
        try:
            project = deepcopy(self.store.data)
            project["selected_graph"] = change["new"]
            self.store.save(project)
            self.session.set_project(self.store.data)
            self._apply_graph(change["new"])
            self._show_saved()
            self._refresh_properties()
            if self.controls["live_update"].value:
                self.update(save=False)
            else:
                self.status.value = "Graph restored. Click <b>Update plots</b> when ready."
        except Exception as error:
            self._paused = True
            self.graph.value = change["old"]
            self._paused = False
            self.save_status.value = "<b>Could not switch:</b> " + escape(str(error))

    def new_graph(self, duplicate=False):
        if not self.save_current():
            return
        try:
            template = self._current() if duplicate else None
            self.store.add_graph(template)
            self.session.set_project(self.store.data)
            self._paused = True
            self._refresh_graph_options()
            self._apply_graph(self.store.data["selected_graph"])
            self._paused = False
            self._show_saved()
            self.status.value = "Graph created and saved. Choose groups and the plots to display."
            self._refresh_properties()
            if duplicate and self.controls["live_update"].value:
                self.update(save=False)
        except Exception as error:
            self._paused = False
            self.save_status.value = "<b>Could not create graph:</b> " + escape(str(error))

    def reload_definitions(self, _=None):
        try:
            self.store.reload()
            upgraded = migrate_specimen_selections(migrate_group_gauges(self.store.data))
            if upgraded != self.store.data:
                self.store.save(upgraded)
            self.session.set_project(self.store.data)
            self._paused = True
            self._refresh_graph_options()
            self._apply_graph(self.store.data["selected_graph"])
            self._paused = False
            self._show_saved()
            self._refresh_properties()
            if self.controls["live_update"].value:
                self.update(save=False)
        except Exception as error:
            self._paused = False
            self.save_status.value = "<b>Reload failed:</b> " + escape(str(error))

    def _ask_delete_graph(self, _=None):
        if not self.save_current():
            return
        self._pending_delete = self.graph.value
        self.delete_message.value = ('Delete graph <b>' + escape(self._current()['name'])
            + '</b>? Only its saved definition is removed. Data and exported files are untouched. '
              'You can restore it with Undo delete.')
        self.delete_confirmation.layout.display = ''

    def _cancel_delete_graph(self, _=None):
        self._pending_delete = None
        self.delete_confirmation.layout.display = 'none'

    def _after_graph_action(self, message):
        upgraded = migrate_specimen_selections(migrate_group_gauges(self.store.data))
        if upgraded != self.store.data:
            self.store.save(upgraded)
        self.session.set_project(self.store.data)
        self._refresh_graph_options()
        self._apply_graph(self.store.data['selected_graph'])
        self._show_saved()
        self._refresh_properties()
        if self.controls['live_update'].value:
            self.update(save=False)
        self.status.value = escape(message)

    def _confirm_delete_graph(self, _=None):
        ident = self._pending_delete
        if ident is None or ident != self.graph.value or not self.save_current():
            return
        try:
            name = self._current()['name']
            self.store.delete_graph(ident)
            self._after_graph_action(f'Deleted graph “{name}”. Undo delete can restore it; data and exports are unchanged.')
        except Exception as error:
            self.save_status.value = '<b>Could not delete graph:</b> ' + escape(str(error))

    def _undo_delete_graph(self, _=None):
        deleted = self.store.data.get('deleted_graphs', [])
        if not deleted:
            return
        # Widget hydration adds default fields on save. That is not a user edit
        # to the automatic empty draft and must not prevent its removal on Undo.
        untouched_draft = deleted[-1].get('replacement') == self._current()
        if not untouched_draft and not self.save_current():
            return
        try:
            self.store.undo_delete()
            self._after_graph_action('Deleted graph restored, including its specimen selections.')
        except Exception as error:
            self.save_status.value = '<b>Could not restore graph:</b> ' + escape(str(error))

    def _specimen_changed(self, ident, included, reason, scope='global', action='selection', mode=None):
        if self._paused:
            return
        if not self.save_current():
            self._refresh_properties()
            return
        try:
            # Never apply a stale browser row to a different selected group/graph.
            known = {r['specimen_id'] for group in self.state()['groups'] for r in self.session._load(group)}
            if ident not in known:
                raise ValueError('Specimen is no longer in this graph. Reload its tables.')
            project = deepcopy(self.store.data)
            spec = project['graphs'][self._index()]['definition']
            mode = mode if mode is not None else ('all' if included else 'exclude')
            validate_data_mode(mode)
            included = mode != 'exclude'
            overrides = spec.setdefault('specimen_inclusion_overrides', {})
            if action == 'inherit':
                overrides.pop(ident, None)
            elif scope == 'graph':
                overrides[ident] = {'included': included, 'mode': mode, 'reason': reason.strip()}
            else:
                # Normal Include changes are global. Existing explicit overrides
                # in other graphs remain deliberate exceptions.
                exclusions = project.setdefault('specimen_exclusions', {})
                modes = project.setdefault('specimen_data_modes', {})
                if mode in ('all', 'exclude'):
                    modes.pop(ident, None)
                else:
                    modes[ident] = {'mode': mode, 'reason': reason.strip()}
                if included:
                    exclusions.pop(ident, None)
                else:
                    exclusions[ident] = reason.strip()
                overrides.pop(ident, None)
            if project != self.store.data:
                self.store.save(project)
                self.session.set_project(self.store.data)
            self._show_saved()
            self._results, self._signature = [], None
            self.export_button.disabled = True
            self.viewer.clear('Specimen selection changed. Update plots to use the saved selection.')
            self._load_overrides()
            self._refresh_properties()
            if self.controls['live_update'].value:
                self.update(save=False)
            else:
                self.status.value = ('Specimen selection saved ' + ('for this graph.' if scope == 'graph' and action != 'inherit'
                    else 'globally; explicit graph overrides remain in effect.' if action != 'inherit'
                    else 'using the global default.') + ' Tables updated; click Update plots when ready.')
        except Exception as error:
            self.save_status.value = '<b>Specimen selection not saved:</b> ' + escape(str(error))
            self._refresh_properties()

    def _sync_gauge_rows(self, force=False):
        """Rebuild only on graph/group changes, not while a row is being edited."""
        graph, w = self._current(), self.w
        groups = self.session.visible_groups(graph['settings']['groups'])
        if not force and self._gauge_graph_id == graph['id'] and tuple(self._gauge_rows) == tuple(groups):
            return
        self._gauge_sync = True
        previous = self.gauge_grid.children
        try:
            cells = [w.HTML('<b>' + title + '</b>') for title in ('Sample group', 'Target (mm)', 'Reconstruct')]
            self._gauge_rows = {}
            self._gauge_graph_id = graph['id']
            for group in groups:
                policy = group_policy(graph['settings'], graph['definition'], group)
                label = (group[len(SAMPLE_GROUP_PREFIX):].removeprefix('Demo_') + ' (sample)'
                         if group.startswith(SAMPLE_GROUP_PREFIX) else group)
                if group not in self.session.files:
                    label += ' (unavailable)'
                target = w.BoundedFloatText(value=policy['target_gauge_mm'], min=0,
                    max=max(100000, policy['target_gauge_mm']), step=1, continuous_update=False,
                    tooltip=label + ': target gauge length in mm; 0 means unset',
                    layout=w.Layout(width='135px', margin='0'))
                enabled = w.Checkbox(value=policy['enabled'], indent=False,
                    tooltip=label + ': use reconstructed post-peak strain',
                    layout=w.Layout(width='auto', margin='0'))
                self._gauge_rows[group] = (target, enabled)
                cells.extend([w.HTML(escape(label), layout=w.Layout(margin='0')), target, enabled])
                for control in (target, enabled):
                    control.observe(lambda change, group=group, graph_id=graph['id']:
                                    self._gauge_row_changed(group, graph_id), names='value')
            if not groups:
                cells.append(w.HTML('Select sample groups above to set their target gauges.',
                                    layout=w.Layout(grid_column='1 / -1')))
            self.gauge_grid.children = tuple(cells)
            self.gauge_message.value = ''
        finally:
            self._gauge_sync = False
        for control in previous:
            control.close()

    def _gauge_row_changed(self, group, graph_id):
        if self._paused or self._gauge_sync or graph_id != self.graph.value or group not in self._gauge_rows:
            return
        target, enabled = self._gauge_rows[group]
        try:
            policy = validate_group_policy({'enabled': enabled.value, 'target_gauge_mm': target.value})
            if not self.save_current():
                raise ValueError('Graph settings could not be saved; gauge settings were not applied.')
            project = deepcopy(self.store.data)
            project['graphs'][self._index()]['definition'].setdefault('gauge_reconstruction', {})[group] = policy
            self.store.save(project)
            self.session.set_project(self.store.data)
            self._show_saved()
            self._changed()
            self.gauge_message.value = 'Saved · ' + escape(group) + ': ' + escape(
                group_basis_label(self._current()['settings'], self._current()['definition'], group))
        except Exception as error:
            # An invalid edit must not look applied while calculations still use
            # the previous saved policy. Restore that row without another event.
            policy = group_policy(self._current()['settings'], self._current()['definition'], group)
            self._gauge_sync = True
            try:
                target.value, enabled.value = policy['target_gauge_mm'], policy['enabled']
            finally:
                self._gauge_sync = False
            self.gauge_message.value = '<b>Not saved:</b> ' + escape(str(error))

    def _load_overrides(self, _=None):
        group = self.override_group.value
        if group is None:
            return
        spec = self._current()["definition"]
        self.override_name.value = spec.get("name_overrides", {}).get(group, self.store.data.get("display_names", {}).get(group, group))
        from matplotlib.colors import to_hex
        color = spec.get('color_overrides', {}).get(group)
        self.override_color_enabled.value = color is not None
        self.override_color.value = color or to_hex(self.session.color_map(self.state(), {}).get(group, '#1f77b4'))
        modulus = spec.get("youngs_modulus_overrides", {}).get(group)
        self.override_e_enabled.value = modulus is not None
        self.override_e.value = modulus/1000 if modulus is not None else self.controls["modulus_gpa"].value
        with redirect_stdout(io.StringIO()):
            rows = [r for r in self.session._load(group) if is_included(r, spec, self.store.data)] if group in self.session.files else []
        choices = [("Automatic: closest failure elongation", "")] + [(r["sample"], r["sample"]) for r in rows]
        saved = spec.get("representative_overrides", {}).get(group, "")
        if saved and saved not in [value for _, value in choices]:
            choices.append((saved + " (excluded/unavailable; automatic fallback)", saved))
        self.override_rep.options = choices
        self.override_rep.value = saved

    def _apply_overrides(self, _=None):
        if not self.save_current() or self.override_group.value is None:
            return
        try:
            project = deepcopy(self.store.data)
            spec = project["graphs"][self._index()]["definition"]
            group = self.override_group.value
            labels = spec.setdefault("name_overrides", {})
            if self.override_name.value.strip():
                labels[group] = self.override_name.value.strip()
            else:
                labels.pop(group, None)
            colors = spec.setdefault('color_overrides', {})
            if self.override_color_enabled.value:
                colors[group] = self.override_color.value
            else:
                colors.pop(group, None)
            modulus = spec.setdefault("youngs_modulus_overrides", {})
            if self.override_e_enabled.value:
                modulus[group] = self.override_e.value * 1000
            else:
                modulus.pop(group, None)
            representative = spec.setdefault("representative_overrides", {})
            if self.override_rep.value:
                representative[group] = self.override_rep.value
            else:
                representative.pop(group, None)
            self.store.save(project)
            self.session.set_project(self.store.data)
            self._show_saved()
            self._changed()
        except Exception as error:
            self.save_status.value = "<b>Override not saved:</b> " + escape(str(error))

    def _reload_data(self, _=None, *, plots=True):
        if self._busy or not self.save_current():
            return
        self.reload_button.disabled = self.tables_reload_button.disabled = True
        self.export_button.disabled = True
        self.table_export_button.disabled = True
        self._results, self._signature = [], None
        self.viewer.clear('Source files are being reloaded; previous plots have been cleared.')
        self.tables.clear('Reloading source CSVs and summaries…')
        try:
            self.session.reload_data()
            self._apply_graph(self.graph.value)
            if plots:
                self.update(save=False)
            else:
                self._refresh_properties()
                self.status.value = 'Data reloaded. Tables refreshed; click Update plots when ready.'
                self.viewer.clear('Data reloaded. Click Update plots when ready.')
        except Exception as error:
            self.status.value = "<b>Data reload failed:</b> " + escape(str(error))
            self.tables.status.value = self.status.value
        finally:
            self.reload_button.disabled = self.tables_reload_button.disabled = False

    def _sample_data_note(self):
        if not self.session.sample_data_dir.is_dir():
            message = 'Bundled samples unavailable; your own data is unaffected.'
        elif not self.session.show_sample_data:
            message = 'Synthetic samples hidden; saved selections are retained.'
        else:
            message = 'Synthetic examples only—not experimental measurements.'
        self.sample_data_note.value = '<small>' + escape(message) + '</small>'

    def _sample_data_changed(self, change):
        if self._paused:
            return
        previous = self.session.show_sample_data
        self.sample_data_toggle.disabled = True
        try:
            if not self.save_current():
                raise RuntimeError('Resolve the graph-save warning before changing sample visibility.')
            self.session.show_sample_data = change['new']
            self.session.reload_data()
            save_sample_data_visibility(self.project_dir, change['new'])
        except Exception as error:
            self.session.show_sample_data = previous
            try:
                self.session.reload_data()
            except Exception:
                # The primary folder may have gone offline. Keep the preference
                # and report the original failure instead of a second UI error.
                self._results, self._signature = [], None
                self.export_button.disabled = True
            old, self._paused = self._paused, True
            try:
                self.sample_data_toggle.value = previous
            finally:
                self._paused = old
            self.status.value = '<b>Sample visibility not changed:</b> ' + escape(str(error))
        else:
            self._apply_graph(self.graph.value)
            self._refresh_properties()
            if self.controls['live_update'].value:
                self.update(save=False)
            else:
                self.status.value = 'Sample visibility saved. Click Update plots when ready.'
        finally:
            self.sample_data_toggle.disabled = False

    def _current_signature(self):
        graph = deepcopy(self._current())
        for key in VIEW_ONLY_SETTINGS:
            graph['settings'].pop(key, None)
        return json.dumps([graph, fit_policy(self.store.data), self.store.data.get('specimen_exclusions', {}),
                           self.store.data.get('specimen_data_modes', {})], sort_keys=True)

    def _fit_settings_saved(self):
        self.session.set_project(self.store.data)
        self._results, self._signature = [], None
        self.export_button.disabled = True
        self.viewer.clear('Specimen calculation settings changed. Update plots to use the saved fit/EL selections.')
        self._show_saved()
        self._refresh_properties()

    def _change_fit_threshold(self, value):
        threshold = validate_threshold(value)
        if not self.save_current():
            raise ValueError('Save failed; the warning threshold was not changed.')
        project = deepcopy(self.store.data)
        project['yield_r2_warning'] = threshold
        if project != self.store.data:
            self.store.save(project)
            self._fit_settings_saved()

    def _apply_specimen_fit(self, ident, source_sha256, override, reason):
        """Validate preview and source, then atomically save a project-wide override."""
        if not self.save_current():
            raise ValueError('Save failed; the specimen fit was not changed.')
        payload = self._inspect_specimen(ident)
        record = payload['record']
        if (source_sha256 != record['source_sha256'] or
                hashlib.sha256(Path(record['source_file']).read_bytes()).hexdigest() != source_sha256):
            raise ValueError('Source data changed during review. Reload data before applying a fit.')
        project = deepcopy(self.store.data)
        before = deepcopy(project.get('specimen_fit_overrides', {}).get(ident))
        timestamp = datetime.now().astimezone().isoformat()
        if override is not None:
            candidate = deepcopy(override)
            candidate['source_sha256'] = source_sha256
            validate_override(candidate)
            fractions = payload['calculation']['fit_fractions']
            result = specimen_calculation(record, fractions, override=candidate)['properties']
            if result['Yield status'] != 'resolved':
                raise ValueError('Cannot apply this fit: ' + result['Notes'])
            automatic = specimen_calculation(record, fractions, override=None)['properties']
            import math
            fields = ('Yield (MPa)', 'Yield strain (%)', 'Fitted E (GPa)', 'Elastic fit R2', 'Elastic intercept (MPa)', 'Yield status', 'Notes')
            snapshot = {key: (automatic[key] if isinstance(automatic[key], str) or math.isfinite(automatic[key]) else None) for key in fields}
            candidate.update(reason=reason.strip(), saved_at=timestamp, automatic_snapshot=snapshot,
                             automatic_fit_fractions=list(fractions))
            validate_override(candidate, saved=True)
            project.setdefault('specimen_fit_overrides', {})[ident] = candidate
        else:
            candidate = None
            project.setdefault('specimen_fit_overrides', {}).pop(ident, None)
        if before == candidate:
            return
        project.setdefault('specimen_fit_history', []).append({'specimen_id': ident, 'saved_at': timestamp,
            'action': 'apply' if candidate else 'restore automatic', 'before': before, 'after': candidate})
        self.store.save(project)
        self._fit_settings_saved()

    def _apply_specimen_failure(self, ident, source_sha256, override, reason):
        """Validate against unchanged raw data, then save an endpoint for all graphs."""
        if not self.save_current():
            raise ValueError('Save failed; failure EL was not changed.')
        payload = self._inspect_specimen(ident)
        record = payload['record']
        if (source_sha256 != record['source_sha256'] or
                hashlib.sha256(Path(record['source_file']).read_bytes()).hexdigest() != source_sha256):
            raise ValueError('Source data changed during review. Reload data before changing failure EL.')
        project = deepcopy(self.store.data)
        before = deepcopy(project.get('specimen_failure_overrides', {}).get(ident))
        timestamp = datetime.now().astimezone().isoformat()
        candidate = None
        if override is not None:
            candidate = deepcopy(override)
            endpoint = manual_failure_endpoint(record, candidate)
            # Validate the exact trimmed prefix too, before committing any setting.
            trial = {**record, '_failure_override': {**candidate, 'source_sha256': source_sha256}}
            fracture_curve(trial)
            automatic = automatic_fracture_endpoint(record)
            import math
            fields = ('status', 'method', 'strain_pct', 'stress_mpa', 'row_before', 'time_s', 'reason', 'endpoint_kind')
            snapshot = {key: (value if isinstance(value, str) or (isinstance(value, (int, float)) and math.isfinite(value)) else None)
                        for key in fields for value in [automatic.get(key)]}
            candidate.update(source_sha256=source_sha256, reason=reason.strip(), saved_at=timestamp,
                             automatic_snapshot=snapshot, strain_pct=endpoint['strain_pct'], stress_mpa=endpoint['stress_mpa'])
            validate_failure_override(candidate, saved=True)
            project.setdefault('specimen_failure_overrides', {})[ident] = candidate
        else:
            project.setdefault('specimen_failure_overrides', {}).pop(ident, None)
        if before == candidate:
            return
        project.setdefault('specimen_failure_history', []).append({'specimen_id': ident, 'saved_at': timestamp,
            'action': 'apply' if candidate else 'restore automatic', 'before': before, 'after': candidate})
        self.store.save(project)
        self._fit_settings_saved()

    def _review_fits(self, _=None):
        self.properties_panel.selected_index = 0
        self.tables.filter.value = ''
        self.tables.review_only.value = True
        self.tables.show_inspector()
        ids = [ident for _, ident in self.tables.inspector.choice.options if ident]
        if ids:
            self.tables.inspector.select(ids[0])

    def _update_fit_warning(self, frames=None):
        samples = frames['tensile_samples'] if frames else None
        if samples is None or samples.empty:
            self.fit_warning.value = ''
            self.review_fits.disabled = True
            return
        flagged = samples[specimen_review_mask(samples)]
        self.review_fits.disabled = flagged.empty
        included = int(flagged['Included'].sum())
        excluded = len(flagged) - included
        threshold = self.store.data.get('yield_r2_warning', .98)
        self.fit_warning.value = (
            f'<div style="padding:9px;background:#fff4dc;border-left:3px solid #d97706">'
            f'<b>{len(flagged)} {"specimen needs" if len(flagged) == 1 else "specimens need"} review</b> · {included} included; {excluded} excluded. '
            f'Fit, fracture/EL, reconstruction or Instron checks. R² threshold {threshold:.5f}. No automatic exclusion.</div>'
            if len(flagged) else f'Specimen checks: no review items. R² threshold {threshold:.5f}.')

    def _inspect_specimen(self, ident):
        with redirect_stdout(io.StringIO()):
            return self.session.specimen_inspection(self.state(), self._current()['definition'], ident)

    def _refresh_properties(self):
        self.table_export_button.disabled = True
        self.tables.set_threshold(self.store.data.get('yield_r2_warning', .98))
        self._update_fit_warning()
        state = self.state()
        if not state['groups']:
            self.tables.clear()
            return
        self.tables_update_button.disabled = True
        try:
            with redirect_stdout(io.StringIO()):
                frames = self.session.property_tables(state, self._current()['definition'])
            self.tables.set_frames(frames, color_map=self.session.color_map(state, self._current()['definition']))
            self._update_fit_warning(frames)
            self.table_export_button.disabled = frames['tensile_samples'].empty
        except Exception as error:
            self.tables.clear('<b>Property tables unavailable:</b> ' + escape(str(error)))
        finally:
            self.tables_update_button.disabled = False

    def _update_tables(self, _=None):
        if self.save_current():
            self._refresh_properties()

    def _export_properties(self, _=None):
        if not self.save_current():
            return
        self.table_export_button.disabled = True
        try:
            destination = self.session.export_properties(self.state(), self._current()['definition'])
            self.tables.status.value = 'Tables exported to <code>' + escape(str(destination)) + '</code>. No plots generated.'
        except Exception as error:
            self.tables.status.value = '<b>Table export failed:</b> ' + escape(str(error))
        finally:
            self.table_export_button.disabled = False

    def update(self, save=True):
        if self._busy or (save and not self.save_current()):
            return
        state = self.state()
        self._results, self._signature = [], None
        self.export_button.disabled = True
        self._refresh_properties()
        if not state["groups"] or not state["families"]:
            self.viewer.clear("No plot types selected. Property tables remain available above.")
            self.status.value = "Choose plot types when needed. Tables do not require a plot selection."
            return
        self._busy = True
        self.update_button.disabled = True
        self.status.value = "Updating selected plots…"
        start, items, messages, failed = perf_counter(), [], [], 0
        try:
            variants = [False, True] if state["show_both_versions"] else [state["show_individuals"]]
            for family in state["families"]:
                for individuals in variants:
                    label = dict((value, label) for label, value in FAMILIES)[family]
                    subtitle = "with individuals" if individuals else "without individuals"
                    item = {"key": family + ("_with" if individuals else "_without"), "label": label + " · " + subtitle}
                    try:
                        if family in PROPERTY_FAMILIES:
                            item['warning'] = self.session.scatter_omission_warning(state, self._current()['definition'])
                        result = self.session.render({**state, "graph_index": self._index(), "family": family, "show_individuals": individuals})
                        self._results.append(result)
                        items.append({**item, "result": result})
                        messages.append(label + ":\n" + result["log"])
                    except Exception as error:
                        failed += 1
                        message = str(error)
                        items.append({**item, "error": message})
                        messages.append(label + ": " + message)
            self.viewer.set_items(items)
            self._signature = self._current_signature()
            self.details.value = "\n\n".join(messages)
            self.status.value = f"{len(self._results)} plots ready in {perf_counter()-start:.2f} s" + (f" · {failed} unavailable (see details)" if failed else "") + " · no results exported."
            self.export_button.disabled = not self._results
        finally:
            self._busy = False
            self.update_button.disabled = False

    def _export(self, _=None):
        if not self._results or self._signature != self._current_signature() or not self.save_current():
            self.status.value = "Update the visible plots before exporting."
            return
        self.export_button.disabled = True
        try:
            destination = self.session.export(self._results, include_tables=self.controls["export_tables"].value)
            self.status.value = "Exported the ready plots and settings to <code>" + escape(str(destination)) + "</code>"
        except Exception as error:
            self.status.value = "<b>Export failed:</b> " + escape(str(error))
        finally:
            self.export_button.disabled = False

    def show(self):
        from IPython.display import display
        display(self.ui)
        return self

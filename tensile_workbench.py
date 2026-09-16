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
from tensile_tables import property_tables, PropertyTablesView
from tensile_selection import is_included
import hashlib
import io
import json
import platform
import re
import uuid

NEW_GRAPH_ACTION = '__create_new_graph__'


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
]

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
        self.files = self.engine.find_sample_groups(self.data_dir)
        self._records.clear()
        self._models.clear()
        self._previews.clear()
        self._property_frames = {}
        self.instron = InstronSummaries(self.data_dir)
        import itertools
        palette = itertools.cycle(self.engine.plt.rcParams["axes.prop_cycle"].by_key()["color"])
        self.colors = {g: next(palette) for g in sorted(self.files)}

    def set_project(self, project):
        self.project = deepcopy(project)
        self.graphs = [{**g["definition"], "name": g["name"]} for g in project["graphs"]]
        self.engine.NAME_LOOKUP = deepcopy(project.get("display_names", {}))

    def output_root(self):
        """Local folder choice overrides the graph template without changing it."""
        from tensile_startup import resolve_folder
        configured = self._output_override if self._output_override is not None else self.project.get('output_directory', './output')
        return resolve_folder(configured, self.project_dir)

    def defaults(self, graph_index=0):
        result = deepcopy(self.project["graphs"][graph_index]["settings"])
        result["graph_index"] = graph_index
        result["family"] = result["families"][0] if result["families"] else "landmark"
        return result

    def _load(self, group):
        if group not in self._records:
            if group not in self.files:
                raise ValueError(f"Unknown group: {group}")
            records = []
            for source in self.files[group]:
                result = self.engine.load_and_prepare_curve(source)
                if result is None:
                    print(f"[SKIP] No usable stress–strain data: {source.name}")
                    continue
                strain, stress = result
                records.append({
                    "sample": source.stem, "source_file": str(source),
                    "specimen_id": source.relative_to(self.data_dir).as_posix(),
                    "strain_pct": strain, "stress_mpa": stress,
                    "raw_strain_pct": strain, "raw_stress_mpa": stress,
                    "failure_elongation_pct": self.engine.failure_elongation_percent(strain),
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                })
            for record in records:
                self.engine.specimen_properties(record)
            self._records[group] = records
        return self._records[group]

    def included_records(self, groups, spec):
        """The single selection gate for every plot family and average export."""
        return {group: selected for group in groups
                if (selected := [row for row in self._load(group) if is_included(row, spec)])}

    def property_tables(self, state, spec):
        """Available without selecting, rendering or successfully fitting a plot."""
        key = json.dumps([state['groups'], spec.get('landmark_yield_fit_fractions', self.engine.LANDMARK_YIELD_FIT_FRACTIONS),
                          spec.get('specimen_exclusions', {})], sort_keys=True)
        if key not in self._property_frames:
            records = {group: self._load(group) for group in state['groups']}
            self._property_frames[key] = property_tables(records, spec, self.engine, self.instron)
            if len(self._property_frames) > 16:
                self._property_frames.pop(next(iter(self._property_frames)))
        return self._property_frames[key]

    def export_properties(self, state, spec):
        """Explicit table-only export; does not calculate average curves."""
        frames = self.property_tables(state, spec)
        if frames['tensile_samples'].empty:
            raise ValueError('No specimen data to export.')
        base = self.output_root()
        destination = base / self.engine.safe_filename(spec['name']) / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_tables')
        destination.mkdir(parents=True, exist_ok=False)
        for name, frame in frames.items():
            self.engine.write_excel_table(frame, destination / (name + '.xlsx'), name[:31])
        (destination / 'settings.json').write_text(json.dumps({'graph_definition': spec, 'settings': state,
            'engine_sha256_at_load': self.engine_sha256,
            'note': 'Individual specimen properties only. Instron comparisons use CSV summaries; see specimen_diagnostics for source hashes.'}, indent=2))
        return destination

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
        for key in ("tensile_xlim", "tensile_ylim", "wh_xlim", "wh_ylim"):
            pair = state[key]
            if pair is not None and (len(pair) != 2 or not all(math.isfinite(v) for v in pair) or pair[0] >= pair[1]):
                raise ValueError(f"{key}: lower limit must be smaller than upper limit.")

    def render(self, state):
        """Cache unaffected plots when another control or panel changes."""
        self._validate(state)
        key_state = deepcopy(state)
        for key in ("families", "show_both_versions", "graph_index", *VIEW_ONLY_SETTINGS):
            key_state.pop(key, None)
        family = state["family"]
        if not family.startswith("work_hardening"):
            for key in ("wh_points", "modulus_gpa", "respect_modulus_overrides", "min_plastic_strain", "despike", "despike_window", "despike_sigma", "median", "median_window", "smooth", "smooth_window", "poly_order", "wh_xlim", "wh_ylim"):
                key_state.pop(key, None)
        else:
            for key in ("pointwise_points", "tail_enabled", "tail_window", "tail_setback", "landmark_error_bars", "tensile_xlim", "tensile_ylim"):
                key_state.pop(key, None)
            if family == "work_hardening":
                key_state.pop("landmark_points", None)
        key = json.dumps([key_state, self.graphs[state["graph_index"]], self.project.get("display_names", {})], sort_keys=True)
        if key not in self._previews:
            self._previews[key] = self._render_uncached(state)
            if len(self._previews) > 12:
                self._previews.popitem(last=False)
        self._previews.move_to_end(key)
        spec = deepcopy(self.graphs[state["graph_index"]])
        spec["tensile_mean_tail"] = {**self.engine.TENSILE_MEAN_TAIL, **spec.get("tensile_mean_tail", {}),
            "enabled": state["tail_enabled"], "fit_window_percent": state["tail_window"], "setback_percent": state["tail_setback"]}
        return {**self._previews[key], "state": deepcopy(state), "graph_spec": spec}

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
                records = self.included_records(state['groups'], spec)
                if not records:
                    raise ValueError('No included usable specimens. Tick Include on the Specimens tab.')
                empty = [g for g in state['groups'] if g not in records]
                if empty:
                    print('[SELECTION] No included usable specimens; omitted groups: ' + ', '.join(empty))
                curves = {g: [(r["strain_pct"], r["stress_mpa"]) for r in rows] for g, rows in records.items()}
                auto_x, auto_y = e.compute_axes(curves)
                is_wh = state["family"].startswith("work_hardening")
                xlim = state["wh_xlim"] if is_wh else state["tensile_xlim"] or auto_x
                ylim = state["wh_ylim"] if is_wh else state["tensile_ylim"] or auto_y
                family = state["family"]
                models = None
                if family not in ("work_hardening", "representative"):
                    key = json.dumps([spec, sorted(records), state["landmark_points"], state["pointwise_points"]], sort_keys=True)
                    if key not in self._models:
                        model_log = io.StringIO()
                        with redirect_stdout(model_log):
                            result = e.prepare_average_curves(spec, records,
                                landmark_points_per_stage=state["landmark_points"],
                                pointwise_points=state["pointwise_points"])
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
                }
                titles = spec.get("titles", {})
                title = next((titles[k] for k in title_keys.get(family, ()) if k in titles),
                             dict((value, label) for label, value in FAMILIES)[family])
                title = spec.get("workbench_titles", {}).get(family) or title
                common = dict(out_path=Path("preview.png"), color_map={**self.colors, **spec.get('color_overrides', {})},
                              show_individual=state["show_individuals"], xlim=xlim, ylim=ylim,
                              title=title, name_overrides=spec.get("name_overrides", {}), preview=True)
                wh = self._wh_settings(state, spec)
                if family in ("landmark", "pointwise", "comparison"):
                    fig = e.render_average_plot(models, records, family=family,
                        landmark_error_bars=state["landmark_error_bars"], **common)
                elif family == "representative":
                    fig = e.render_representative_tensile_plot(records,
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
                        "seconds": perf_counter() - start, "n_samples": len(source_rows)}
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
        first.text(.5, .01, "Solid: mean specimen WH; dashed: derivative of landmark mean.\nFaint lines, if enabled: original specimen WH.", ha="center")
        first.tight_layout(rect=(0, .08, 1, 1))
        return first

    def export(self, results, include_tables=False):
        """Explicit multi-plot snapshot; no original batch directories touched."""
        if not results:
            raise ValueError("There are no valid previews to export.")
        result = results[0]
        graph = self.engine.safe_filename(result["graph_spec"]["name"])
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:6]
        destination = self.output_root() / graph / stamp
        destination.mkdir(parents=True, exist_ok=False)
        state = result["state"]
        metadata = {
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
                family_number = {"pointwise": "01", "landmark": "02", "comparison": "03", "representative": "04", "work_hardening": "05", "work_hardening_landmark": "06", "work_hardening_comparison": "07"}[view_state["family"]]
                plot = destination / f"{graph}_{family_number}_{view_state['family']}_{variant}.png"
                view["figure"].savefig(plot, dpi=self.engine.PLOT_DPI)
            (destination / "settings.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            (destination / "calculation_log.txt").write_text("\n\n".join(r["log"] for r in results), encoding="utf-8")
            if include_tables:
                self._export_tables(destination, result)
        except Exception as error:
            raise RuntimeError(f"Export incomplete in {destination}: {error}") from error
        return destination

    def _export_tables(self, destination, result):
        """Build all graph-level tables from cached original curves on demand."""
        e, state, spec = self.engine, result["state"], result["graph_spec"]
        records = self.included_records(state['groups'], spec)
        with redirect_stdout(io.StringIO()):
            models, audit, summary = e.prepare_average_curves(spec, records,
                landmark_points_per_stage=state["landmark_points"], pointwise_points=state["pointwise_points"])
        frames = dict(self.property_tables(state, spec))
        frames.update(landmark_samples=e.pd.DataFrame(audit), landmark_summary=e.pd.DataFrame(summary),
                      toughness_stats=e.pd.DataFrame(e.summarize_toughness_stats(models, spec)))
        curves = []
        for group, model in models.items():
            for method in ("pointwise", "landmark"):
                curve = model[method]
                if curve is not None:
                    curves.extend({"Group": group, "Method": method, "Strain (%)": float(x), "Stress (MPa)": float(y),
                        "Segment": "stage-aligned" if method=="landmark" else ("fitted tail" if x>curve["measured_x"][-1] else "measured mean")}
                        for x, y in zip(curve["x"], curve["y"]))
        frames.update(average_curves=e.pd.DataFrame(curves))
        for name, frame in frames.items():
            e.write_excel_table(frame, destination / f"{name}.xlsx", name[:31])


class TensileWorkbench:
    """Graph editor and multi-plot board. Definitions autosave independently of previews."""

    def __init__(self, project_dir=None, project_path=None, data_dir=None, output_dir=None):
        import ipywidgets as w
        self.w = w
        self.project_dir = Path(project_dir or Path(__file__).parent).expanduser().resolve()
        self.store = ProjectStore(project_path or self.project_dir / "tensile_workbench.project.json",
                                  self.project_dir / "tensile_workbench_defaults.json")
        self.session = PreviewSession(self.project_dir, self.store.data, data_dir, output_dir)
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
        self.family_boxes = {family: w.Checkbox(description=label, indent=False, layout=w.Layout(width="auto")) for label, family in FAMILIES}
        self._check("show_individuals", "Show individual specimens")
        self._check("show_both_versions", "Display both with/without-individuals versions")
        self._check("landmark_error_bars", "Landmark ±1 SD bars")
        self._check("live_update", "Live preview (on slider release)")
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
                           ("wh_xlim", "WH plastic strain (%)"), ("wh_ylim", "WH rate (MPa)")):
            auto = w.Checkbox(description="Automatic", indent=False)
            lo, hi = w.FloatText(description="Min:", continuous_update=False), w.FloatText(description="Max:", continuous_update=False)
            row = w.VBox([w.HTML("<b>" + title + "</b>"), auto, self._row([lo, hi])])
            self.axes[key] = (auto, lo, hi, row)
        for label, family in FAMILIES:
            self.title_inputs[family] = w.Text(description=label, continuous_update=False,
                style={"description_width": "initial"}, layout=w.Layout(width="98%"))
        self.override_group = w.Dropdown(description="Group:", layout=w.Layout(width="98%"))
        self.override_name = w.Text(description="Legend label:", continuous_update=False,
                                    style={"description_width": "initial"}, layout=w.Layout(width="98%"))
        self.override_color_enabled = w.Checkbox(description='Override colour for this graph', indent=False)
        self.override_color = w.ColorPicker(description='Colour:', value='#1f77b4', concise=False)
        self.override_e_enabled = w.Checkbox(description="Use a group-specific WH modulus", indent=False)
        self.override_e = w.BoundedFloatText(value=115, min=1, max=1000, description="E (GPa):")
        self.override_rep = w.Dropdown(description="Representative:", style={"description_width": "initial"}, layout=w.Layout(width="98%"))
        self.override_button = w.Button(description="Apply group overrides")
        self.update_button = w.Button(description="Update plots", button_style="primary")
        self.reload_button = w.Button(description="Reload data")
        self.export_button = w.Button(description="Export plot set", tooltip="Export all generated plots in this set, including when one is enlarged.", disabled=True)
        self.viewer = DualPlotView(w, self.controls["columns"], self.controls["plot_width"], self.controls["renderer"])
        self.board = self.viewer.board
        self.details = w.Textarea(disabled=True, layout=w.Layout(width="98%", height="180px"))
        self.tables = PropertyTablesView(w, on_selection=self._specimen_changed)
        self.tables_update_button = w.Button(description='Update tables')
        self.table_export_button = w.Button(description='Export tables only', disabled=True)
        self.properties_panel = w.Accordion(children=[w.VBox([
            self.tables.ui, self._row([self.tables_update_button, self.table_export_button])
        ])], selected_index=None, layout=w.Layout(width='100%'))
        self.properties_panel.set_title(0, 'Specimen properties · tables and Instron comparison')
        general = w.Accordion(children=[w.VBox([self.override_group, self.override_name,
                             self.override_color_enabled, self.override_color, self.override_button])], selected_index=None)
        general.set_title(0, "Labels and colours · this graph, all plot types")
        self.plot_settings = {}
        self.plot_selectors = {}
        for label, family in FAMILIES:
            self.title_inputs[family].description = "Title:"
            local = [self.title_inputs[family]]
            wh = family.startswith("work_hardening")
            axes_prefix = "wh" if wh else "tensile"
            axes = w.Accordion(children=[w.VBox([self.axes[axes_prefix + suffix][3] for suffix in ("_xlim", "_ylim")])], selected_index=None)
            axes.set_title(0, "Axes · linked across " + ("WH plots" if wh else "tensile plots"))
            local.append(axes)
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
            w.HTML("Tick the exact sample groups to include, regardless of their naming format."), general,
            self.properties_panel,
            w.HTML("<h3>Plot views</h3>"), self.controls["renderer"],
            self._row([self.controls["show_individuals"], self.controls["show_both_versions"]]),
            w.HTML("Choose plots below. Each selector has its own settings. Shared averaging parameters and axis ranges stay linked between related plots."),
            self.plot_options,
            self._row([self.update_button, self.reload_button, self.controls["live_update"]]),
            self.status, self.viewer.ui,
            self._row([self.export_button, self.controls["export_tables"]]), log,
        ], layout=w.Layout(width="100%"))
        self._refresh_graph_options()
        self._apply_graph(self.store.data["selected_graph"])
        self.graph.observe(self._graph_changed, names="value")
        self.name.observe(self._changed, names="value")
        for key, widget in self.controls.items():
            widget.observe(self._view_changed if key in VIEW_ONLY_SETTINGS else self._changed, names="value")
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
            choices = sorted(set(self.session.files) | set(state["groups"]))
            self.controls["groups"].options = [(g if g in self.session.files else g + " (unavailable)", g) for g in choices]
            for key, control in self.controls.items():
                value = state.get(key, {"export_tables": False, "plot_width": 640, "renderer": "static"}.get(key, control.value))
                if key == "groups":
                    value = tuple(value)
                if isinstance(control, (self.w.IntSlider, self.w.FloatSlider)):
                    control.min = min(control.min, value)
                    control.max = max(control.max, value)
                control.value = value
            for family, box in self.family_boxes.items():
                box.value = family in state["families"]
            fallbacks = {"tensile_xlim": [0,30], "tensile_ylim": [0,1000], "wh_xlim": [0,7], "wh_ylim": [0,4500]}
            for key, (auto, lo, hi, _) in self.axes.items():
                pair = state.get(key)
                auto.value = pair is None
                lo.value, hi.value = pair or fallbacks[key]
            legacy = graph["definition"].get("titles", {})
            title_keys = {"landmark": "tensile_landmark_aligned", "pointwise": "tensile_averages_only", "comparison": "tensile_comparison", "representative": "tensile_representative", "work_hardening": "work_hardening_averages_only", "work_hardening_landmark": "work_hardening_landmark"}
            for family, control in self.title_inputs.items():
                control.value = graph["definition"].get("workbench_titles", {}).get(family, legacy.get(title_keys.get(family), ""))
            self.override_group.options = state["groups"]
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

    def save_current(self):
        """Validate then autosave; never discard a conflicting external edit."""
        try:
            state = self.state()
            check = {**state, "groups": state["groups"] or ["draft"], "family": state["families"][0] if state["families"] else "landmark"}
            self.session._validate(check)
            project = deepcopy(self.store.data)
            graph = project["graphs"][self._index()]
            graph["name"] = self.name.value.strip()
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
            return True
        except Exception as error:
            self.save_status.value = "<b>Not saved:</b> " + escape(str(error))
            self.export_button.disabled = True
            return False

    def _changed(self, _=None):
        if self._paused:
            return
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

    def _specimen_changed(self, ident, included, reason):
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
            exclusions = spec.setdefault('specimen_exclusions', {})
            if included:
                exclusions.pop(ident, None)
            else:
                exclusions[ident] = reason.strip()
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
                self.status.value = 'Specimen selection saved for this graph. Tables updated; click Update plots when ready.'
        except Exception as error:
            self.save_status.value = '<b>Specimen selection not saved:</b> ' + escape(str(error))
            self._refresh_properties()

    def _load_overrides(self, _=None):
        group = self.override_group.value
        if group is None:
            return
        spec = self._current()["definition"]
        self.override_name.value = spec.get("name_overrides", {}).get(group, self.store.data.get("display_names", {}).get(group, group))
        from matplotlib.colors import to_hex
        color = spec.get('color_overrides', {}).get(group)
        self.override_color_enabled.value = color is not None
        self.override_color.value = color or to_hex(self.session.colors.get(group, '#1f77b4'))
        modulus = spec.get("youngs_modulus_overrides", {}).get(group)
        self.override_e_enabled.value = modulus is not None
        self.override_e.value = modulus/1000 if modulus is not None else self.controls["modulus_gpa"].value
        with redirect_stdout(io.StringIO()):
            rows = [r for r in self.session._load(group) if is_included(r, spec)] if group in self.session.files else []
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

    def _reload_data(self, _=None):
        if not self.save_current():
            return
        self.export_button.disabled = True
        self._results, self._signature = [], None
        try:
            self.session.reload_data()
            self._apply_graph(self.graph.value)
            self.update(save=False)
        except Exception as error:
            self.status.value = "<b>Data reload failed:</b> " + escape(str(error))

    def _current_signature(self):
        graph = deepcopy(self._current())
        for key in VIEW_ONLY_SETTINGS:
            graph['settings'].pop(key, None)
        return json.dumps(graph, sort_keys=True)

    def _refresh_properties(self):
        self.table_export_button.disabled = True
        state = self.state()
        if not state['groups']:
            self.tables.clear()
            return
        self.tables_update_button.disabled = True
        try:
            with redirect_stdout(io.StringIO()):
                frames = self.session.property_tables(state, self._current()['definition'])
            self.tables.set_frames(frames)
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

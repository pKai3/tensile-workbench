"""Property populations and curve populations must not silently diverge."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import ipywidgets as w
import pandas as pd

from selection_fixture import make_fixture
from tensile_workbench import PreviewSession, TensileWorkbench
from tensile_selection import selection_state, property_allowed, curve_allowed, DATA_MODES
from tensile_tables import specimen_table_data, specimen_export_frame
from tensile_comparison import relative_comparison
from tensile_group_review import GroupCurveReview, review_marker_points
from tensile_specimens import SpecimenTable
from tensile_exports import export_curves
from workbench_project import validate_project


class PartialDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='partial-data-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = make_fixture(self.root)
        self.session = PreviewSession(self.root, self.project)
        self.state = self.session.defaults()

    def mode(self, number, mode):
        self.project.setdefault('specimen_data_modes', {})[f'Alloy A/coupon_{number}.csv'] = {'mode': mode, 'reason': 'Synthetic AVE failure'}
        self.session.set_project(self.project)

    def frames(self):
        with redirect_stdout(io.StringIO()):
            return self.session.property_tables(self.state, self.session.graphs[0])

    def models(self, prepeak=False):
        with redirect_stdout(io.StringIO()):
            records = self.session.analysis_records(self.state, self.session.graphs[0], measured=prepeak)
            return self.session.engine.prepare_average_curves(self.session.graphs[0], records, prepeak_only=prepeak)[0]['Alloy A']

    def test_policy_matrix_and_legacy_graph_override(self):
        fields = ['ys', 'uts', 'uniform', 'el']
        expected = {'all': [1,1,1,1], 'after_uts': [1,1,1,0], 'after_yield': [1,1,0,0],
                    'no_strain': [0,1,0,0], 'exclude': [0,0,0,0]}
        for mode in DATA_MODES:
            self.assertEqual([property_allowed(mode, f) for f in fields], expected[mode])
        row = {'source_file': 'A/spec.csv'}
        project = {'specimen_data_modes': {'A/spec.csv': {'mode': 'after_yield'}}}
        self.assertEqual(selection_state(row, {}, project)['mode'], 'after_yield')
        self.assertEqual(selection_state(row, {'specimen_inclusion_overrides': {'A/spec.csv': {'included': True}}}, project)['mode'], 'all')
        self.assertFalse(curve_allowed({'_data_mode': 'after_uts'}))
        self.assertTrue(curve_allowed({'_data_mode': 'after_uts'}, prepeak=True))

    def test_summary_uses_property_counts_but_display_keeps_raw_values(self):
        baseline = self.frames()['tensile_samples'].copy()
        self.mode(2, 'after_uts')
        frames = self.frames()
        details = frames['tensile_summary_details'].query("Source == 'Calculated' or Source == 'Calc'").set_index('Property')
        self.assertEqual(details.loc['0.2% yield strength', 'n'], 3)
        self.assertEqual(details.loc['Uniform elongation', 'n'], 3)
        self.assertEqual(details.loc['Failure elongation', 'n'], 2)
        self.assertEqual(details.loc['Tensile toughness', 'n'], 2)
        np.testing.assert_allclose(frames['tensile_samples']['Failure Elongation (%)'], baseline['Failure Elongation (%)'])
        _, _, rows = specimen_table_data(frames['tensile_samples'], frames['instron_comparison'])
        self.assertEqual(rows[1]['mode'], 'after_uts')
        self.assertTrue(rows[1]['excluded_values'])
        exported = specimen_export_frame(frames['tensile_samples'], frames['instron_comparison'])
        self.assertIn('Failure elongation', exported.iloc[1]['Excluded properties'])

    def test_instron_values_do_not_bypass_exclusion(self):
        self.mode(2, 'no_strain')
        match = self.session.instron.match
        def populated(group, record):
            ref = match(group, record)
            return {**ref, 'values': {**ref['values'], 'ys': 600., 'uts': 750., 'uniform': 7., 'el': 17., 'e': 120.}}
        with patch.object(self.session.instron, 'match', side_effect=populated):
            frames = self.frames()
        details = frames['tensile_summary_details'].query("Source == 'Instron'").set_index('Property')
        self.assertEqual(details.loc['UTS', 'n'], 3)
        self.assertEqual(details.loc['0.2% yield strength', 'n'], 2)
        self.assertEqual(details.loc['Failure elongation', 'n'], 2)
        comparisons = relative_comparison(frames).set_index('Property')
        self.assertEqual(comparisons.loc['0.2% yield strength', 'Paired n'], 2)
        self.assertEqual(comparisons.loc['Failure elongation', 'Paired n'], 2)

    def test_landmark_uses_all_eligible_means_not_only_shape_cohort(self):
        self.mode(2, 'after_uts')
        model = self.models()['landmark']
        self.assertEqual(model['shape_n'], 2)
        self.assertEqual(model['property_counts']['Yield (MPa)'], 3)
        self.assertEqual(model['property_counts']['Failure elongation (%)'], 2)
        summary = self.frames()['tensile_summary_details']
        for point, prop, source in [('yield', '0.2% yield strength', 'Calculated'), ('UTS', 'UTS', 'Calculated'), ('failure', 'Failure elongation', 'Calc')]:
            mark = next(p for p in model['point_statistics'] if p['name'] == point)
            value = mark['x'] if point == 'failure' else mark['y']
            mean = summary[(summary.Property == prop) & (summary.Source == source)]['Mean'].iloc[0]
            self.assertAlmostEqual(value, mean)
            self.assertAlmostEqual(np.interp(mark['x'], model['x'], model['y']), mark['y'])
        self.assertEqual(self.models(prepeak=True)['landmark']['shape_n'], 3)
        self.mode(2, 'after_yield')
        model = self.models(prepeak=True)['landmark']
        self.assertEqual(model['shape_n'], 2)
        self.assertEqual(model['property_counts']['Uniform elongation (%)'], 2)
        self.assertEqual(model['property_counts']['UTS (MPa)'], 3)

    def test_unaffected_landmarks_preserve_previous_shape(self):
        records = self.session.included_records(self.state['groups'], self.session.graphs[0])['Alloy A']
        with redirect_stdout(io.StringIO()):
            items = [self.session.engine.landmark_specimen(r) for r in records]
        x, y, knots = self.session.engine.average_landmark_shapes(items)
        model = self.models()['landmark']
        np.testing.assert_allclose(model['x'], x)
        np.testing.assert_allclose(model['y'], y, atol=1e-10)

    def test_no_eligible_shapes_does_not_fabricate_curve(self):
        for number in (1,2,3):
            self.mode(number, 'after_yield')
        self.assertIsNone(self.models()['landmark'])
        self.assertIsNone(self.models(prepeak=True)['landmark'])
        self.assertEqual(self.frames()['tensile_summary']['Included n'].iloc[0], 3)

    def test_stress_peak_retained_even_without_any_valid_strain(self):
        record = deepcopy(self.session._load('Alloy A')[0])
        record.pop('_property_cache', None)
        record['source_sha256'] = 'synthetic-changed'
        record['strain_pct'] = record['stress_mpa'] = np.array([])
        record['raw_strain_pct'] = record['raw_stress_mpa'] = np.array([])
        record['_measurement_indices'] = np.array([], dtype=int)
        record['_acquisition']['strain'][:] = np.nan
        record['_data_mode'] = 'no_strain'
        props = self.session.engine.specimen_properties(record)
        self.assertAlmostEqual(props['UTS (MPa)'], np.nanmax(record['_acquisition']['stress']))
        self.assertTrue(np.isnan(props['Yield (MPa)']))
        self.assertTrue(np.isnan(props['Uniform elongation (%)']))

    def test_scatter_omits_partial_specimens_and_warning_names_them(self):
        self.mode(2, 'after_uts')
        result = self.session.render({**self.state, 'family': 'ys_vs_el', 'show_individuals': True})
        warning = self.session.scatter_omission_warning(self.state, self.session.graphs[0])
        self.assertIn('coupon_2', warning)
        individuals = [line for line in result['figure'].axes[0].lines if hasattr(line, '_tensile_hover_label')]
        self.assertEqual(len(individuals), 2)
        self.assertFalse(any('coupon_2' in line._tensile_hover_label for line in individuals))
        self.assertFalse((self.root / 'output').exists())

    def test_group_review_is_lazy_keeps_untrimmed_points_and_excluded_curves(self):
        self.project['specimen_exclusions'] = {'Alloy A/coupon_1.csv': ''}
        self.session.set_project(self.project)
        frames = self.frames()
        _, _, rows = specimen_table_data(frames['tensile_samples'], frames['instron_comparison'])
        loader = lambda group: self.session.group_review_records(group, self.session.graphs[0])
        review = GroupCurveReview(w, loader=loader)
        self.addCleanup(review.clear)
        review.set_rows(rows)
        self.assertIsNone(review.figure)
        review.set_active(True)
        self.assertIsNotNone(review.figure, review.status.value)
        self.assertEqual(len(review.figure.data), 3)
        trace = review.figure.data[0]
        self.assertEqual(trace.line.dash, '12 5')
        self.assertEqual(len(trace.x), len(self.session._load('Alloy A')[0]['_acquisition']['strain']))
        before = deepcopy(self.session.project)
        review.select(rows[1]['id'])
        self.assertEqual(review.figure.data[1].line.width, 3.5)
        self.assertTrue(all(t.visible is True for t in review.figure.data))
        self.assertEqual(self.session.project, before)
        review.show_excluded.value = False
        self.assertEqual(len(review.figure.data), 2)

    def test_group_review_sorts_displayed_names_naturally_in_table_and_legend(self):
        frames = self.frames()
        _, _, rows = specimen_table_data(frames['tensile_samples'], frames['instron_comparison'])
        named = [{**row, 'sample': name} for row, name in zip(rows, ('B003_10', 'b003_2', 'B003_1'))]
        review = GroupCurveReview(w, loader=lambda group: self.session.group_review_records(group, self.session.graphs[0]))
        self.addCleanup(review.clear)
        review.set_rows(named)
        review.set_active(True)
        expected = ['B003_1', 'b003_2', 'B003_10']
        self.assertEqual([r['sample'] for r in review.table.rows], expected)
        self.assertEqual([trace.name for trace in review.figure.data], expected)
        self.assertEqual(review.selected, rows[2]['id'])
        self.assertEqual([r['sample'] for r in named], ['B003_10', 'b003_2', 'B003_1'])

    def test_review_partial_modes_have_visible_labels_and_distinct_styles(self):
        import plotly.graph_objects as go
        self.mode(1, 'after_uts')
        self.mode(2, 'after_yield')
        self.mode(3, 'no_strain')
        frames = self.frames()
        _, _, rows = specimen_table_data(frames['tensile_samples'], frames['instron_comparison'])
        review = GroupCurveReview(w, loader=lambda group: self.session.group_review_records(group, self.session.graphs[0]))
        self.addCleanup(review.clear)
        review.set_rows(rows)
        with patch('plotly.graph_objects.FigureWidget', wraps=go.FigureWidget) as create_widget:
            review.set_active(True)
        # Voilà must receive complete initial data/layout, not an empty widget
        # followed by pre-mount messages that the browser may never receive.
        initial_figure = create_widget.call_args.args[0]
        self.assertEqual(len(initial_figure.data), 3)
        self.assertFalse(initial_figure.layout.showlegend)
        self.assertEqual(initial_figure.layout.yaxis.title.text, 'Engineering stress (MPa)')
        self.assertEqual(DATA_MODES['after_uts'], 'AVE failed after UTS / Broke outside dots')
        self.assertEqual([t.line.dash for t in review.figure.data], ['8 4', '2 4', '8 3 2 3'])
        for row, short, trace in zip(rows, ['EL excluded', 'Post-yield strain excluded', 'All strain excluded'], review.figure.data):
            button = review._legend_buttons[row['id']]
            self.assertIsInstance(button, w.Button)
            self.assertIn(short, button.description)
            self.assertIn(DATA_MODES[row['mode']], button.tooltip)
            self.assertIn(DATA_MODES[row['mode']], trace.hovertemplate)
        self.assertIn('Broke outside dots', review.status.value)
        self.assertFalse(review.figure.layout.showlegend)
        self.assertLess(review.ui.children.index(review.legend), review.ui.children.index(review.plot))
        margin = review.figure.layout.margin.to_plotly_json()
        review.plot.children[0].pixels = 740
        self.assertEqual(review.figure.layout.width, 740)
        review.select(rows[2]['id'])
        self.assertEqual(review.figure.layout.margin.to_plotly_json(), margin)

    def test_review_dense_curves_use_svg_and_keep_every_point_gap_and_dash_on_selection(self):
        self.mode(2, 'after_uts')
        frames = self.frames()
        _, _, rows = specimen_table_data(frames['tensile_samples'], frames['instron_comparison'])
        records = self.session.group_review_records('Alloy A', self.session.graphs[0])
        x = np.linspace(0., 18., 50001)
        y = 800. * (1. - np.exp(-x * 4.)) - np.maximum(x - 8., 0.) ** 2
        x[20000:20005] = np.nan  # missing AVE readings must remain a gap
        x[35000:35010] = x[35000:35010][::-1]  # retain strain reversals
        y[41000] += 30.  # isolated spike is not filtered from stored plot data
        y[-1] = 200.  # preserve the sparse, near-vertical fracture drop
        records[1] = {**records[1], '_acquisition': {'strain': x, 'stress': y, 'time': np.arange(len(x))}}
        review = GroupCurveReview(w, loader=lambda group: records)
        self.addCleanup(review.clear)
        review.set_rows(rows)
        review.set_active(True)
        trace = review.figure.data[1]
        self.assertEqual(trace.type, 'scatter')
        self.assertTrue(trace.line.simplify)
        self.assertEqual(trace.line.shape, 'linear')
        self.assertFalse(trace.connectgaps)
        np.testing.assert_array_equal(trace.x, x)
        np.testing.assert_array_equal(trace.y, np.where(np.isfinite(x), y, np.nan))
        dash = trace.line.dash
        review.select(rows[1]['id'])
        self.assertEqual(trace.line.width, 3.5)
        self.assertEqual(trace.line.dash, dash)
        review.select(rows[0]['id'])
        self.assertEqual(trace.line.width, 1.3)
        self.assertEqual(trace.line.dash, dash)

    def test_review_markers_and_highlighting_never_change_data_use_visibility_or_zoom(self):
        self.mode(2, 'after_uts')
        frames = self.frames()
        _, _, rows = specimen_table_data(frames['tensile_samples'], frames['instron_comparison'])
        review = GroupCurveReview(w, loader=lambda group: self.session.group_review_records(group, self.session.graphs[0]))
        self.addCleanup(review.clear)
        review.set_rows(rows)
        review.set_active(True)
        original_project = deepcopy(self.session.project)
        figure = review.figure
        figure.update_layout(xaxis_range=[2., 12.], yaxis_range=[200., 900.])
        highlighted = rows[1]['id']
        review._legend_buttons[highlighted].click()
        review._legend_buttons[highlighted].click()  # repeated clicks do not hide a curve
        self.assertEqual(review.selected, highlighted)
        self.assertIn('Highlighted:', review.status.value)
        self.assertIn('tw-review-highlighted', review._legend_buttons[highlighted]._dom_classes)
        self.assertNotIn('tw-review-highlighted', review._legend_buttons[rows[0]['id']]._dom_classes)
        for control in review.markers.values():
            control.value = True
        markers = [t for t in figure.data if t.meta['kind'] == 'marker']
        self.assertEqual(len(markers), 9)
        partial = {t.meta['property']: t for t in markers if t.meta['id'] == highlighted}
        self.assertEqual(partial['EL'].marker.symbol, 'x-open')
        self.assertFalse(partial['EL'].meta['eligible'])
        self.assertIn('Excluded from analysis', partial['EL'].hovertemplate)
        self.assertEqual(partial['YS'].marker.symbol, 'circle')
        self.assertTrue(partial['YS'].meta['eligible'])
        self.assertTrue(all(t.visible is True for t in figure.data))
        review.markers['UTS'].value = False
        self.assertFalse(any(t.meta.get('property') == 'UTS' for t in figure.data))
        self.assertIs(review.figure, figure)
        self.assertEqual(figure.layout.xaxis.range, (2., 12.))
        self.assertEqual(figure.layout.yaxis.range, (200., 900.))
        self.assertEqual(self.session.project, original_project)
        old_button = review._legend_buttons[highlighted]
        review.axis.value = 'time'
        self.assertTrue(review.markers['EL'].value)
        self.assertEqual(len(review.figure.data), 9)  # 3 curves + YS/EL per specimen
        review._legend_buttons[rows[0]['id']].click()
        old_button.click()
        self.assertEqual(review.selected, rows[0]['id'])  # stale callbacks cannot alter new view
        self.assertTrue(all(t.visible is True for t in review.figure.data))
        self.assertEqual(self.session.project, original_project)

    def test_review_marker_positions_respect_measured_rows_and_manual_endpoint(self):
        from tensile_fracture import fracture_endpoint
        record = self.session.group_review_records('Alloy A', self.session.graphs[0])[0]
        p, raw = record['_review_properties'], record['_acquisition']
        end = fracture_endpoint(record)
        strain_points = review_marker_points(record)
        time_points = review_marker_points(record, 'time')
        self.assertEqual(strain_points['YS'], (p['Yield strain (%)'], p['Yield (MPa)']))
        peak = int(np.argmax(raw['stress']))
        self.assertEqual(strain_points['UTS'], (raw['strain'][peak], raw['stress'][peak]))
        self.assertEqual(time_points['UTS'], (raw['time'][peak], raw['stress'][peak]))
        self.assertEqual(strain_points['EL'], (end['strain_pct'], end['stress_mpa']))
        self.assertEqual(time_points['EL'], (raw['time'][int(end['row_before'])-1], end['stress_mpa']))
        self.assertAlmostEqual(time_points['YS'][0], np.interp(p['Yield strain (%)'], raw['strain'], raw['time']))
        # The review uses the effective endpoint, including a saved manual choice.
        manual_row = 1601
        record = {**record, '_failure_override': {'row': manual_row, 'source_sha256': record['source_sha256']}}
        self.assertEqual(review_marker_points(record)['EL'],
                         (raw['strain'][manual_row-1], raw['stress'][manual_row-1]))
        self.assertEqual(review_marker_points(record, 'time')['EL'],
                         (raw['time'][manual_row-1], raw['stress'][manual_row-1]))

    def test_review_missing_coordinates_do_not_invent_markers(self):
        record = deepcopy(self.session.group_review_records('Alloy A', self.session.graphs[0])[0])
        record['_review_properties']['Yield (MPa)'] = np.nan
        peak = int(np.argmax(record['_acquisition']['stress']))
        record['_acquisition']['strain'][peak] = np.nan
        record['_acquisition']['time'][:] = np.nan
        with patch('tensile_group_review.fracture_endpoint', return_value={'status': 'unresolved'}):
            self.assertEqual(review_marker_points(record), {})
            self.assertEqual(review_marker_points(record, 'time'), {})

    def test_invalid_policy_rejected_and_global_graph_save_roundtrip(self):
        self.mode(2, 'after_uts')
        validate_project(self.project)
        bad = deepcopy(self.project)
        bad['specimen_data_modes']['Alloy A/coupon_2.csv']['mode'] = 'unknown'
        with self.assertRaises(ValueError):
            validate_project(bad)
        with redirect_stdout(io.StringIO()):
            app = TensileWorkbench(self.root)
            app._specimen_changed('Alloy A/coupon_2.csv', True, 'Synthetic', mode='after_uts')
        self.addCleanup(app.tables.clear)
        self.assertEqual(app.store.data['specimen_data_modes']['Alloy A/coupon_2.csv']['mode'], 'after_uts')
        app.graph.value = '1'
        frames = app.session.property_tables(app.state(), app._current()['definition'])
        self.assertEqual(frames['tensile_samples'].iloc[1]['Data use mode'], 'after_uts')
        app._specimen_changed('Alloy A/coupon_2.csv', True, '', scope='graph', mode='all')
        app.graph.value = '0'
        frames = app.session.property_tables(app.state(), app._current()['definition'])
        self.assertEqual(frames['tensile_samples'].iloc[1]['Data use mode'], 'after_uts')

    def test_exports_keep_policy_and_independent_landmark_counts(self):
        self.mode(2, 'after_uts')
        with redirect_stdout(io.StringIO()):
            path = self.session.export_properties(self.state, self.session.graphs[0])
        specimens = pd.read_excel(path / 'Selection_test_results.xlsx', sheet_name='Specimens')
        self.assertEqual(specimens.iloc[1]['Data use'], DATA_MODES['after_uts'])
        self.assertTrue(np.isfinite(specimens.iloc[1]['Elongation (%) · Calc']))
        self.assertIn('Failure elongation', specimens.iloc[1]['Excluded properties'])
        result = self.session.render({**self.state, 'family': 'landmark', 'show_individuals': True})
        self.assertEqual(len(result['export_records']['Alloy A']), 2)
        export_path = self.root / 'synthetic_curves.xlsx'
        export_curves([result], self.session.engine, export_path)
        book = pd.ExcelFile(export_path)
        checks = pd.read_excel(book, sheet_name='Curve checks')
        yield_point = checks.loc[checks['Landmark'].eq('yield')].iloc[0]
        self.assertEqual(yield_point['Stress n'], 3)
        failure_point = checks.loc[checks['Landmark'].eq('failure')].iloc[0]
        self.assertEqual(failure_point['Strain n'], 2)

    def test_explicit_partial_exclusion_avoids_broken_fracture_blocking_strength_plots(self):
        self.mode(2, 'after_yield')
        record = self.session._load('Alloy A')[1]
        record['source_sha256'] = 'synthetic-no-unloading'
        stress = record['_acquisition']['stress']
        stress[np.argmax(stress):] = np.max(stress)
        record['_acquisition']['force'] = stress.copy()
        record['stress_mpa'] = record['raw_stress_mpa'] = stress[record['_measurement_indices']]
        record.pop('_property_cache', None)
        record.pop('_fracture_detection', None)
        from tensile_fracture import fracture_endpoint, endpoint_available
        self.assertFalse(endpoint_available(fracture_endpoint(record)))
        self.assertNotIn(record['specimen_id'], self.models()['landmark']['shape_specimens'])

    def test_dropdown_messages_save_mode_and_reject_stale_or_invalid_messages(self):
        received = []
        table = SpecimenTable(on_selection=lambda *args: received.append(args))
        self.addCleanup(table.close)
        table.context, table.rows = 'fresh', [{'id': 'A/specimen.csv'}]
        message = {'context': 'fresh', 'type': 'selection', 'id': 'A/specimen.csv',
                   'included': True, 'mode': 'after_uts', 'reason': 'AVE lost', 'scope': 'global'}
        table._receive(None, message, [])
        self.assertEqual(received[0][-1], 'after_uts')
        for change in ({'context': 'old'}, {'mode': []}, {'mode': 'exclude'}, {'id': 'wrong'}):
            table._receive(None, {**message, **change}, [])
        self.assertEqual(len(received), 1)

    def test_gauge_reconstruction_skips_partial_specimens_without_changing_group_basis(self):
        self.mode(1, 'after_uts')
        project = deepcopy(self.session.project)
        spec = project['graphs'][0]['definition']
        spec['gauge_reconstruction'] = {'Alloy A': {'enabled': True, 'target_gauge_mm': 20.}}
        self.session.set_project(project)
        match = self.session.instron.match
        def dimensions(group, record):
            reference = match(group, record)
            return {**reference, 'values': {**reference['values'], 'gauge': 25.}}
        with patch.object(self.session.instron, 'match', side_effect=dimensions):
            frames = self.frames()
        samples = frames['tensile_samples']
        self.assertTrue(np.isnan(samples.iloc[0]['Reconstructed EL (%)']))
        self.assertEqual(samples.iloc[0]['EL plot source'], 'Excluded')
        self.assertTrue(np.isfinite(samples.iloc[1]['Reconstructed EL (%)']))
        self.assertEqual(frames['tensile_summary'].iloc[0]['Elongation basis'], 'Estimated standard gauge')

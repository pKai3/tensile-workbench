"""Bundled loading artwork and real Voilà streaming template, without data/kernels."""
import asyncio
from pathlib import Path
import unittest
from xml.etree import ElementTree

import nbformat
from voila.configuration import VoilaConfiguration
from voila.exporter import VoilaExporter

from tensile_activity import BusyOverlay
from workbench_server import WorkbenchVoila


ROOT = Path(__file__).resolve().parents[1]


class LoadingArtworkTests(unittest.TestCase):
    def test_overlay_uses_shared_self_contained_svg(self):
        artwork = (ROOT / 'web/static/tensile-loading.svg').read_text(encoding='utf-8')
        svg = ElementTree.fromstring(artwork)
        self.assertEqual(svg.attrib['viewBox'], '0 0 260 160')
        self.assertEqual(svg.attrib['aria-hidden'], 'true')
        self.assertEqual(svg.attrib['focusable'], 'false')
        overlay = BusyOverlay()
        self.addCleanup(overlay.close)
        self.assertEqual(overlay.loader_svg, artwork)
        self.assertIn("model.get('loader_svg')", BusyOverlay._esm)
        self.assertIn("setAttribute('role','status')", BusyOverlay._esm)
        self.assertIn('prefers-reduced-motion:reduce', artwork)
        self.assertIn('animation:none !important', artwork)
        self.assertIn('tw-coupon-intact', artwork)
        self.assertIn('tw-coupon-break', artwork)
        self.assertIn('3.4s', artwork)
        self.assertNotIn('<script', artwork)
        self.assertNotIn('href=', artwork)
        self.assertNotIn('url(', artwork)
        self.assertNotIn('tw-busy-spin', BusyOverlay._css)

    def test_real_template_streams_coupon_before_starting_kernel_and_keeps_finish(self):
        app = WorkbenchVoila()
        app.voila_configuration = VoilaConfiguration()
        app.setup_template_dirs()
        self.assertEqual(app.template_paths[:2], [str(ROOT / 'web/templates'), str(ROOT / 'web')])
        exporter = VoilaExporter(template_paths=app.template_paths, template_name='lab',
                                 base_url='/nested/workbench/')
        chunks = []

        async def start(nb):
            # Startup artwork must reach the browser before notebook execution.
            partial = ''.join(chunks)
            self.assertIn('class="tw-coupon"', partial)
            self.assertIn('id="loading_text"', partial)
            return 'synthetic-kernel'

        async def cells(nb, kernel):
            for cell in nb.cells:
                yield cell

        async def render():
            async for chunk, _ in exporter.generate_from_notebook_node(
                nbformat.v4.new_notebook(),
                resources=dict(base_url='/nested/workbench/', theme='light', labextensions=[]),
                extra_context=dict(frontend='voila', main_js='voila.js', kernel_start=start,
                                   cell_generator=cells, progressive_rendering=False),
                page_config=dict(fullStaticUrl='/nested/workbench/voila/static'),
            ):
                chunks.append(chunk)

        asyncio.run(render())
        html = ''.join(chunks)
        self.assertEqual(html.count('id="loading"'), 1)
        self.assertEqual(html.count('class="tw-coupon"'), 1)
        self.assertIn('<title>Tensile Workbench</title>', html)
        self.assertIn('role="status" aria-live="polite"', html)
        self.assertIn('window.voila_finish();', html)
        self.assertIn('window.display_cells = function()', html)
        self.assertIn('voila-skeleton-avatar', html)
        self.assertNotIn('<svg class="spinner"', html)


if __name__ == '__main__':
    unittest.main()

"""Bounded recorded Pasa import; fixtures are synthetic and never run research."""
import json
import tempfile
import unittest
from pathlib import Path
from test_sdk import PROJECT, PNG, module


class RecordedPasaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.adapter = module('pasa_adapter')
        self.renders = self.root / 'surfels/case/renders'
        self.renders.mkdir(parents=True)
        (self.root / 'run_manifest.json').write_text(json.dumps({'status':'complete', 'parameters':{
            'run_name':'synthetic fixture', 'names':['case'], 'methods':['surfels'], 'split':'test', 'iterations':3}}))
        for view in ('000', '003'):
            for kind in ('input', 'render'):
                (self.renders / (view + '_' + kind + '.png')).write_bytes(PNG)
        self.diagnostics = {'scope':'training views, not held-out', 'views':[
            {'view':'000', 'foreground_psnr':20.0, 'full_image_psnr':22.0, 'foreground_coverage':0.9, 'surface_points':10},
            {'view':'003', 'foreground_psnr':25.0, 'full_image_psnr':24.0, 'foreground_coverage':0.95, 'surface_points':12}]}
        self.write_diagnostics()

    def tearDown(self):
        self.temp.cleanup()

    def write_diagnostics(self):
        (self.renders / 'diagnostics.json').write_text(json.dumps(self.diagnostics))

    def test_default_import_stays_bounded_to_previous_view(self):
        bundle = self.adapter.build_page(self.root, project=PROJECT).bundle()
        render = next(s for s in bundle['sections'] if s['key']=='render-0-0')
        self.assertEqual(len(render['blocks']), 1)
        self.assertFalse(any(s['key'].startswith('diagnostics') for s in bundle['sections']))

    def test_selected_view_pairs_and_training_diagnostics_keep_evaluation_unconfirmed(self):
        bundle = self.adapter.build_page(self.root, project=PROJECT, selected_views=['000','003'], include_diagnostics=True).bundle()
        renders = [s for s in bundle['sections'] if s['key'].startswith('render-')]
        self.assertEqual([s['key'] for s in renders], ['render-0-0-000','render-0-0-003'])
        self.assertTrue(all(len(s['blocks'])==2 for s in renders))
        diagnostic = next(s for s in bundle['sections'] if s['key']=='diagnostics-0-0')
        self.assertIn('training views, not held-out', diagnostic['blocks'][0]['text'])
        self.assertEqual(diagnostic['blocks'][1]['rows'][1][2],25.0)
        self.assertEqual(bundle['evidence']['evaluation_status'],'not_run')
        self.assertIn('held-out', diagnostic['blocks'][-1]['text'])

    def test_unselected_diagnostic_views_do_not_enter_bundle(self):
        bundle = self.adapter.build_page(self.root, project=PROJECT, selected_views=['003'], include_diagnostics=True).bundle()
        diagnostic = next(s for s in bundle['sections'] if s['key']=='diagnostics-0-0')
        self.assertEqual(len(diagnostic['blocks'][1]['rows']),1)
        self.assertEqual(diagnostic['blocks'][1]['rows'][0][0],'003')

    def test_nonfinite_diagnostic_is_rejected(self):
        self.diagnostics['views'][0]['foreground_psnr'] = float('nan')
        self.write_diagnostics()
        with self.assertRaisesRegex(ValueError,'finite'):
            self.adapter.build_page(self.root, project=PROJECT, selected_views=['000'], include_diagnostics=True)

    def test_view_path_escape_and_duplicates_are_rejected(self):
        for views in (['../'], ['003','003'], []):
            with self.subTest(views=views), self.assertRaises(ValueError):
                self.adapter.build_page(self.root, project=PROJECT, selected_views=views)


if __name__ == '__main__':
    unittest.main()

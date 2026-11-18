# -*- coding: utf-8 -*-
"""Anàlisi + reparació + comparació de punta a punta amb un disc sintètic."""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from album import make_album, music, to_cd, FS  # noqa: E402
from premaster.project import Project, import_vtracklist  # noqa: E402
from premaster.analysis import analyze, suggested_actions  # noqa: E402
from premaster.repair import run_repair, RepairSettings, default_out_dir  # noqa: E402
from premaster.compare import compare_files  # noqa: E402


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _project(self):
        files = make_album(self.d, seconds=6.0)
        p = Project()
        for s, fl in files.items():
            p.add_files(s, fl)
        return p

    def test_analysis_flags(self):
        res = analyze(self._project())
        by = {t.pos: t for t in res.tracks}
        self.assertEqual(by["A01"].status["sib"], "red")
        self.assertIn(by["A04"].status["sib"], ("yellow", "red"))
        self.assertEqual(by["A03"].status["corr"], "red")
        self.assertEqual(by["B02"].status["fs"], "red")
        self.assertTrue(by["B03"].inner and by["B03"].is_last)
        self.assertEqual(by["A02"].status["sib"], "ok")
        self.assertTrue(all(t.status["tp"] == "red" for t in res.tracks))

    def test_repair(self):
        res = analyze(self._project())
        plan = {t.id: suggested_actions(t, res.limits) for t in res.tracks}
        out = default_out_dir(res)
        rr = run_repair(res, plan, RepairSettings(out, tp_target=-3.0))
        self.assertAlmostEqual(rr.album_tp_after, -3.0, delta=0.15)
        self.assertLess(rr.gain_db, 0)
        by = {r.t.pos: r for r in rr.tracks}
        self.assertGreater(by["A03"].m_after["corr150"], 0.95)
        self.assertGreater(by["B03"].m_after["corr150"], 0.95)
        self.assertLessEqual(by["A01"].m_after["sibilance_db"], -8.5)
        for r in rr.tracks:
            self.assertTrue(os.path.isfile(r.out_path))
            self.assertEqual(sf.info(r.out_path).subtype, "PCM_16")   # «igual que l'original»
        # Els originals no es toquen
        self.assertTrue(all(os.path.isfile(t.path) for t in res.tracks))

    def test_bit_exact_copy_when_nothing_to_do(self):
        x = to_cd(music(5, 9), peak_db=-6.0)
        p1 = os.path.join(self.d, "A01_ok.wav")
        sf.write(p1, x, FS, subtype="PCM_24")
        p = Project()
        p.add_files("A", [p1])
        res = analyze(p)
        plan = {t.id: {"declip": False, "bass_mono": False, "deess": False} for t in res.tracks}
        rr = run_repair(res, plan, RepairSettings(os.path.join(self.d, "out"), tp_target=-3.0))
        self.assertEqual(rr.gain_db, 0.0)
        self.assertTrue(rr.tracks[0].bit_exact)
        self.assertEqual(md5(p1), md5(rr.tracks[0].out_path))

    def test_float_to_24(self):
        x = to_cd(music(4, 3), peak_db=-6.0)
        p1 = os.path.join(self.d, "A01_float.wav")
        sf.write(p1, x, FS, subtype="FLOAT")
        p = Project()
        p.add_files("A", [p1])
        res = analyze(p)
        rr = run_repair(res, {}, RepairSettings(os.path.join(self.d, "out")))
        self.assertEqual(sf.info(rr.tracks[0].out_path).subtype, "PCM_24")

    def test_out_dir_guard(self):
        res = analyze(self._project())
        with self.assertRaises(ValueError):
            run_repair(res, {}, RepairSettings(self.d))

    def test_compare(self):
        x = to_cd(music(5, 4))
        a = os.path.join(self.d, "a.wav")
        b = os.path.join(self.d, "b.wav")
        c = os.path.join(self.d, "c.wav")
        sf.write(a, x, FS, subtype="PCM_16")
        shutil.copy(a, b)
        sf.write(c, np.vstack([np.zeros((50, 2)), x * 0.5]), FS, subtype="PCM_24")
        r = compare_files(a, b)
        self.assertTrue(r.identical_bytes)
        r2 = compare_files(a, c)
        self.assertFalse(r2.identical_pcm)
        self.assertEqual(r2.null["lag"], 50)
        self.assertAlmostEqual(r2.null["gain_db"], 6.02, delta=0.05)
        self.assertIn("mismo audio", r2.conclusion)

    def test_import_vtracklist(self):
        import json
        files = make_album(self.d, seconds=2.0)
        proj = {"app": "VinylTracklist", "artist": "X", "album": "Y",
                "sides": [{"name": "A", "tracks": [{"path": "/no/existeix.wav",
                                                    "relpath": os.path.basename(files["A"][1]), "title": "Títol"}]},
                          {"name": "B", "tracks": [{"path": files["B"][0], "title": None}]}]}
        pp = os.path.join(self.d, "disc.vtracklist")
        with open(pp, "w", encoding="utf-8") as f:
            json.dump(proj, f)
        p = import_vtracklist(pp)
        self.assertEqual(p.sides["A"][0].title, "Títol")
        self.assertTrue(p.sides["A"][0].header.ok)
        self.assertEqual(len(p.sides["B"]), 1)


if __name__ == "__main__":
    unittest.main()

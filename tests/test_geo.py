import tempfile
import unittest
from pathlib import Path
from unittest import mock

from geo import service as geo


def fake_fetch(url, params=None, headers=None):
    if url.endswith("/localidades/estados"):
        return [{"sigla": "SC", "nome": "Santa Catarina"}, {"sigla": "RS", "nome": "Rio Grande do Sul"}]
    if "nominatim" in url:
        return [
            {"lat": "-28.47", "lon": "-49.0", "display_name": "Rua A, Tubarão"},
            {"lat": "40.0", "lon": "-3.7", "display_name": "Madrid, fora do Brasil"},
        ]
    raise AssertionError("URL inesperada: " + url)


class GeoServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = geo.CACHE_DIR
        geo.CACHE_DIR = Path(self._tmp.name)  # nunca toca no cache real
        geo._memory.clear()

    def tearDown(self):
        geo.CACHE_DIR = self._old_dir
        geo._memory.clear()
        self._tmp.cleanup()

    def test_validation_rejects_bad_input_before_any_request(self):
        with mock.patch.object(geo, "_fetch", side_effect=AssertionError("não deveria consultar a rede")):
            for bad in ("", "1234", "12345678", "abc", "4218707; DROP"):
                with self.assertRaises(ValueError, msg=bad):
                    geo.valid_ibge_id(bad)
            for bad in ("S", "SCX", "1", "../"):
                with self.assertRaises(ValueError, msg=bad):
                    geo.valid_uf(bad)
        self.assertEqual(geo.valid_ibge_id(" 4218707 "), 4218707)

    def test_uf_must_exist(self):
        with mock.patch.object(geo, "_fetch", side_effect=fake_fetch):
            self.assertEqual(geo.valid_uf("sc"), "SC")
            with self.assertRaises(ValueError):
                geo.valid_uf("ZZ")

    def test_bbox_of_polygon_and_multipolygon(self):
        polygon = {"type": "Polygon", "coordinates": [[[-49.2, -28.6], [-48.9, -28.6], [-48.9, -28.3], [-49.2, -28.3]]]}
        self.assertEqual(geo._bbox(polygon), [-28.6, -49.2, -28.3, -48.9])
        multi = {"type": "MultiPolygon", "coordinates": [polygon["coordinates"], [[[-50.0, -29.0], [-49.9, -29.0], [-49.9, -28.9]]]]}
        self.assertEqual(geo._bbox(multi), [-29.0, -50.0, -28.3, -48.9])

    def test_in_brazil(self):
        self.assertTrue(geo.in_brazil(-28.47, -49.0))
        self.assertFalse(geo.in_brazil(40.0, -3.7))
        self.assertFalse(geo.in_brazil(0.0, 0.0))

    def test_geocode_drops_results_outside_brazil_and_validates_query(self):
        with mock.patch.object(geo, "_fetch", side_effect=fake_fetch):
            results = geo.geocode("Rua A, 100")
            self.assertEqual([r["label"] for r in results], ["Rua A, Tubarão"])
            with self.assertRaises(ValueError):
                geo.geocode("ab")

    def test_service_down_without_cache_raises_unavailable(self):
        import requests

        with mock.patch.object(geo, "_fetch", side_effect=requests.ConnectionError()):
            with self.assertRaises(geo.GeoUnavailable):
                geo.estados()

    def test_stale_cache_is_used_when_service_is_down(self):
        import requests

        with mock.patch.object(geo, "_fetch", side_effect=fake_fetch):
            geo.estados()
        geo._memory.clear()
        with mock.patch.object(geo, "_fetch", side_effect=requests.ConnectionError()), mock.patch.object(
            geo, "STATIC_TTL", -1
        ):
            self.assertEqual(len(geo.estados()), 2)  # expirou, mas serve a cópia antiga


if __name__ == "__main__":
    unittest.main()

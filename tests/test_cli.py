import json
import tempfile
import unittest

from sdn_path_tracer.core import format_trace
from sdn_path_tracer.trace_cli import build_trace_url, save_trace


class TraceCliTests(unittest.TestCase):
    def test_build_trace_url_encodes_inputs(self):
        url = build_trace_url("http://127.0.0.1:8080/", "h1", "10.0.0.4")
        self.assertEqual(url, "http://127.0.0.1:8080/trace?src=h1&dst=10.0.0.4")

    def test_save_trace_writes_json(self):
        trace = {
            "src_host": "h1",
            "dst_host": "h4",
            "path": ["h1", "s1", "s2", "s4", "h4"],
            "switch_hops": ["s1", "s2", "s4"],
            "flow_rules": [],
            "timestamp": "2026-04-17T00:00:00+00:00",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = f"{temp_dir}/trace.json"
            save_trace(trace, output_path)
            with open(output_path, "r", encoding="utf-8") as handle:
                written = json.loads(handle.read())
        self.assertEqual(written["src_host"], "h1")
        self.assertEqual(written["dst_host"], "h4")

    def test_rendered_trace_contains_route(self):
        trace = {
            "src_host": "h1",
            "dst_host": "h4",
            "path": ["h1", "s1", "s2", "s4", "h4"],
            "switch_hops": ["s1", "s2", "s4"],
            "flow_rules": [{"switch": "s1", "in_port": 1, "out_port": 2, "match": {"eth_src": "a"}}],
            "timestamp": "2026-04-17T00:00:00+00:00",
        }
        rendered = format_trace(trace)
        self.assertIn("Packet path:", rendered)
        self.assertIn("h1 -> s1 -> s2 -> s4 -> h4", rendered)


if __name__ == "__main__":
    unittest.main()

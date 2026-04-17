import unittest

from sdn_path_tracer.core import PathTracerState, TraceError, format_trace


class PathTracerStateTests(unittest.TestCase):
    def setUp(self):
        known_hosts = {
            "h1": {"ip": "10.0.0.1", "mac": "00:00:00:00:00:01"},
            "h4": {"ip": "10.0.0.4", "mac": "00:00:00:00:00:04"},
        }
        self.state = PathTracerState(known_hosts)
        self.state.add_link(1, 11, 2, 21)
        self.state.add_link(1, 12, 3, 31)
        self.state.add_link(2, 24, 4, 42)
        self.state.add_link(3, 34, 4, 43)
        self.state.learn_host("h1", switch_dpid=1, port_no=1)
        self.state.learn_host("h4", switch_dpid=4, port_no=4)

    def test_shortest_path_prefers_deterministic_route(self):
        self.assertEqual(self.state.shortest_path(1, 4), [1, 2, 4])

    def test_flow_rule_tracking_is_stored_by_pair(self):
        self.state.record_flow_rule("h1", "h4", 1, 1, 11, {"eth_src": "a", "eth_dst": "b"})
        rules = self.state.get_flow_rules_for_pair("h1", "h4")
        self.assertIn(1, rules)
        self.assertEqual(rules[1].out_port, 11)

    def test_build_trace_returns_path_and_rules(self):
        self.state.record_flow_rule("h1", "h4", 1, 1, 11, {"eth_src": "a", "eth_dst": "b"})
        self.state.record_flow_rule("h1", "h4", 2, 21, 24, {"eth_src": "a", "eth_dst": "b"})
        self.state.record_flow_rule("h1", "h4", 4, 42, 4, {"eth_src": "a", "eth_dst": "b"})
        trace = self.state.build_trace("h1", "h4")
        self.assertEqual(trace["path"], ["h1", "s1", "s2", "s4", "h4"])
        self.assertEqual(trace["switch_hops"], ["s1", "s2", "s4"])
        self.assertEqual(len(trace["flow_rules"]), 3)
        self.assertIn("timestamp", trace)

    def test_format_trace_is_readable(self):
        self.state.record_flow_rule("h1", "h4", 1, 1, 11, {"eth_src": "a", "eth_dst": "b"})
        self.state.record_flow_rule("h1", "h4", 2, 21, 24, {"eth_src": "a", "eth_dst": "b"})
        self.state.record_flow_rule("h1", "h4", 4, 42, 4, {"eth_src": "a", "eth_dst": "b"})
        trace = self.state.build_trace("h1", "h4")
        rendered = format_trace(trace)
        self.assertIn("h1 -> s1 -> s2 -> s4 -> h4", rendered)
        self.assertIn("s2: in_port=21 out_port=24", rendered)

    def test_trace_fails_before_destination_is_discovered(self):
        state = PathTracerState({"h1": {"ip": "10.0.0.1", "mac": "00:00:00:00:00:01"}, "h2": {"ip": "10.0.0.2", "mac": "00:00:00:00:00:02"}})
        state.add_link(1, 10, 2, 20)
        state.learn_host("h1", switch_dpid=1, port_no=1)
        with self.assertRaises(TraceError) as ctx:
            state.build_trace("h1", "h2")
        self.assertIn("has not been discovered yet", str(ctx.exception))

    def test_trace_fails_when_flow_rules_are_missing(self):
        with self.assertRaises(TraceError) as ctx:
            self.state.build_trace("h1", "h4")
        self.assertIn("Generate traffic first", str(ctx.exception))

    def test_host_location_is_not_overwritten_by_transit_packet(self):
        state = PathTracerState({"h1": {"ip": "10.0.0.1", "mac": "00:00:00:00:00:01"}})
        state.learn_host("h1", switch_dpid=1, port_no=1)
        state.learn_host(mac="00:00:00:00:00:01", switch_dpid=2, port_no=2)
        host = state.get_host("h1")
        self.assertEqual(host.switch_dpid, 1)
        self.assertEqual(host.port_no, 1)

    def test_known_hosts_can_start_with_fixed_attachment(self):
        state = PathTracerState(
            {"h4": {"ip": "10.0.0.4", "mac": "00:00:00:00:00:04", "switch": 4, "port": 1}}
        )
        host = state.get_host("h4")
        self.assertEqual(host.switch_dpid, 4)
        self.assertEqual(host.port_no, 1)


if __name__ == "__main__":
    unittest.main()

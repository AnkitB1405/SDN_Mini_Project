import unittest
from unittest.mock import patch

try:
    from sdn_path_tracer.controller import DEMO_LINKS, PathTracerController
    from sdn_path_tracer.core import TraceError
except ModuleNotFoundError as exc:
    PathTracerController = None
    TraceError = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(PathTracerController is None, f"os_ken is unavailable: {IMPORT_ERROR}")
class ControllerLogicTests(unittest.TestCase):
    def test_demo_topology_seed_matches_mininet_layout(self):
        self.assertEqual(
            DEMO_LINKS,
            [
                (1, 2, 2, 2),
                (1, 3, 3, 2),
                (2, 3, 4, 2),
                (3, 3, 4, 3),
                (2, 4, 3, 4),
            ],
        )

    def test_broadcast_packet_is_flooded(self):
        eth = type("Eth", (), {"dst": "ff:ff:ff:ff:ff:ff"})()
        self.assertTrue(PathTracerController._should_flood_packet(eth))

    def test_unicast_packet_is_not_forced_to_flood(self):
        eth = type("Eth", (), {"dst": "00:00:00:00:00:04"})()
        self.assertFalse(PathTracerController._should_flood_packet(eth))

    def test_arp_packet_is_detected(self):
        pkt = type("Pkt", (), {"get_protocol": lambda self, protocol: object()})()
        self.assertTrue(PathTracerController._is_arp_packet(pkt))

    def test_path_out_port_uses_live_topology(self):
        controller = PathTracerController()
        controller.state.add_link(1, 2, 2, 2)
        controller.state.add_link(2, 3, 4, 2)
        controller.state.learn_host("h1", switch_dpid=1, port_no=1)
        controller.state.learn_host("h4", switch_dpid=4, port_no=1)
        src_host = controller.state.get_host("h1")
        dst_host = controller.state.get_host("h4")
        self.assertEqual(controller._get_path_out_port(1, src_host, dst_host), 2)
        self.assertEqual(controller._get_path_out_port(2, src_host, dst_host), 3)
        self.assertEqual(controller._get_path_out_port(4, src_host, dst_host), 1)

    def test_path_out_port_is_available_from_demo_seed(self):
        controller = PathTracerController()
        self.assertEqual(
            controller._get_path_out_port(1, controller.state.get_host("h1"), controller.state.get_host("h4")),
            2,
        )

    def test_prepare_unicast_forwarding_returns_current_switch_out_port(self):
        controller = PathTracerController()
        controller.state.add_link(1, 2, 2, 2)
        controller.state.add_link(2, 3, 4, 2)
        controller.state.learn_host("h1", switch_dpid=1, port_no=1)
        controller.state.learn_host("h4", switch_dpid=4, port_no=1)
        controller._install_bidirectional_path = lambda src_host, dst_host: None
        src_host = controller.state.get_host("h1")
        dst_host = controller.state.get_host("h4")
        self.assertEqual(controller._prepare_unicast_forwarding(2, src_host, dst_host), 3)

    def test_demo_hosts_are_seeded_on_edge_ports(self):
        controller = PathTracerController()
        self.assertEqual(controller.state.get_host("h1").switch_dpid, 1)
        self.assertEqual(controller.state.get_host("h1").port_no, 1)
        self.assertEqual(controller.state.get_host("h4").switch_dpid, 4)
        self.assertEqual(controller.state.get_host("h4").port_no, 1)

    @patch("sdn_path_tracer.controller.get_link", return_value=[])
    @patch("sdn_path_tracer.controller.get_switch")
    def test_refresh_topology_falls_back_to_demo_links(self, mock_get_switch, mock_get_link):
        controller = PathTracerController()
        mock_get_switch.return_value = [type("Switch", (), {"dp": type("DP", (), {"id": dpid})()})() for dpid in (1, 2, 3, 4)]
        controller._refresh_topology()
        self.assertEqual(controller._get_path_out_port(1, controller.state.get_host("h1"), controller.state.get_host("h4")), 2)


if __name__ == "__main__":
    unittest.main()

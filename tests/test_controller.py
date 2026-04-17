import unittest

try:
    from sdn_path_tracer.controller import DEMO_LINKS, PathTracerController
except ModuleNotFoundError as exc:
    PathTracerController = None
    DEMO_LINKS = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(PathTracerController is None, f"os_ken is unavailable: {IMPORT_ERROR}")
class ControllerLogicTests(unittest.TestCase):
    def test_broadcast_packet_is_flooded(self):
        eth = type("Eth", (), {"dst": "ff:ff:ff:ff:ff:ff"})()
        self.assertTrue(PathTracerController._should_flood_packet(eth))

    def test_unicast_packet_is_not_forced_to_flood(self):
        eth = type("Eth", (), {"dst": "00:00:00:00:00:04"})()
        self.assertFalse(PathTracerController._should_flood_packet(eth))

    def test_arp_packet_is_detected(self):
        pkt = type("Pkt", (), {"get_protocol": lambda self, protocol: object()})()
        self.assertTrue(PathTracerController._is_arp_packet(pkt))

    def test_seeded_demo_links_match_mininet_port_layout(self):
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


if __name__ == "__main__":
    unittest.main()

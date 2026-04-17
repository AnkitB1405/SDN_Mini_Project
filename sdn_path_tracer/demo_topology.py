from __future__ import annotations

import argparse

from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.topo import Topo


class DemoPathTracerTopo(Topo):
    def build(self):
        s1 = self.addSwitch("s1", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", protocols="OpenFlow13")
        s3 = self.addSwitch("s3", protocols="OpenFlow13")
        s4 = self.addSwitch("s4", protocols="OpenFlow13")

        self.addHost("h1", ip="10.0.0.1/24", mac="00:00:00:00:00:01")
        self.addHost("h2", ip="10.0.0.2/24", mac="00:00:00:00:00:02")
        self.addHost("h3", ip="10.0.0.3/24", mac="00:00:00:00:00:03")
        self.addHost("h4", ip="10.0.0.4/24", mac="00:00:00:00:00:04")

        self.addLink("h1", s1)
        self.addLink("h2", s2)
        self.addLink("h3", s3)
        self.addLink("h4", s4)

        self.addLink(s1, s2)
        self.addLink(s1, s3)
        self.addLink(s2, s4)
        self.addLink(s3, s4)
        self.addLink(s2, s3)


def configure_demo_hosts(net: Mininet) -> None:
    for host in net.hosts:
        intf = host.defaultIntf()
        host.cmd(f"ethtool -K {intf} rx off tx off sg off tso off ufo off gso off gro off lro off >/dev/null 2>&1")
        host.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=1 >/dev/null 2>&1")
        host.cmd("sysctl -w net.ipv6.conf.default.disable_ipv6=1 >/dev/null 2>&1")
        host.cmd("sysctl -w net.ipv6.conf.lo.disable_ipv6=1 >/dev/null 2>&1")
        host.cmd(f"sysctl -w net.ipv6.conf.{intf}.disable_ipv6=1 >/dev/null 2>&1")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Mininet demo topology for the SDN path tracer.")
    parser.add_argument("--controller-ip", default="127.0.0.1")
    parser.add_argument("--controller-port", type=int, default=6653)
    args = parser.parse_args()

    topo = DemoPathTracerTopo()
    net = Mininet(topo=topo, build=False, switch=OVSKernelSwitch, controller=None, autoSetMacs=False)
    net.addController(
        "c0",
        controller=RemoteController,
        ip=args.controller_ip,
        port=args.controller_port,
    )
    net.build()
    net.start()
    configure_demo_hosts(net)
    print("Topology started. Try: h1 ping -c 2 h4")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    main()

from __future__ import annotations

import argparse
import logging

from os_ken import cfg
from os_ken.base import app_manager

import os_ken.controller.controller
import os_ken.topology.switches
import sdn_path_tracer.controller


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SDN path tracer on top of OS-Ken.")
    parser.add_argument("--ofp-tcp-listen-port", type=int, default=6653)
    parser.add_argument("--trace-api-host", default="127.0.0.1")
    parser.add_argument("--trace-api-port", type=int, default=8080)
    parser.add_argument("--observe-links", action="store_true", default=True)
    parser.add_argument("--quiet-observe-links", action="store_false", dest="observe_links")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    conf = cfg.CONF
    conf.set_override("ofp_tcp_listen_port", args.ofp_tcp_listen_port)
    conf.set_override("observe_links", args.observe_links)
    conf.set_override("trace_api_host", args.trace_api_host)
    conf.set_override("trace_api_port", args.trace_api_port)

    app_manager.AppManager.run_apps(["sdn_path_tracer.controller"])


if __name__ == "__main__":
    main()

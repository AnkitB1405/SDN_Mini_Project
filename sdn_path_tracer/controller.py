from __future__ import annotations

import json

from ryu.app.wsgi import ControllerBase, Response, WSGIApplication, route
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib.packet import arp, ethernet, ether_types, ipv4, packet
from ryu.ofproto import ofproto_v1_3
from ryu.topology import event
from ryu.topology.api import get_link, get_switch

try:
    from sdn_path_tracer.core import PathTracerState, TraceError, format_trace
except ModuleNotFoundError:
    from core import PathTracerState, TraceError, format_trace

TRACE_APP_INSTANCE = "trace_app_instance"

DEMO_HOSTS = {
    "h1": {"ip": "10.0.0.1", "mac": "00:00:00:00:00:01"},
    "h2": {"ip": "10.0.0.2", "mac": "00:00:00:00:00:02"},
    "h3": {"ip": "10.0.0.3", "mac": "00:00:00:00:00:03"},
    "h4": {"ip": "10.0.0.4", "mac": "00:00:00:00:00:04"},
}


class PathTraceController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super().__init__(req, link, data, **config)
        self.app = data[TRACE_APP_INSTANCE]

    @route("trace", "/trace", methods=["GET"])
    def trace(self, req, **kwargs):
        src = req.params.get("src")
        dst = req.params.get("dst")
        pretty = req.params.get("pretty", "0") == "1"
        if not src or not dst:
            return Response(
                status=400,
                content_type="application/json",
                body=json.dumps({"error": "Both src and dst query parameters are required."}),
            )
        try:
            trace = self.app.state.build_trace(src, dst)
            payload = trace if not pretty else {"trace": trace, "text": format_trace(trace)}
            return Response(content_type="application/json", body=json.dumps(payload, indent=2))
        except TraceError as exc:
            return Response(status=404, content_type="application/json", body=json.dumps({"error": str(exc)}))


class PathTracerController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {"wsgi": WSGIApplication}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = PathTracerState(DEMO_HOSTS)
        self.datapaths = {}
        wsgi = kwargs["wsgi"]
        wsgi.register(PathTraceController, {TRACE_APP_INSTANCE: self})

    def _refresh_topology(self) -> None:
        switch_list = get_switch(self, None)
        link_list = get_link(self, None)
        self.state.reset_topology()
        for switch in switch_list:
            self.state.add_switch(switch.dp.id)
            self.datapaths[switch.dp.id] = switch.dp
        for link in link_list:
            self.state.add_link(
                link.src.dpid,
                link.src.port_no,
                link.dst.dpid,
                link.dst.port_no,
            )

    def _add_flow(self, datapath, priority, match, actions) -> None:
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        instructions = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions,
        )
        datapath.send_msg(mod)

    def _packet_out(self, datapath, msg, in_port, actions) -> None:
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)

    def _flood(self, datapath, msg, in_port) -> None:
        parser = datapath.ofproto_parser
        actions = [parser.OFPActionOutput(datapath.ofproto.OFPP_FLOOD)]
        self._packet_out(datapath, msg, in_port, actions)

    def _extract_ips(self, pkt: packet.Packet) -> tuple[str | None, str | None]:
        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            return arp_pkt.src_ip, arp_pkt.dst_ip
        ipv4_pkt = pkt.get_protocol(ipv4.ipv4)
        if ipv4_pkt:
            return ipv4_pkt.src, ipv4_pkt.dst
        return None, None

    def _learn_source_host(self, dpid: int, in_port: int, src_mac: str, src_ip: str | None):
        if self.state.is_switch_port(dpid, in_port):
            return self.state.get_host(src_mac)
        return self.state.learn_host(mac=src_mac, ip=src_ip, switch_dpid=dpid, port_no=in_port)

    def _resolve_destination_host(self, dst_mac: str, dst_ip: str | None):
        if dst_ip:
            host = self.state.get_host(dst_ip)
            if host:
                return host
        return self.state.get_host(dst_mac)

    def _build_match(self, parser, in_port: int, src_host, dst_host):
        match_fields = {
            "in_port": in_port,
            "eth_src": src_host.mac,
            "eth_dst": dst_host.mac,
        }
        return parser.OFPMatch(**match_fields), match_fields

    def _install_direction(self, src_host, dst_host) -> int:
        datapath = self.datapaths.get(src_host.switch_dpid)
        if datapath is None:
            raise TraceError(f"Switch s{src_host.switch_dpid} is not connected to the controller.")

        switch_path = self.state.shortest_path(src_host.switch_dpid, dst_host.switch_dpid)
        for index, dpid in enumerate(switch_path):
            current_dp = self.datapaths.get(dpid)
            if current_dp is None:
                raise TraceError(f"Switch s{dpid} is not connected to the controller.")
            parser = current_dp.ofproto_parser
            if index == 0:
                in_port = src_host.port_no
            else:
                previous_dpid = switch_path[index - 1]
                in_port = self.state.get_link_port(dpid, previous_dpid)
            if index == len(switch_path) - 1:
                out_port = dst_host.port_no
            else:
                next_dpid = switch_path[index + 1]
                out_port = self.state.get_link_port(dpid, next_dpid)

            match, match_fields = self._build_match(parser, in_port, src_host, dst_host)
            actions = [parser.OFPActionOutput(out_port)]
            self._add_flow(current_dp, 10, match, actions)
            self.state.record_flow_rule(src_host.name, dst_host.name, dpid, in_port, out_port, match_fields)

        return self.state.get_flow_rules_for_pair(src_host.name, dst_host.name)[switch_path[0]].out_port

    def _install_bidirectional_path(self, src_host, dst_host) -> int:
        first_out_port = self._install_direction(src_host, dst_host)
        self._install_direction(dst_host, src_host)
        return first_out_port

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        self.datapaths[datapath.id] = datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, 0, match, actions)

    @set_ev_cls(event.EventSwitchEnter)
    @set_ev_cls(event.EventLinkAdd)
    @set_ev_cls(event.EventLinkDelete)
    @set_ev_cls(event.EventSwitchLeave)
    def topology_change_handler(self, ev):
        self._refresh_topology()

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        self.datapaths[datapath.id] = datapath
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        src_ip, dst_ip = self._extract_ips(pkt)
        src_host = self._learn_source_host(datapath.id, in_port, eth.src, src_ip)
        dst_host = self._resolve_destination_host(eth.dst, dst_ip)

        if not src_host or not dst_host:
            self._flood(datapath, msg, in_port)
            return

        if dst_host.switch_dpid is None or dst_host.port_no is None:
            self._flood(datapath, msg, in_port)
            return

        try:
            out_port = self._install_bidirectional_path(src_host, dst_host)
        except TraceError as exc:
            self.logger.warning(str(exc))
            self._flood(datapath, msg, in_port)
            return

        actions = [parser.OFPActionOutput(out_port)]
        self._packet_out(datapath, msg, in_port, actions)

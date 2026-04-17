from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional


class TraceError(Exception):
    pass


@dataclass
class HostRecord:
    name: str
    mac: Optional[str] = None
    ip: Optional[str] = None
    switch_dpid: Optional[int] = None
    port_no: Optional[int] = None


@dataclass
class FlowRuleRecord:
    switch_dpid: int
    in_port: int
    out_port: int
    match: dict

    def as_dict(self) -> dict:
        return {
            "switch": f"s{self.switch_dpid}",
            "in_port": self.in_port,
            "out_port": self.out_port,
            "match": dict(self.match),
        }


class PathTracerState:
    def __init__(self, known_hosts: Optional[dict] = None) -> None:
        self.switches = set()
        self.adjacency: Dict[int, Dict[int, int]] = {}
        self.hosts_by_name: Dict[str, HostRecord] = {}
        self.name_by_mac: Dict[str, str] = {}
        self.name_by_ip: Dict[str, str] = {}
        self.flow_rules: Dict[tuple[str, str], Dict[int, FlowRuleRecord]] = {}
        self._dynamic_host_count = 1
        for host_name, details in (known_hosts or {}).items():
            self.learn_host(
                name=host_name,
                mac=details.get("mac"),
                ip=details.get("ip"),
                switch_dpid=details.get("switch"),
                port_no=details.get("port"),
            )

    @staticmethod
    def _normalize_mac(mac: Optional[str]) -> Optional[str]:
        return mac.lower() if mac else None

    def reset_topology(self) -> None:
        self.switches.clear()
        self.adjacency.clear()

    def add_switch(self, dpid: int) -> None:
        self.switches.add(dpid)
        self.adjacency.setdefault(dpid, {})

    def add_link(self, src_dpid: int, src_port: int, dst_dpid: int, dst_port: int) -> None:
        self.add_switch(src_dpid)
        self.add_switch(dst_dpid)
        self.adjacency[src_dpid][dst_dpid] = src_port
        self.adjacency[dst_dpid][src_dpid] = dst_port

    def is_switch_port(self, dpid: int, port_no: int) -> bool:
        return port_no in self.adjacency.get(dpid, {}).values()

    def _next_dynamic_name(self) -> str:
        name = f"host-{self._dynamic_host_count}"
        self._dynamic_host_count += 1
        return name

    def resolve_host_name(self, identifier: str) -> Optional[str]:
        if identifier in self.hosts_by_name:
            return identifier
        normalized_mac = self._normalize_mac(identifier)
        if normalized_mac in self.name_by_mac:
            return self.name_by_mac[normalized_mac]
        if identifier in self.name_by_ip:
            return self.name_by_ip[identifier]
        return None

    def get_host(self, identifier: str) -> Optional[HostRecord]:
        host_name = self.resolve_host_name(identifier)
        if not host_name:
            return None
        return self.hosts_by_name.get(host_name)

    def learn_host(
        self,
        name: Optional[str] = None,
        mac: Optional[str] = None,
        ip: Optional[str] = None,
        switch_dpid: Optional[int] = None,
        port_no: Optional[int] = None,
    ) -> HostRecord:
        normalized_mac = self._normalize_mac(mac)
        resolved_name = (
            name
            or (normalized_mac and self.name_by_mac.get(normalized_mac))
            or (ip and self.name_by_ip.get(ip))
            or self._next_dynamic_name()
        )
        host = self.hosts_by_name.get(resolved_name)
        if not host:
            host = HostRecord(name=resolved_name)
            self.hosts_by_name[resolved_name] = host
        if normalized_mac:
            host.mac = normalized_mac
            self.name_by_mac[normalized_mac] = resolved_name
        if ip:
            host.ip = ip
            self.name_by_ip[ip] = resolved_name
        if switch_dpid is not None:
            host.switch_dpid = switch_dpid
        if port_no is not None:
            host.port_no = port_no
        return host

    def shortest_path(self, src_dpid: int, dst_dpid: int) -> list[int]:
        if src_dpid == dst_dpid:
            return [src_dpid]
        queue = deque([(src_dpid, [src_dpid])])
        visited = {src_dpid}
        while queue:
            current, path = queue.popleft()
            for neighbor in sorted(self.adjacency.get(current, {})):
                if neighbor in visited:
                    continue
                next_path = path + [neighbor]
                if neighbor == dst_dpid:
                    return next_path
                visited.add(neighbor)
                queue.append((neighbor, next_path))
        raise TraceError(f"No path exists between s{src_dpid} and s{dst_dpid}.")

    def get_link_port(self, src_dpid: int, dst_dpid: int) -> int:
        try:
            return self.adjacency[src_dpid][dst_dpid]
        except KeyError as exc:
            raise TraceError(f"Missing link information between s{src_dpid} and s{dst_dpid}.") from exc

    def record_flow_rule(
        self,
        src_host: str,
        dst_host: str,
        switch_dpid: int,
        in_port: int,
        out_port: int,
        match: dict,
    ) -> None:
        key = (src_host, dst_host)
        self.flow_rules.setdefault(key, {})[switch_dpid] = FlowRuleRecord(
            switch_dpid=switch_dpid,
            in_port=in_port,
            out_port=out_port,
            match=dict(match),
        )

    def get_flow_rules_for_pair(self, src_host: str, dst_host: str) -> Dict[int, FlowRuleRecord]:
        return self.flow_rules.get((src_host, dst_host), {})

    def build_trace(self, src_identifier: str, dst_identifier: str) -> dict:
        src_host = self.get_host(src_identifier)
        dst_host = self.get_host(dst_identifier)
        if not src_host:
            raise TraceError(f"Unknown source host: {src_identifier}")
        if not dst_host:
            raise TraceError(f"Unknown destination host: {dst_identifier}")
        if src_host.switch_dpid is None or src_host.port_no is None:
            raise TraceError(f"Source host {src_host.name} has not been discovered yet.")
        if dst_host.switch_dpid is None or dst_host.port_no is None:
            raise TraceError(f"Destination host {dst_host.name} has not been discovered yet.")

        switch_path = self.shortest_path(src_host.switch_dpid, dst_host.switch_dpid)
        tracked_rules = self.get_flow_rules_for_pair(src_host.name, dst_host.name)
        if not tracked_rules:
            raise TraceError(
                f"No tracked flow rules found for {src_host.name} -> {dst_host.name}. Generate traffic first."
            )

        flow_rules = []
        for dpid in switch_path:
            rule = tracked_rules.get(dpid)
            if not rule:
                raise TraceError(f"Tracked flow rule missing on s{dpid} for {src_host.name} -> {dst_host.name}.")
            flow_rules.append(rule.as_dict())

        return {
            "src_host": src_host.name,
            "dst_host": dst_host.name,
            "path": [src_host.name] + [f"s{dpid}" for dpid in switch_path] + [dst_host.name],
            "switch_hops": [f"s{dpid}" for dpid in switch_path],
            "flow_rules": flow_rules,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def format_trace(trace: dict) -> str:
    lines = [
        "Packet path:",
        "  " + " -> ".join(trace["path"]),
        "Switch hops:",
        "  " + ", ".join(trace["switch_hops"]),
        "Flow rules:",
    ]
    for rule in trace["flow_rules"]:
        lines.append(
            f"  {rule['switch']}: in_port={rule['in_port']} out_port={rule['out_port']} match={rule['match']}"
        )
    return "\n".join(lines)

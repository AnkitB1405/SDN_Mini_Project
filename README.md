# SDN Based Path Tracer

This mini project builds an SDN path tracer on top of `Ryu` and `Mininet`. It identifies the forwarding path taken by packets, tracks the flow rules installed on switches, displays the route in the terminal, and validates the logic with tests.

## What the project does

In Software Defined Networking, the controller decides how switches forward packets. In this project, the Ryu controller learns the network topology, watches packets that arrive at the controller, discovers where hosts are attached, installs OpenFlow rules, and stores those rules so the route can be traced later.

When traffic is generated between two hosts:

- the controller discovers the source and destination host locations
- it computes the shortest switch path
- it installs flow rules on each switch in that path
- it stores those flow rules
- the trace tool fetches the route and prints it in a readable form

Example route:

```text
h1 -> s1 -> s2 -> s4 -> h4
```

## Project files

- `sdn_path_tracer/controller.py` - Ryu controller app
- `sdn_path_tracer/demo_topology.py` - Mininet demo topology
- `sdn_path_tracer/trace_cli.py` - terminal trace client
- `sdn_path_tracer/core.py` - path and flow tracking logic
- `tests/` - unit tests

## Features

- Track flow rules installed for each host pair
- Identify forwarding path using discovered topology
- Display the route in terminal output
- Return JSON trace output
- Validate path logic and output using tests

## Demo topology

The included Mininet topology uses:

- 4 hosts: `h1`, `h2`, `h3`, `h4`
- 4 switches: `s1`, `s2`, `s3`, `s4`
- redundant links between switches so path selection is meaningful

Hosts use fixed IP and MAC addresses so the controller can label traces cleanly.

## Prerequisites

- Ubuntu
- Python 3
- Mininet installed
- Open vSwitch installed
- `ryu` installed in your Python environment

Install the Python dependency:

```bash
python3 -m pip install -r requirements.txt
```

If Mininet or Open vSwitch was used earlier, cleanup helps:

```bash
sudo mn -c
```

## How to run

Open three terminals in the project folder.

### 1. Start the Ryu controller

```bash
ryu-manager --observe-links --ofp-tcp-listen-port 6653 sdn_path_tracer/controller.py
```

The controller exposes the trace API on port `8080`.

### 2. Start the Mininet topology

```bash
sudo python3 sdn_path_tracer/demo_topology.py --controller-ip 127.0.0.1 --controller-port 6653
```

This opens the Mininet CLI.

### 3. Generate traffic

Inside Mininet, run:

```bash
h1 ping -c 2 h4
```

The first packets help the controller discover host locations and install the forwarding rules.

### 4. Trace the path

In another terminal:

```bash
python3 -m sdn_path_tracer.trace_cli --src h1 --dst h4
```

To save the JSON result:

```bash
python3 -m sdn_path_tracer.trace_cli --src h1 --dst h4 --output trace_h1_h4.json
```

## Sample output

```text
Packet path:
  h1 -> s1 -> s2 -> s4 -> h4
Switch hops:
  s1, s2, s4
Flow rules:
  s1: in_port=1 out_port=2 match={'in_port': 1, 'eth_src': '00:00:00:00:00:01', 'eth_dst': '00:00:00:00:00:04'}
  s2: in_port=2 out_port=3 match={'in_port': 2, 'eth_src': '00:00:00:00:00:01', 'eth_dst': '00:00:00:00:00:04'}
  s4: in_port=2 out_port=1 match={'in_port': 2, 'eth_src': '00:00:00:00:00:01', 'eth_dst': '00:00:00:00:00:04'}
```

## JSON trace output

The trace API and CLI return these fields:

- `src_host`
- `dst_host`
- `path`
- `switch_hops`
- `flow_rules`
- `timestamp`

## How the path is identified

The controller discovers switch links from Mininet using Ryu topology events. When a packet reaches the controller, it learns which host is attached to which switch port. Once both end hosts are known, it calculates the shortest switch path and installs OpenFlow 1.3 rules along that route. Those installed rules are stored in memory and later used to reconstruct the exact forwarding path.

## Running the tests

The tests do not need Mininet. They validate the path and trace logic directly.

```bash
python3 -m unittest discover -s tests -v
```

The test suite checks:

- shortest path selection
- flow rule tracking
- path reconstruction
- output format
- error handling when a route is not ready

## Notes

- If the trace call says the destination host is not discovered yet, generate traffic first.
- If ports are already in use, stop old controller or Mininet processes and run `sudo mn -c`.
- The controller uses the shortest available path based on discovered links.

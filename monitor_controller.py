"""
SDN Network Utilization Monitor - POX Controller
=================================================
Place this file at: <pox_root>/ext/monitor_controller.py

Run:
  ./pox.py monitor_controller

Then in another terminal:
  sudo python3 topology.py
"""

from pox.core import core
from pox.lib.util import dpid_to_str
from pox.lib.recoco import Timer
import pox.openflow.libopenflow_01 as of

from collections import defaultdict
import time

log = core.getLogger()

POLL_INTERVAL = 5  # seconds


class NetworkMonitor(object):

    def __init__(self):
        self.mac_to_port = defaultdict(dict)   # {dpid: {mac: port}}
        self.prev_stats  = {}                  # {(dpid, port, 'tx'/'rx'): bytes}
        self.connections = {}                  # {dpid: connection}

        core.openflow.addListeners(self)
        Timer(POLL_INTERVAL, self._monitor_loop, recurring=True)
        log.info("NetworkMonitor ready.")

    # ── Switch connection ─────────────────────────────────────────────────────

    def _handle_ConnectionUp(self, event):
        dpid = event.dpid
        con  = event.connection
        self.connections[dpid] = con

        # table-miss: match all → send to controller
        msg = of.ofp_flow_mod()
        msg.priority = 0
        msg.match = of.ofp_match()
        msg.actions.append(of.ofp_action_output(port=of.OFPP_CONTROLLER))
        con.send(msg)

        log.info("Switch %s connected — table-miss rule installed.", dpid_to_str(dpid))

    def _handle_ConnectionDown(self, event):
        dpid = event.dpid
        self.connections.pop(dpid, None)
        self.mac_to_port.pop(dpid, None)
        log.info("Switch %s disconnected.", dpid_to_str(dpid))

    # ── Packet-in — learning switch + flow install ────────────────────────────

    def _handle_PacketIn(self, event):
        dpid = event.dpid
        con = event.connection
        in_port = event.port
        pkt = event.parsed

        if not pkt.parsed:
            return

        src = str(pkt.src)
        dst = str(pkt.dst)

        # MAC learning
        self.mac_to_port[dpid][src] = in_port
        out_port = self.mac_to_port[dpid].get(dst, of.OFPP_FLOOD)

        log.debug("packet_in  dpid=%s  %s->%s  port %s->%s",
                  dpid_to_str(dpid), src, dst, in_port, out_port)

        if out_port != of.OFPP_FLOOD:
            # install flow rule — idle_timeout=10s so stale entries expire
            msg = of.ofp_flow_mod()
            msg.priority = 1
            msg.idle_timeout = 10
            msg.hard_timeout = 120
            msg.match = of.ofp_match.from_packet(pkt, in_port)
            msg.actions.append(of.ofp_action_output(port=out_port))
            msg.data = event.ofp
            con.send(msg)
        else:
            # flood
            msg = of.ofp_packet_out()
            msg.data = event.ofp
            msg.in_port = in_port
            msg.actions.append(of.ofp_action_output(port=of.OFPP_FLOOD))
            con.send(msg)

    # ── Port stats reply — compute and display utilization ───────────────────

    def _handle_PortStatsReceived(self, event):
        dpid = event.connection.dpid

        print("\n" + "="*52)
        print("  Switch dpid={}  (interval={}s)".format(dpid_to_str(dpid), POLL_INTERVAL))
        print("="*52)
        print("  {:<8} {:>10} {:>10} {:>10} {:>10}".format(
              'Port', 'TX Mbps', 'RX Mbps', 'TX pkts', 'RX pkts'))
        print("  " + "-"*48)

        for stat in event.stats:
            port = stat.port_no
            if port > 0xFF00:   # skip synthetic ports (OFPP_LOCAL etc.)
                continue

            tx_bytes = stat.tx_bytes
            rx_bytes = stat.rx_bytes
            key_tx   = (dpid, port, 'tx')
            key_rx   = (dpid, port, 'rx')

            tx_mbps = rx_mbps = 0.0
            if key_tx in self.prev_stats:
                tx_mbps = (tx_bytes - self.prev_stats[key_tx]) * 8 / POLL_INTERVAL / 1e6
                rx_mbps = (rx_bytes - self.prev_stats[key_rx]) * 8 / POLL_INTERVAL / 1e6

            self.prev_stats[key_tx] = tx_bytes
            self.prev_stats[key_rx] = rx_bytes

            print("  {:<8} {:>10.3f} {:>10.3f} {:>10} {:>10}".format(
                  port, tx_mbps, rx_mbps, stat.tx_packets, stat.rx_packets))

    # ── Background poller ─────────────────────────────────────────────────────

    def _monitor_loop(self):
        for dpid, con in list(self.connections.items()):
            con.send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
            log.debug("Port stats requested from switch %s", dpid_to_str(dpid))


# ── POX entry point ───────────────────────────────────────────────────────────

def launch():
    core.registerNew(NetworkMonitor)
    log.info("Monitor launched.")

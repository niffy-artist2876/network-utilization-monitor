from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.cli import CLI

def build_topology():
    net = Mininet(controller=RemoteController, switch=OVSSwitch, link=TCLink)

    c0 = net.addController('c0', ip='127.0.0.1', port=6633)

    s1 = net.addSwitch('s1')
    s2 = net.addSwitch('s2')

    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')
    h3 = net.addHost('h3', ip='10.0.0.3/24')
    h4 = net.addHost('h4', ip='10.0.0.4/24')

    net.addLink(h1, s1, bw=100)
    net.addLink(h2, s1, bw=100)
    net.addLink(h3, s2, bw=100)
    net.addLink(h4, s2, bw=100)
    net.addLink(s1, s2, bw=100)

    net.build()
    c0.start()
    s1.start([c0])
    s2.start([c0])

    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    build_topology()
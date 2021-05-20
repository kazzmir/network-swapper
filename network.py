#!/usr/bin/env python3

import queue

class Config(object):
    def __init__(self):
        self.preferred_interface = None
        self.backup_interface = None
        self.ping_host = None

def read_config():
    config = Config()
    # FIXME: read these out of a file
    config.preferred_interface = 'enx00e04c680b8d'
    config.backup_interface = 'wlp0s20f3'
    config.ping_host = '8.8.8.8'

    return config

def print_date(what):
    import datetime
    print("{}: {}".format(datetime.datetime.now(), what))

PingGood = 'good'
PingBad = 'bad'

def send_ping(server, interface):
    # Send ICMP ping to server via the given interface
    pass

def ethernet_pinger(server, interface, status_queue, stop):
    print_date("Running ping thread")
    while not stop.wait(1):
        if send_ping(server, interface):
            status_queue.put(PingGood)
        else:
            status_queue.put(PingBad)

def find_gateway(ip, interface):
    link = ip.link_lookup(ifname=interface)[0]
    routes = ip.route('dump')
    for route in routes:
        if 'attrs' in route:
            attrs = route['attrs']
            good = True
            gateway = None
            for attr in attrs:
                if attr[0] == 'RTA_OIF' and attr[1] != link:
                    good = False

                if attr[0] == 'RTA_GATEWAY':
                    gateway = attr[1]

                if attr[0] == 'RTA_DST':
                    good = False

            if good and gateway is not None:
                return gateway

    return None

def iptables_block_all(interface):
    print_date("Blocking all packets via iptables to interface {}".format(interface))
    import iptc

    # Add a DROP rule in the INPUT chain for the given interface
    filter_table = iptc.Table(iptc.Table.FILTER)
    input_chain = iptc.Chain(filter_table, 'INPUT')
    add_drop_input = True
    for rule in input_chain.rules:
        if rule.in_interface == interface and rule.target.name == 'DROP':
            # Rule already exists, don't add another one
            add_drop_input = False
            break

    if add_drop_input:
        rule = iptc.Rule()
        rule.in_interface = interface
        rule.target = iptc.Target(rule, 'DROP')

        input_chain.insert_rule(rule)

    # Add a DROP rule in the OUTPUT chain for the given interface
    output_chain = iptc.Chain(filter_table, 'OUTPUT')
    add_drop_output = True
    for rule in output_chain.rules:
        if rule.out_interface == interface and rule.target.name == 'DROP':
            # Rule already exists, don't add another one
            add_drop_output = False
            break

    if add_drop_output:
        rule = iptc.Rule()
        rule.out_interface = interface
        rule.target = iptc.Target(rule, 'DROP')

        output_chain.insert_rule(rule)


def iptables_unblock_all(interface):
    print_date("Unblocking all packets via iptables to interface {}".format(interface))
    import iptc

    # Add a DROP rule in the INPUT chain for the given interface
    filter_table = iptc.Table(iptc.Table.FILTER)
    input_chain = iptc.Chain(filter_table, 'INPUT')
    add_drop_input = True
    for rule in input_chain.rules:
        if rule.in_interface == interface and rule.target.name == 'DROP':
            # Rule already exists, don't add another one
            input_chain.delete_rule(rule)
            break

    # Add a DROP rule in the OUTPUT chain for the given interface
    output_chain = iptc.Chain(filter_table, 'OUTPUT')
    add_drop_output = True
    for rule in output_chain.rules:
        if rule.out_interface == interface and rule.target.name == 'DROP':
            # Rule already exists, don't add another one
            output_chain.delete_rule(rule)
            break

def change_network(old, new, block):
    from pyroute2 import IPRoute
    print_date("Changing interface from {} to {}".format(old, new))

    with IPRoute() as ip:
        gateway_old = find_gateway(ip, old)
        gateway_new = find_gateway(ip, new)

        if gateway_old is None:
            print_date("Error: could not get gateway for old interface: {}".format(old))
            return

        if gateway_new is None:
            print_date("Error: could not get gateway for new interface: {}".format(new))

        old_link = ip.link_lookup(ifname=old)[0]
        new_link = ip.link_lookup(ifname=new)[0]

        # Remove old default routes. The routes must be removed before the new metric can be used,
        # otherwise netlink will respond with an error
        ip.route('del', dst='0.0.0.0/0', oif=old_link, gateway=gateway_old)
        ip.route('del', dst='0.0.0.0/0', oif=new_link, gateway=gateway_new)
        # Add new default routes where the new interface has a lower metric
        ip.route('add', dst='0.0.0.0/0', oif=old_link, gateway=gateway_old, priority=200)
        ip.route('add', dst='0.0.0.0/0', oif=new_link, gateway=gateway_new, priority=50)

    if block:
        iptables_block_all(old)
    else:
        iptables_unblock_all(new)

    import subprocess
    subprocess.call(['systemctl', 'restart', 'openvpn@hs'])
               

def run(config):
    global_stop = threading.Event()
    ethernet_ping_status = queue.Queue()

    pinger = threading.Thread(target=ethernet_pinger, args=(config.ping_host, config.preferred_interface, ethernet_ping_status, global_stop))
    pinger.daemon = True
    pinger.start()

    StatePreferred = 0
    StateBackup = 1
    
    state = StatePreferred
    good_count = 0

    while not global_stop.is_set():
        data = ethernet_ping_status.get()
        if state == StatePreferred:
            if data == PingBad:
                state = StateBackup
                change_network(config.preferred_interface, config.backup_interface, block=False)
                good_count = 0
            # otherwise its PingGood so we stay on the preferred network
        elif state == StateBackup:
            if data == PingGood:
                good_count += 1
                if good_count > 3:
                    change_network(config.backup_interface, config.preferred_interface, block=True)
            else:
                good_count = 0


def test():
    # change_network('enx00e04c680b8d', 'wlp0s20f3', block=False)
    change_network('wlp0s20f3', 'enx00e04c680b8d', block=True)
    # iptables_block_all('wlp0s20f3')
    # iptables_unblock_all('wlp0s20f3')

def main():
    config = read_config()

    run(config)

test()
# main()

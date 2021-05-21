#!/usr/bin/env python3

import queue
import threading
import subprocess

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
    """Sends a ping on the given interface using the 'ping' tool, returns true if successful otherwise fales"""
    # Send ICMP ping to server via the given interface
    # FIXME: figure out how to do this from pure python. It seems a raw socket can't be bound to an interface/ip?
    ping = subprocess.run(['ping', '-I', interface, '-w', '1', '-c', '1', server], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return ping.returncode == 0

def icmp_pinger2(server, interface, status_queue, stop):
    try:
        import pythonping
        print_date("Running ping thread")

        pinger = pythonping.executor.Communicator(server, None, 1, source='192.168.1.149')

        while not stop.wait(1):
            response = pinger.ping()
            print(response)

            #if send_ping(server, interface):
            #    status_queue.put(PingGood)
            #else:
            #    status_queue.put(PingBad)
    except Exception as fail:
        import traceback
        traceback.print_exc()
        print("Pinger failed: {}".format(fail))

def icmp_pinger(server, interface, status_queue, stop):
    try:
        print_date("Pinger running on interface {} to {}".format(interface, server))
        while not stop.wait(1):
            ping = send_ping(server, interface)
            # print_date("Ping: {}".format(ping))
            if ping:
                status_queue.put(PingGood)
            else:
                status_queue.put(PingBad)
    except Exception as fail:
        import traceback
        traceback.print_exc()
        print("Pinger failed: {}".format(fail))

def find_gateway(ip, interface):
    """Find the gateway ip for the default route of the given interface"""
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
    for rule in input_chain.rules:
        if rule.in_interface == interface and rule.target.name == 'DROP':
            input_chain.delete_rule(rule)

    # Add a DROP rule in the OUTPUT chain for the given interface
    output_chain = iptc.Chain(filter_table, 'OUTPUT')
    for rule in output_chain.rules:
        if rule.out_interface == interface and rule.target.name == 'DROP':
            output_chain.delete_rule(rule)

def change_network(old, new, block):
    """Switch the network from old to new, possibly setting up iptables rules to block
       the old interface
    """
    from pyroute2 import IPRoute
    print_date("Changing default interface from {} to {}".format(old, new))

    with IPRoute() as ip:
        gateway_old = find_gateway(ip, old)
        gateway_new = find_gateway(ip, new)

        if gateway_old is None:
            print_date("Error: could not get gateway for old interface: {}".format(old))
            return

        if gateway_new is None:
            print_date("Error: could not get gateway for new interface: {}".format(new))
            return

        old_link = ip.link_lookup(ifname=old)[0]
        new_link = ip.link_lookup(ifname=new)[0]

        # Remove old default routes. The routes must be removed before the new metric can be used,
        # otherwise netlink will respond with an error
        try:
            while True:
                ip.route('del', dst='0.0.0.0/0', oif=old_link, gateway=gateway_old)
        except Exception:
            pass

        try:
            while True:
                ip.route('del', dst='0.0.0.0/0', oif=new_link, gateway=gateway_new)
        except Exception:
            pass

        # Add new default routes where the new interface has a lower metric
        ip.route('add', dst='0.0.0.0/0', oif=old_link, gateway=gateway_old, priority=200)
        ip.route('add', dst='0.0.0.0/0', oif=new_link, gateway=gateway_new, priority=50)

    if block:
        iptables_block_all(old)
    else:
        iptables_unblock_all(new)

    # Restart things that depend on the network being up.
    # It would also be nice to restart my music mplayer that is streaming from the internet
    subprocess.call(['systemctl', 'restart', 'openvpn@hs'])
               

def run(config):
    global_stop = threading.Event()
    icmp_ping_status = queue.Queue()

    import signal

    def stop(signum, frame):
        print("Quitting..")
        global_stop.set()
        # Ensure the loop gets something and then quits
        icmp_ping_status.put(PingGood)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    pinger = threading.Thread(target=icmp_pinger, args=(config.ping_host, config.preferred_interface, icmp_ping_status, global_stop))
    pinger.daemon = True
    pinger.start()

    StatePreferred = 0
    StateBackup = 1
    
    state = StatePreferred
    good_count = 0
    bad_count = 0

    bad_max = 2

    # Start in the state where the preferred interface is the default route
    change_network(config.backup_interface, config.preferred_interface, block=True)

    while not global_stop.is_set():
        data = icmp_ping_status.get()
        if state == StatePreferred:
            if data == PingBad:
                bad_count += 1
                print_date("Ping failure on {} ({}/{})".format(config.preferred_interface, bad_count, bad_max))
                if bad_count >= bad_max:
                    state = StateBackup
                    change_network(config.preferred_interface, config.backup_interface, block=False)
                    good_count = 0
            else:
                # otherwise its PingGood so we stay on the preferred network
                bad_count = 0
        elif state == StateBackup:
            if data == PingGood:
                good_count += 1
                if good_count >= 3:
                    change_network(config.backup_interface, config.preferred_interface, block=True)
                    state = StatePreferred
                    bad_count = 0
            else:
                good_count = 0

def test_ping():
    global_stop = threading.Event()

    import signal

    def stop(signum, frame):
        print("Quitting..")
        global_stop.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    data = queue.Queue()

    icmp_pinger('8.8.8.8', 'enx00e04c680b8d', data, global_stop)
    # icmp_pinger('127.0.0.1', 'enx00e04c680b8d', data, global_stop)

def test():
    # change_network('enx00e04c680b8d', 'wlp0s20f3', block=False)
    change_network('wlp0s20f3', 'enx00e04c680b8d', block=True)
    # iptables_block_all('wlp0s20f3')
    # iptables_unblock_all('wlp0s20f3')

def is_root():
    import os
    return os.geteuid() == 0

def main():
    print_date("Network swapper")

    if not is_root():
        print_date("Error: must run as root")
        return

    config = read_config()

    run(config)

# test()
# test_ping()
main()

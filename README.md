Network Swapper
---------------

This program swaps the default route between different interfaces depending on certain conditions, namely the current default interface stops working then this program will swap to another interface.

My use case is that I have two network interfaces: ethernet attached to a cable modem, and tether/wifi via my phone (or sometimes my LTE modem). Ethernet is my preferred mode of network access as it is fast, high bandwidth, and has almost unlimited data caps. Unfortunately the cable network is unreliable somehow, which causes all packets sent out through the cable modem to get dropped or something. In these cases I switch to tether/wifi, which is reliable but is not as fast and has much more limited amount of maximum data I can send in a given time period.

The design is:
  send a ping to some host, such as 8.8.8.8, once a second via the preferred network interface (ethernet). If the ping doesn't come back then switch the default interface to wifi. Pings will still be sent via ethernet, and when X successful pings come back then switch the default interface back to ethernet, where X is something like 3 or 4.
  switching interfaces consists of
  * setting the default metric of the new interface to something low, like 50, and the other one to something higher, like 100.
  * use iptables to block packets from egressing out of the non-preferred interface, to force existing connections to end. connections that continue to use the preferred interface are fine.

Changing the default interface and sending ping's needs root access, so this program will have to be run as root for the time being.

Setup:
```
$ sudo pip install -r requirements.txt
```

Example of operation:
```
2021-05-22 23:10:57.806765: Network swapper
2021-05-22 23:10:57.806973: Pinger running on interface enx00e04c680b8d to 8.8.8.8
2021-05-22 23:10:57.907772: Changing default interface from enx00a0c6000000 to enx00e04c680b8d
2021-05-22 23:10:57.914431: Blocking all packets via iptables to interface enx00a0c6000000
2021-05-22 23:26:23.640483: Ping failure on enx00e04c680b8d (1/2)
2021-05-22 23:26:25.647860: Ping failure on enx00e04c680b8d (2/2)
2021-05-22 23:26:25.648059: Changing default interface from enx00e04c680b8d to enx00a0c6000000
2021-05-22 23:26:25.660135: Unblocking all packets via iptables to interface enx00a0c6000000
2021-05-22 23:26:58.757813: Changing default interface from enx00a0c6000000 to enx00e04c680b8d
2021-05-22 23:26:58.787192: Blocking all packets via iptables to interface enx00a0c6000000
2021-05-23 00:13:32.810662: Ping failure on enx00e04c680b8d (1/2)
2021-05-23 11:41:23.994766: Ping failure on enx00e04c680b8d (1/2)
2021-05-23 11:41:26.068302: Ping failure on enx00e04c680b8d (2/2)
2021-05-23 11:41:26.068362: Changing default interface from enx00e04c680b8d to enx00a0c6000000
2021-05-23 11:41:26.074659: Unblocking all packets via iptables to interface enx00a0c6000000
2021-05-23 11:41:29.124702: Changing default interface from enx00a0c6000000 to enx00e04c680b8d
2021-05-23 11:41:29.142150: Blocking all packets via iptables to interface enx00a0c6000000
```
After 2 bad pings this script switches the default route from the preferred interface enx00e04c680b8d to the backup interface enx00a0c6000000. Once a few good pings are sent out of enx00e04c680b8d then the default route switches back.

Notes:
Ubuntu's sytemd-resolved doesn't seem to choose the appropriate DNS server in all cases in that it tries to choose one of the upstream gateways, but it doesn't know which upstream is currently active. Rather than trying to convince systemd-resolved to do the right thing I simply uninstalled it and installed dnsmasq instead.

ipv4 vs ipv6: my main interface only has an ipv4 ip, but my backup interface gets both ipv4 and ipv6. Simply switching the default route to the main interface is not enough to prevent existing ipv4/ipv6 connections from going through the backup interface, so additionally iptables is used to block all traffic on the backup interface. Additionally, if a DNS lookup returns an ipv6 ip then the backup interface will be used to send the traffic. Rather than try to prevent all ipv6 situations from occurring I found it simplest to just delete the ipv6 ip's from the backup interface so that only ipv4 remains. If the main interface has an ipv6 interface then this probably is not an issue.

Network Swapper
---------------

This program swaps the default route between different interfaces depending on certain conditions, namely the current default interface stops working then this program will swap to another interface.

My use case is that I have two network interfaces: ethernet attached to a cable modem, and tether/wifi via my phone (or sometimes my LTE modem). Ethernet is my preferred mode of network access as it is fast, high bandwidth, and has almost unlimited data caps. Unfortunately the cable network is unreliable somehow, which causes all packets sent out through the cable modem to get dropped or something. In these cases I switch to tether/wifi, which is reliable but is not as fast and has much more limited amount of maximum data I can send in a given time period.

The design is:
  send a ping to some host, such as 8.8.8.8, once a second via the preferred network interface (ethernet). If the ping doesn't come back then switch the default interface to wifi. Pings will still be sent via ethernet, and when X successful pings come back then switch the default interface back to ethernet, where X is something like 3 or 4.
  switching interfaces consists of
  * setting the default metric of the new interface to something low, like 50, and the other one to something higher, like 100.
  * ifconfig down and then up on the old default interface to force all existing network connections to break.

Changing the default interface and sending ping's needs root access, so this program will have to be run as root for the time being.

Setup:
$ pip install python-iptables

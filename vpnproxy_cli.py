#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = "duc_tin"
__copyright__ = "Copyright 2015+, duc_tin"
__license__ = "GPLv2"
__version__ = "1.20"
__maintainer__ = "duc_tin"
__email__ = "nguyenbaduc.tin@gmail.com"

import os
import signal
import base64
import time
import datetime
from config import *
from subprocess import call, Popen, PIPE

# Get sudo privilege
euid = os.geteuid()
if euid != 0:
    args = ['sudo', sys.executable] + sys.argv + [os.environ]
    os.execlpe('sudo', *args)

# Define some mirrors of vpngate.net
mirrors = ['http://www.vpngate.net',
           'http://103.253.112.16:49882',
           'http://158.ip-37-187-34.eu:58272',
           'http://121.186.216.97:38438',
           'http://hannan.postech.ac.kr:6395',
           'http://115.160.46.181:38061',
           'http://hornet.knu.ac.kr:36171',
           'http://182-166-242-138f1.osk3.eonet.ne.jp:64298']

# TODO: add user manual to this and can be access by h, help.
# add option to change DNS differ from google


class Server():
    # if os.path.exists('/sbin/resolvconf'):
    #     # dns_leak_stop = 'script-security 2\r\nup update-resolv-conf.sh\r\ndown update-resolv-conf.sh\r\n'
    #     dns_leak_stop = 'script-security 2\r\nup updatedns.sh\r\n'
    #
    # else:
    #     print ''
    #     dns_leak_stop = ''

    def __init__(self, data):
        self.ip = data[1]
        self.score = int(data[2])
        self.ping = int(data[3]) if data[3] != '-' else 'inf'
        self.speed = int(data[4])
        self.country_long = data[5]
        self.country_short = data[6]
        self.NumSessions = data[7]
        self.uptime = data[8]
        self.logPolicy = data[11]
        self.config_data = base64.b64decode(data[-1])
        self.proto = 'tcp' if '\r\nproto tcp\r\n' in self.config_data else 'udp'
        port = re.findall('remote .+ \d+', self.config_data)
        if not port:
            self.port = '0'
        else:
            self.port = port[0].split()[-1]

    def write_file(self):
        txt_data = self.config_data
        if use_proxy == 'yes':
            txt_data = txt_data.replace('\r\n;http-proxy-retry\r\n', '\r\nhttp-proxy-retry 3\r\n')
            txt_data = txt_data.replace('\r\n;http-proxy [proxy server] [proxy port]\r\n',
                                        '\r\nhttp-proxy %s %s\r\n' % (proxy, port))

        tmp_vpn = open('vpn_tmp', 'w+')
        tmp_vpn.write(txt_data)
        return tmp_vpn

    def __str__(self):
        speed = self.speed / 1000. ** 2
        uptime = datetime.timedelta(milliseconds=int(self.uptime))
        uptime = re.split(',|\.', str(uptime))[0]
        txt = [self.country_short, str(self.ping), '%.2f' % speed, uptime, self.logPolicy, str(self.score), self.proto, self.port]
        txt = [dta.center(spaces[ind + 1]) for ind, dta in enumerate(txt)]
        return ''.join(txt)


def get_data():
    global proxy
    if use_proxy == 'yes':
        ping_name = ['ping', '-w 2', '-c 2', proxy]
        ping_ip = ['ping', '-w 2', '-c 2', ip]
        res1, err1 = Popen(ping_name, stdout=PIPE, stderr=PIPE).communicate()
        res2, err2 = Popen(ping_ip, stdout=PIPE, stderr=PIPE).communicate()

        if err1 and not err2:
            print ctext('Warning: ', 'yB'),
            print "Cannot resolve proxy's hostname"
            proxy = ip
        if err1 and err2:
            print ' Ping proxy got error: ', ctext(err1, 'r')
            print ' Check your proxy setting'
        if not err1 and '100% packet loss' in res1:
            print ctext('Warning:', 'yB') + ctext('Proxy not response to ping', 'y')
            print ctext("Either proxy's security not allow it to response to ping packet\n or proxy itself is dead", 'y')

        proxies = {
            'http': 'http://' + proxy + ':' + port,
            'https': 'http://' + proxy + ':' + port,
        }

    else:
        proxies = {}

    i = 0
    while i < len(mirrors):
        try:
            print ctext('using gate: ', 'B'), mirrors[i]
            gate = mirrors[i] + '/api/iphone/'
            vpn_data = requests.get(gate, proxies=proxies, timeout=3).text.replace('\r', '')

            if 'vpn_servers' not in vpn_data:
                raise requests.exceptions.RequestException

            servers = [line.split(',') for line in vpn_data.split('\n')]
            servers = {s[0]: Server(s) for s in servers[2:] if len(s) > 1}
            return servers
        except requests.exceptions.RequestException as e:
            print e
            print 'Connection to gate ' + ctext(mirrors[i], 'B') + ctext(' failed\n', 'rB')
            i += 1
    else:
        print 'Failed to get VPN servers data\nCheck your network setting and proxy'
        sys.exit(1)


def refresh_data():
    # fetch data from vpngate.net
    vpnlist = get_data()

    if s_country != 'all':
        vpnlist = dict([vpn for vpn in vpnlist.items()
                        if re.search(r'\b%s\b' % s_country, vpn[1].country_long.lower() + ' '
                                     + vpn[1].country_short.lower())])
    if s_port != 'all':
        vpnlist = dict([vpn for vpn in vpnlist.items() if vpn[1].port == s_port])

    if sort_by == 'speed':
        sort = sorted(vpnlist.keys(), key=lambda x: vpnlist[x].speed, reverse=True)
    elif sort_by == 'ping':
        sort = sorted(vpnlist.keys(), key=lambda x: vpnlist[x].ping)
    elif sort_by == 'score':
        sort = sorted(vpnlist.keys(), key=lambda x: vpnlist[x].score, reverse=True)
    elif sort_by == 'up time':
        sort = sorted(vpnlist.keys(), key=lambda x: int(vpnlist[x].uptime))
    else:
        print '\nValueError: sort_by must be in "speed|ping|score|up time" but got "%s" instead.' % sort_by
        print 'Change your setting by "$ ./vpnproxy config"\n'
        sys.exit()

    return sort, vpnlist


def dns_manager(action='backup', DNS='8.8.8.8'):
    global dns_fix

    dns_orig = '/etc/resolv.conf.bak'

    if not os.path.exists(dns_orig):
        print ctext('Backup DNS setting', 'yB')
        backup = ['-a', '/etc/resolv.conf', '/etc/resolv.conf.bak']
        call(['cp'] + backup)

    if action == "change" and dns_fix == 'yes':
        DNS = DNS.replace(' ', '').split(',')

        with open('/etc/resolv.conf', 'w+') as resolv:
            for dns in DNS:
                resolv.write('nameserver ' + dns + '\n')

    elif action == "restore":
        print ctext('\nRestore dns', 'yB')
        reverseDNS = ['-a', '/etc/resolv.conf.bak', '/etc/resolv.conf']
        call(['cp'] + reverseDNS)


def vpn_manager(ovpn):
    """ Check VPN season
        If vpn tunnel break or fail to create, terminate vpn season
        So openvpn not keep sending requests to proxy server and
         save you from being blocked.
    """
    global dns, verbose

    command = ['openvpn', '--config', ovpn]
    p = Popen(command, stdout=PIPE, stdin=PIPE)
    try:
        while p.poll() is None:
            line = p.stdout.readline()
            if verbose == 'yes':
                print line,
            if 'Initialization Sequence Completed' in line:
                dns_manager('change', dns)
                print ctext('VPN tunnel established successfully'.center(40), 'B')
                print 'Ctrl+C to quit VPN'.center(40)
            if 'Restart pause, 5 second(s)' in line or 'Connection timed out' in line:
                print line
                print ctext('Terminate vpn', 'B')
                p.send_signal(signal.SIGINT)
    except KeyboardInterrupt:
        p.send_signal(signal.SIGINT)
        p.wait()
        print ctext('VPN tunnel is terminated'.center(40), 'B')
    finally:
        dns_manager('restore')


# ---------------------------- Main  --------------------------------
# get config file path
path = os.path.realpath(sys.argv[0])
config_file = os.path.split(path)[0] + '/config.ini'
args = sys.argv[1:]

# get proxy from config file
if os.path.exists(config_file):
    if len(args):
        # process commandline arguments
        if args[0] in ['r', 'restore']:
            dns_manager('restore')
        else:
            get_input(config_file, args)

    proxy, port, ip, sort_by, use_proxy, s_country, s_port, dns_fix, dns, verbose = read_config(config_file)

else:
    print '\n' + '_'*12 + ctext(' First time config ', 'gB') + '_'*12 + '\n'
    print "If you don't know what to do, just press Enter to use default option\n"
    use_proxy = 'no' if raw_input(ctext('Do you need proxy to connect? ', 'B')+'[yes|no(default)]:') in 'no' else 'yes'
    if use_proxy == 'yes':
        print ' Input your http proxy such as ' + ctext('www.abc.com:8080', 'pB')
        while 1:
            try:
                proxy, port = raw_input(' Your\033[95m proxy:port \033[0m: ').split(':')
                ip = socket.gethostbyname(proxy)
                port = port.strip()
                if not 0 <= int(port) <= 65535:
                    raise ValueError
            except ValueError:
                print ctext(' Error: Http proxy must in format ', 'r')+ctext('address:port', 'B')
                print ' Where ' + ctext('address', 'B') + ' is in form of www.abc.com or 123.321.4.5'
                print '       ' + ctext('port', 'B') + ' is a number in range 0-65535'
            else:
                break

    else:
        proxy, port, ip = '', '', ''

    sort_by = raw_input(ctext('\nSort servers by ', 'B') + '[speed (default) | ping | score | up time]: ')
    if sort_by not in ['speed', 'ping', 'score', 'up time']:
        sort_by = 'speed'

    s_country = raw_input(ctext('\nFilter server by country ','B') + '[eg: all (default), jp, japan]: ')
    if not s_country:
        s_country = 'all'

    dns_fix = 'yes' if raw_input(ctext('\nFix DNS leaking ', 'B') + '[yes (default) | no] : ') in 'yes' else 'no'
    dns = ''
    if dns_fix == 'yes':
        dns = raw_input(' DNS server or Enter to use 8.8.8.8 (google): ')
    if not dns:
        dns = '8.8.8.8, 84.200.69.80, 208.67.222.222'
    verbose = 'no' if 'n' in raw_input(ctext('Write openvpn log? [yes (default)| no]: ', 'B')) else 'yes'
    write_config(self.config_file, proxy, port, ip, sort_by, use_proxy, s_country, 'all', dns_fix, dns, verbose)
    print '\n' + '_'*12 + ctext(' Config done', 'gB') + '_'*12 + '\n'

# ------------------- check_dependencies: ----------------------
required = {'openvpn': 0, 'python-requests': 0, 'resolvconf': 0}

try:
    import requests
except ImportError:
    required['python-requests'] = 1

if not os.path.exists('/usr/sbin/openvpn'):
    required['openvpn'] = 1

if not os.path.exists('/sbin/resolvconf'):
    required['resolvconf'] = 1

need = [p for p in required if required[p]]
if need:
    print ctext('\n**Lack of dependencies**', 'rB')
    env = dict(os.environ)
    env['http_proxy'] = 'http://' + proxy + ':' + port
    env['https_proxy'] = 'http://' + proxy + ':' + port

    for package in need:
        print '\n___Now installing', ctext(package, 'gB')
        print
        call(['apt-get', 'install', package], env=env)

    import requests


# -------- all dependencies should be available after this line ----------------------
dns_manager()
ranked, vpn_list = refresh_data()

labels = ['Index', 'Country', 'Ping', 'Speed', 'Up time', 'Log Policy', 'Score', 'protocol', 'Portal']
spaces = [6, 7, 6, 10, 10, 10, 10, 8, 8]
labels = [label.center(spaces[ind]) for ind, label in enumerate(labels)]
connected_servers = []

while True:
    print ctext('Use proxy: ', 'B'), use_proxy,
    print ' || ', ctext('Country: ', 'B'), s_country

    if not ranked:
        print '\nNo server found for "%s"\n' % s_country
    else:
        print ctext(''.join(labels), 'gB')
        for index, key in enumerate(ranked[:20]):
            text = '%2d:'.center(6) % index + str(vpn_list[key])
            if connected_servers and vpn_list[key].ip == connected_servers[-1]:
                text = ctext(text, 'y')
            elif connected_servers and vpn_list[key].ip in connected_servers:
                text = ctext(text, 'r')
            print text

    try:
        server_sum = min(len(ranked), 20)
        user_input = raw_input(ctext('Vpn command: ', 'gB'))
        if user_input.strip().lower() in ['q', 'quit', 'exit']:
            print ctext('Goodbye'.center(40), 'gB')
            sys.exit()
        elif user_input.strip().lower() in 'refresh':
            ranked, vpn_list = refresh_data()
        elif user_input.strip().lower() in 'config':
            get_input(config_file, [user_input])
            proxy, port, ip, sort_by, use_proxy, s_country, s_port, dns_fix, dns, verbose = read_config(config_file)
            ranked, vpn_list = refresh_data()
        elif re.findall(r'^\d+$', user_input.strip()) and int(user_input) < server_sum:
            chose = int(user_input)
            print time.ctime().center(40)
            print ('Connect to ' + vpn_list[ranked[chose]].country_long).center(40)
            print vpn_list[ranked[chose]].ip.center(40)
            connected_servers.append(vpn_list[ranked[chose]].ip)
            vpn_file = vpn_list[ranked[chose]].write_file()
            vpn_file.close()
            vpn_manager(os.path.abspath(vpn_file.name))
        else:
            print 'Invalid command!'
            print '  q(uit) to quit\n  r(efresh) to refresh table\n' \
                  '  c(onfig) to change setting\n  number in range 0~%s to choose vpn\n' % (server_sum - 1)
            time.sleep(3)

    except KeyboardInterrupt:
        time.sleep(0.5)
        print "\nSelect another VPN server or 'q' to quit"

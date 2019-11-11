import time
import select
import socket
import requests
import email.parser
import xml.etree.ElementTree as et
from urllib.parse import urlsplit
from fcache.cache import FileCache

# Uses the ssdp project on GitHub as a reference
# https://github.com/codingjoe/ssdp

class Router:
    def __init__(self, url, ip, port, wan_ip_type, base_url):
        self.url = url
        self.ip = ip
        self.port = port
        self.type = wan_ip_type
        self.base_url = base_url
        self.serial_number = ""
        self.uuid = ""
        self.control_url = ""

    @classmethod
    def parse_ssdp_response(cls, ssdp_response, sender):
        response_headers = dict(ssdp_response.headers)

        if 'LOCATION' not in response_headers:
            print('The M-SEARCH response from %s:%d did not contain a Location header.' \
                  % (sender[0], sender[1]))
            print(ssdp_response)
            return None

        urlparts = urlsplit(response_headers['LOCATION'])
        base_url = '{}://{}'.format(urlparts.scheme, urlparts.netloc)

        return Router(
            url=response_headers['LOCATION'],
            ip=sender[0],
            port=sender[1],
            wan_ip_type=response_headers['ST'],
            base_url=base_url
        )


class SSDP:
    multicast_host = '239.255.255.250'
    multicast_port = 1900
    buffer_size = 4096
    response_time_secs = 5

    @classmethod
    def list(cls, refresh=False):
        """list finds all devices responding to an SSDP search for WANIPConnection:1 and WANIPConnection:2."""
        
        # Open the file cache of objects
        cache = FileCache("upnp", "cs")
        
        if cache and cache['lastUpdate'] and cache['routers']:
            lastUpdate = cache['lastUpdate']
            timeDelta = time.time() - lastUpdate

            # Cache is recently refreshed in the last 5 minutes
            if timeDelta < 300 and not refresh:
                return cache['routers']

        print("Searching for routers. This can take a few seconds!")

        # Create a UDP socket and set its timeout
        sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM, proto=socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.setblocking(False)

        # Create the WANIPConnection:1 and WANIPConnection:2 request objects
        headers = {
            'HOST': "{}:{}".format(SSDP.multicast_host, SSDP.multicast_port),
            'MAN': '"ssdp:discover"',
            'MX': str(SSDP.response_time_secs),
            'USER-AGENT': 'UPnP/x App/x Python/x'
        }

        wan_ip1_sent = False
        wan_ip1 = SSDP._create_msearch_request('urn:schemas-upnp-org:service:WANIPConnection:1', headers=headers)

        wan_ip2_sent = False
        wan_ip2 = SSDP._create_msearch_request('urn:schemas-upnp-org:service:WANIPConnection:2', headers=headers)

        inputs = [sock]
        outputs = [sock]

        routers = []
        time_end = time.time() + SSDP.response_time_secs

        while time.time() < time_end:
            _timeout = 1
            readable, writable, _ = select.select(inputs, outputs, inputs, _timeout)
            for _sock in readable:
                msg, sender = _sock.recvfrom(SSDP.buffer_size)
                response = SSDPResponse.parse(msg.decode())
                router = Router.parse_ssdp_response(response, sender)
                if router:
                    routers.append(router)

            for _sock in writable:
                if not wan_ip1_sent:
                    wan_ip1.sendto(_sock, (SSDP.multicast_host, SSDP.multicast_port))
                    time_end = time.time() + SSDP.response_time_secs
                    wan_ip1_sent = True
                if not wan_ip2_sent:
                    wan_ip2.sendto(_sock, (SSDP.multicast_host, SSDP.multicast_port))
                    time_end = time.time() + SSDP.response_time_secs
                    wan_ip2_sent = True

        for r in routers:
            (serial_number, control_url, uuid) = SSDP._get_router_service_description(r.url)
            r.serial_number = serial_number
            r.control_url = control_url
            r.uuid = uuid

        # Update cache
        cache['lastUpdate'] = time.time()
        cache['routers'] = routers
        cache.close()

        return routers

    @classmethod
    def _create_msearch_request(cls, service_type, headers={}):
        headers["ST"] = service_type
        return SSDPRequest('M-SEARCH', headers=headers)

    @classmethod
    def _get_router_service_description(cls, url):
        """Examines the given router to find the control URL, serial number, and UUID."""
        response = requests.get(url)
        # print(response.text)
        
        # Parse the returned XML and find the <URLBase> and <controlURL> elements
        xml = et.fromstring(response.text)

        serialNumber = next(
            (x.text for x in xml.findall(".//{urn:schemas-upnp-org:device-1-0}serialNumber")),
            None
        )

        # The UUID field contains the text "uuid:" before the actual UUID value. This is removed
        # and just the actual UUID is returned.
        # Example: uuid:11111111-2222-3333-4444-555555555555 becomes 11111111-2222-3333-4444-555555555555
        uuid = next(
            (x.text for x in xml.findall(".//{urn:schemas-upnp-org:device-1-0}UDN")),
            None
        )

        if uuid:
            uuid = uuid.split(":")[1]

        for svc in xml.findall(".//{urn:schemas-upnp-org:device-1-0}service"):
            svcType = svc.find(".//{urn:schemas-upnp-org:device-1-0}serviceType").text
            controlUrl = svc.find(".//{urn:schemas-upnp-org:device-1-0}controlURL").text
            # print("Found svcType:%s controlUrl:%s" % (svcType, controlUrl))

            if (SSDP._is_wanip_service(svcType)):
                return (serialNumber, controlUrl, uuid)

        return (None, None, None)

    @classmethod
    def _is_wanip_service(cls, svcType):
        return svcType == "urn:schemas-upnp-org:service:WANIPConnection:1" \
                    or svcType == "urn:schemas-upnp-org:service:WANIPConnection:2"

class SSDPMessage:
    """Simplified HTTP message to serve as a SSDP message."""

    def __init__(self, version='HTTP/1.1', headers=None):
        if headers is None:
            headers = []
        elif isinstance(headers, dict):
            headers = headers.items()

        self.version = version
        self.headers = list(headers)

    @classmethod
    def parse(cls, msg):
        """
        Parse message from string.
        Args:
            msg (str): Message string.
        Returns:
            SSDPMessage: Message parsed from string.
        """
        raise NotImplementedError()

    @classmethod
    def parse_headers(cls, msg):
        """
        Parse HTTP headers.
        Args:
            msg (str): HTTP message.
        Returns:
            (List[Tuple[str, str]): List of header tuples.
        """
        return list(email.parser.Parser().parsestr(msg).items())

    def __str__(self):
        """Return complete HTTP message."""
        raise NotImplementedError()

    def __bytes__(self):
        """Return complete HTTP message as bytes."""
        return self.__str__().encode().replace(b'\n', b'\r\n')


class SSDPResponse(SSDPMessage):
    """Simple Service Discovery Protocol (SSDP) response."""

    def __init__(self, status_code, reason, **kwargs):
        self.status_code = int(status_code)
        self.reason = reason
        super().__init__(**kwargs)

    @classmethod
    def parse(cls, msg):
        """Parse message string to response object."""
        lines = msg.splitlines()
        version, status_code, reason = lines[0].split()
        headers = cls.parse_headers('\r\n'.join(lines[1:]))
        return cls(version=version, status_code=status_code,
                   reason=reason, headers=headers)

    def __str__(self):
        """Return complete SSDP response."""
        lines = list()
        lines.append(' '.join(
            [self.version, str(self.status_code), self.reason]
        ))
        for header in self.headers:
            lines.append('%s: %s' % header)
        return '\n'.join(lines)


class SSDPRequest(SSDPMessage):
    """Simple Service Discovery Protocol (SSDP) request."""

    def __init__(self, method, uri='*', version='HTTP/1.1', headers=None):
        self.method = method
        self.uri = uri
        super().__init__(version=version, headers=headers)

    @classmethod
    def parse(cls, msg):
        """Parse message string to request object."""
        lines = msg.splitlines()
        method, uri, version = lines[0].split()
        headers = cls.parse_headers('\r\n'.join(lines[1:]))
        return cls(version=version, uri=uri, method=method, headers=headers)

    def sendto(self, transport, addr):
        """
        Send request to a given address via given transport.
        Args:
            transport (asyncio.DatagramTransport):
                Write transport to send the message on.
            addr (Tuple[str, int]):
                IP address and port pair to send the message to.
        """
        msg = bytes(self) + b'\r\n'
        # logger.debug("%s:%s < %s", *(addr + (self,)))
        transport.sendto(msg, addr)

    def __str__(self):
        """Return complete SSDP request."""
        lines = list()
        lines.append(' '.join(
            [self.method, self.uri, self.version]
        ))
        for header in self.headers:
            lines.append('%s: %s' % header)
        return '\n'.join(lines)

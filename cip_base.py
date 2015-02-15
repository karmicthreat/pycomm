import struct
import socket
from cip_const import *

import os
import json
import logging.config


def setup_logging(default_path='logging.json', default_level=logging.INFO, env_key='LOG_CFG'):
    """Setup logging configuration

    """
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = json.load(f)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)


class ProtocolError(Exception):
    pass


class SocketError(Exception):
    pass


class CipError(Exception):
    pass


def pack_sint(n):
    return struct.pack('B', n)


def pack_uint(n):
    """pack 16 bit into 2 bytes little indian"""
    return struct.pack('<H', n)


def pack_dint(n):
    """pack 32 bit into 4 bytes little indian"""
    return struct.pack('<I', n)


def pack_real(r):
    """unpack 4 bytes little indian to int"""
    return struct.pack('<f', r)


def pack_lint(l):
    """unpack 4 bytes little indian to int"""
    return struct.unpack('<q', l)


def unpack_bool(st):
    if int(struct.unpack('B', st[0])[0]) == 255:
        return 1
    return 0

def unpack_sint(st):
    return int(struct.unpack('B', st[0])[0])


def unpack_uint(st):
    """unpack 2 bytes little indian to int"""
    return int(struct.unpack('<H', st[0:2])[0])


def unpack_dint(st):
    """unpack 4 bytes little indian to int"""
    return int(struct.unpack('<I', st[0:4])[0])


def unpack_real(st):
    """unpack 4 bytes little indian to int"""
    return float(struct.unpack('<f', st[0:4])[0])


def unpack_lint(st):
    """unpack 4 bytes little indian to int"""
    return int(struct.unpack('<q', st[0:8])[0])


UNPACK_DATA_FUNCTION = {
    'BOOL': unpack_bool,
    'SINT': unpack_sint,    # Signed 8-bit integer
    'INT': unpack_uint,     # Signed 16-bit integer
    'DINT': unpack_dint,    # Signed 32-bit integer
    'REAL': unpack_real,    # 32-bit floating point,
    'DWORD': unpack_dint,    # byte string 32-bits
    'LINT': unpack_lint,
}

PACK_DATA_FUNCTION = {
    'BOOL': pack_sint,
    'SINT': pack_sint,    # Signed 8-bit integer
    'INT': pack_uint,     # Signed 16-bit integer
    'DINT': pack_dint,    # Signed 32-bit integer
    'REAL': pack_real,    # 32-bit floating point,
    'DWORD': pack_dint,    # byte string 32-bits
    'LINT': pack_lint,
}

def print_info(msg):
    """
    nice formatted print for the encapsulated message
    :param msg: the encapsulated message to print
    :return:
    """
    print
    n = len(msg)
    print "  Full length of EIP = %d (0x%04x)" % (n, n)

    cmd = unpack_uint(msg[:2])
    print "         EIP Command =",
    if cmd == 0:
        print "NOP"
    elif cmd == 0x01:
        print "List Targets"
    elif cmd == 0x04:
        print "List Services"
    elif cmd == 0x63:
        print "List Identity"
    elif cmd == 0x64:
        print "List Interfaces"
    elif cmd == 0x65:
        print "Register Session"
    elif cmd == 0x66:
        print "Unregister Session"
    elif cmd == 0x6f:
        print "SendRRData"
    elif cmd == 0x70:
        print "SendUnitData"
    else:
        print "Unknown command: 0x%02x" % cmd

    # The Data Part
    d = unpack_uint(msg[2:4])
    print "Attached Data Length = %d" % d

    n = unpack_dint(msg[4:8])
    print "      Session Handle = %d (0x%08x)" % (n, n)

    n = unpack_dint(msg[8:12])
    print "      Session Status = %d (0x%08x)" % (n, n)

    print "      Sender Context = %s" % msg[12:20]

    n = unpack_dint(msg[20:24])
    print "    Protocol Options = %d (0x%08x)" % (n, n)

    if 0 < d < 500:
        print "data =", list(msg[24:])
    elif d > 500:
        print "attached data is longer than 500 bytes"
    print

    return msg


def print_bytes_line(msg):
    out = ''
    for ch in msg:
        out += "{:0>2x}".format(ord(ch))
    return out


def print_bytes_msg(msg, info=''):
    out = info
    new_line = True
    line = 0
    column = 0
    for idx, ch in enumerate(msg):
        if new_line:
            out += "\n({:0>4d}) ".format(line * 10)
            new_line = False
        out += "{:0>2x} ".format(ord(ch))
        if column == 9:
            new_line = True
            column = 0
            line += 1
        else:
            column += 1
    return out


def get_extended_status(msg, start):
    status = unpack_sint(msg[start:start+1])
    # Exit if  send_rr_data replay returned error
    # 42 General Status
    # 43 Size of additional status
    # 44..n additional status
    extended_status_size = unpack_sint(msg[start+1:start+2])
    if extended_status_size != 0:
        # There is an additional status
        try:
            if extended_status_size == 1:
                extended_status = unpack_sint(msg[start+2:start+3])
            elif extended_status_size == 2:
                extended_status = unpack_sint(msg[start+2:start+4])
            elif extended_status_size == 4:
                extended_status = unpack_dint(msg[start+2:start+6])
            else:
                print ('Extended Status Size Unknown')
                return False
        except LookupError:
            print ('Extended status [{0}] not coded '.format(pack_dint(extended_status)))
            return False

    print ('Extended status :{0}'.format(EXTEND_CODES[status][extended_status]))
    return False


def create_tag_rp(tag):
    """ Create tag Request Packet

    It returns the request packed wrapped around the tag passed.
    If any error it returns none
    """
    tags = tag.split('.')
    rp = []
    index = []
    for tag in tags:
        add_index = False
        # Check if is an array tag
        if tag.find('[') != -1:
            # Remove the last square bracket
            tag = tag[:len(tag)-1]
            # Isolate the value inside bracket
            inside_value = tag[tag.find('[')+1:]
            # Now split the inside value in case part of multidimensional array
            index = inside_value.split(',')
            # Flag the existence of one o more index
            add_index = True
            # Get only the tag part
            tag = tag[:tag.find('[')]
        tag_length = len(tag)
        # Create the request path
        rp.append(EXTENDED_SYMBOL)  # ANSI Ext. symbolic segment
        rp.append(chr(tag_length))  # Length of the tag
        # Add the tag to the Request path
        for char in tag:
            rp.append(char)
        # Add pad byte because total length of Request path must be word-aligned
        if tag_length % 2:
            rp.append(PADDING_BYTE)
        # Add any index
        if add_index:
            for idx in index:
                val = int(idx)
                if val <= 0xff:
                    rp.append(ELEMENT_ID["8-bit"])
                    rp.append(pack_sint(val))
                elif val <= 0xffff:
                    rp.append(ELEMENT_ID["16-bit"]+PADDING_BYTE)
                    rp.append(pack_uint(val))
                elif val <= 0xfffffffff:
                    rp.append(ELEMENT_ID["32-bit"]+PADDING_BYTE)
                    rp.append(pack_dint(val))
                else:
                    # Cannot create a valid request packet
                    return None

    # At this point the Request Path is completed,
    return ''.join(rp)


def build_common_packet_format(message_type, message, addr_type, addr_data=None, timeout=0):
    """ build_common_packet_format

    It creates the common part for a CIP message. Check Volume 2 (page 2.22) of CIP specification  for reference
    """
    msg = pack_dint(0)   # Interface Handle: shall be 0 for CIP
    msg += pack_uint(timeout)   # timeout
    msg += pack_uint(2)  # Item count: should be at list 2 (Address and Data)
    msg += addr_type  # Address Item Type ID

    if addr_data is not None:
        msg += pack_uint(len(addr_data))  # Address Item Length
        msg += addr_data
    else:
        msg += pack_uint(0)  # Address Item Length
    msg += message_type  # Data Type ID
    msg += pack_uint(len(message))   # Data Item Length
    msg += message
    return msg


class Socket:
    def __init__(self, timeout):
        self.timeout = 5.0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if timeout is None:
            self.sock.settimeout(self.timeout)
        else:
            self.sock.settimeout(timeout)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    @property
    def timeout(self):
        return self.timeout

    @timeout.setter
    def timeout(self, par):
        self.timeout = par

    def connect(self, host, port):
        try:
            self.sock.connect((host, port))
        except socket.timeout:
            raise SocketError("Socket timeout during connection.")

    def send(self, msg, timeout=0):
        if timeout != 0:
            self.sock.settimeout(timeout)
        total_sent = 0
        while total_sent < len(msg):
            try:
                sent = self.sock.send(msg[total_sent:])
                if sent == 0:
                    raise SocketError("socket connection broken.")
                total_sent += sent
            except socket.error:
                raise SocketError("socket connection broken.")
        return total_sent

    def receive(self, timeout=0):
        if timeout != 0:
            self.sock.settimeout(timeout)
        msg_len = 28
        chunks = []
        bytes_recd = 0
        one_shot = True
        while bytes_recd < msg_len:
            try:
                chunk = self.sock.recv(min(msg_len - bytes_recd, 2048))
                if chunk == '':
                    raise SocketError("socket connection broken.")
                if one_shot:
                    data_size = int(struct.unpack('<H', chunk[2:4])[0])  # Length
                    msg_len = HEADER_SIZE + data_size
                    one_shot = False

                chunks.append(chunk)
                bytes_recd += len(chunk)
            except socket.error, e:
                raise SocketError(e)
        return ''.join(chunks)

    def close(self):
        self.sock.close()


#!/usr/bin/env python


from logging import basicConfig, DEBUG, debug, error, info

from securexmlrpc import SecureXMLRPCServer as RPCServer
from xmlrpclib import SafeTransport, ServerProxy, Binary

from threading import Timer

from flowtools import FlowSet

from os import system, getuid, setuid, setreuid, setregid, path, mkdir, system
from sys import argv,exit
from pwd import getpwuid,getpwnam


KEYFILE ='cert/localhost-client.key.unsecure'
CERTFILE='cert/localhost-client.crt'

class SafeTransportWithCert(SafeTransport):
    __cert_file = CERTFILE
    __key_file = KEYFILE
    def make_connection(self,host):
        host_with_cert = (host, {
            'key_file'  :  self.__key_file,
            'cert_file' :  self.__cert_file
            })
        return SafeTransport.make_connection(self,host_with_cert)

def update_check_call(url):
    debug('start update %s' % url)
    transport = SafeTransportWithCert()
    try:
        server = ServerProxy(url, transport = transport)
        info(server.check())
        debug('check updates ok')
    except Exception, e:
        debug('check updates fail [%s]' % str(e))
    global update_check
    update_check = Timer( 30, update_check_call, (url,))
    update_check.start()


class Rpc:
    title = 'Rpc'
    name = 'Rpc'
    def ping(self):
        return 'pong'
    def check(self):
        return 'check!'
    def send_flow(self, file):
        transport = SafeTransportWithCert()
        try:
            server = ServerProxy(self.rpcurl, transport = transport)
            content = Binary(open(file, 'rb').read())
            server.get_flow(content)
        except Exception, e:
            error('fail send flow (%s)' % str(e))

    def get_flow(self, content):
        pass


if __name__ == '__main__':
    from optparse import OptionParser
    from ConfigParser import ConfigParser
    parser = OptionParser()
    parser.add_option('-c', '--config', dest='cfgfile', help='full path to config')
    (options, args) = parser.parse_args()
    if options.cfgfile == None:
        parser.error('need path to configuration')

    try:
        cfg = ConfigParser()
        if not cfg.read(options.cfgfile): 
            raise Exception('Config file %s not exists' % options.cfgfile)
        user = cfg.get('main', 'user')
        netini_file = cfg.get('main', 'netini')
        log = cfg.get('main', 'log')
        rpcbind = (cfg.get('main', 'bindhost'), cfg.getint('main','bindport'))
        rpcurl = cfg.get('main', 'rpcurl')
    except Exception, e:
        print 'error: %s' % str(e)
        exit(1)

    cur_user = getpwuid(getuid())[0]
    (need_uid, need_gid) = getpwnam(user)[2:4]

    if getuid() == 0:
        setregid(0, need_gid)
        setreuid(0, need_uid)
    else:
        critical('user %s is not %s' % (cur_user, user))
        exit(2)

    basicConfig(level=DEBUG,
        format='%(asctime)s %(levelname)s %(message)s',
        filename=log, filemode='a')

    identify_conf = {}

    netini = ConfigParser()
    netini.read(netini_file)
    for sect in netini.sections():
        identify_conf.add( ( int(sect),
            netini.get(sect,'int'),
            netini.get(sect,'mac'),
            netini.get(sect,'net'),
            netini.get(sect,'mask') ) )

    rpc = Rpc()
    rpc.rpcurl = rpcurl
    rpcserver = RPCServer(rpc, rpcbind)

    update_check = Timer( 30, update_check_call, (rpcurl, ))
    update_check.start()

    rpcserver.startup()

    info('stopping server')

    update_check.cancel()

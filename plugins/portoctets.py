from util import GetCommandGenerator, CarbonProtocol

from time import time 
from logging import debug, error, info

from twisted.internet.protocol import ClientCreator
from twisted.internet import reactor

ifHCInOctets = (1,3,6,1,2,1,31,1,1,1,6)
ifHCOutOctets = (1,3,6,1,2,1,31,1,1,1,10)

def receive((errorIndication, errorStatus, errorIndex, varBinds, cbCtx)):
    if errorIndication or errorStatus:
        cbCtx.job_info['status'] = ERROR

    _in=0
    _out=0
    now = time()

    for oid, val in varBinds:
        if oid == (ifHCInOctets + (cbCtx.port_id,)):
            _in = val
        elif oid == (ifHCOutOctets + (cbCtx.port_id,)):
            _out = val
        else:
            error('port-octets: receive unknown oid')

    values = ()

    if cbCtx.job_info['in'] != None:
#TODO if _in < previous_in then _in = MAXVALUE+_in
        d_in = _in - cbCtx.job_info['in']
        d_out = _out - cbCtx.job_info['out']
        d_time = now - cbCtx.job_info['time']

        debug('delta in:%s delta time:%s' % ( d_in, d_time))

        speed_in = d_in*8/d_time  # MBit
        speed_out = d_out*8/d_time

        values += ( '%s.ports.octets.%s.in' % (
                                      cbCtx.host_name,
                                      cbCtx.port_name
                                    ),
                    speed_in,
                    now),
        values += ( '%s.ports.octets.%s.out' % (
                                      cbCtx.host_name,
                                      cbCtx.port_name
                                    ),
                    speed_out,
                    now),

        c = ClientCreator(reactor, CarbonProtocol, values)
        c.connectTCP(
                cbCtx.carbon_host,
                cbCtx.carbon_port
                ).addCallback(lambda p: p.sendMessage())
        
    cbCtx.job_info['in'] = _in
    cbCtx.job_info['out'] = _out
    cbCtx.job_info['time'] = now


def fetch(snmpEngine, carbon_host, carbon_port, host_name, job_info, port_name, port_id):
    debug('port-octets: generate snmp from %s %s %s' % (host_name, port_name,
        port_id))
    getCmdGen = GetCommandGenerator()
    df = getCmdGen.sendReq(
            snmpEngine,
            host_name,
            (
                ((ifHCInOctets+(int(port_id),)), None),
                ((ifHCOutOctets+(int(port_id),)), None),
                ),
            )

    df.host_name = host_name
    df.port_name = port_name
    df.carbon_host = carbon_host
    df.carbon_port = carbon_port
    df.port_id = int(port_id)
    df.job_info = job_info

    df.addCallback(receive)

def info():
    return { 
            'time' : time(),
            'in' : None,
            'out' : None,
            'status' : 'UNKNOWN'
            }

if __name__ == "__main__":
    from optparse import OptionParser
    from pysnmp.entity import engine, config
    from pysnmp.carrier.twisted import dispatch
    from pysnmp.carrier.twisted.dgram import udp
    from twisted.internet.task import LoopingCall
    from logging import basicConfig, DEBUG

    basicConfig(level=DEBUG, format='%(asctime)s %(levelname)s %(message)s')

    parser = OptionParser()
    parser.add_option('--name', dest='name',
            help='host name')
    parser.add_option('--host', dest='host',
            help='host ip')
    parser.add_option('--community', dest='community',
            help='host community')
    parser.add_option('--portid', dest='port_id',
            help='port id', type='int')
    parser.add_option('--carbon-host', dest='carbon_host',
            help='carbon host')
    parser.add_option('--carbon-port', dest='carbon_port',
            help='carbon port', type='int')
    parser.add_option('--portname', dest='port_name',
            help='port name')
    parser.add_option('--v2c', action='store_true',
            dest='v2c', default=False)

    (options, args) = parser.parse_args()

    snmpEngine = engine.SnmpEngine()
    snmpEngine.registerTransportDispatcher(dispatch.TwistedDispatcher())
    config.addSocketTransport(snmpEngine, udp.domainName, udp.UdpTwistedTransport().openClientMode())
    

    config.addV1System(snmpEngine, options.name, options.community)

    if not options.v2c:
        config.addTargetParams(snmpEngine, options.name, options.name, 
                'noAuthNoPriv', 0)
    else:
        config.addTargetParams(snmpEngine, options.name,
                options.name, 'noAuthNoPriv', 1)
    config.addTargetAddr(
            snmpEngine, 
            options.name,   
            config.snmpUDPDomain,
            (options.host, 161),
            options.name)

    job_info = info()

    job = LoopingCall( fetch, *( 
                                snmpEngine,
                                options.carbon_host,
                                options.carbon_port,
                                options.name,
                                job_info,
                                options.port_name,
                                options.port_id
                                ))

    job.start(10)
    reactor.run()
    





    

    

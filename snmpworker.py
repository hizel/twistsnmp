from twisted.internet import reactor, defer
from pysnmp.entity import engine, config
from pysnmp.carrier.twisted import dispatch
from pysnmp.carrier.twisted.dgram import udp
from pysnmp.entity.rfc3413.twisted import cmdgen
from pysnmp.smi import builder, view, error

mibBuilder = builder.MibBuilder().loadModules('SNMPv2-MIB', 'IF-MIB')
mibView = view.MibViewController(mibBuilder)


snmpEngine = engine.SnmpEngine()
snmpEngine.registerTransportDispatcher(dispatch.TwistedDispatcher())

config.addV1System(snmpEngine, 'agent1', 'public')
config.addTargetParams(snmpEngine, 'params1', 'agent1', 'noAuthNoPriv', 1)
config.addTargetAddr(
        snmpEngine, 'gals', config.snmpUDPDomain,
        ('10.24.0.1', 161), 'params1'
        )

config.addSocketTransport(
        snmpEngine,
        udp.domainName,
        udp.UdpTwistedTransport().openClientMode()
        )

def receiveResponse((errorIndication, errorStatus, errorIndex, varBinds)):
    if errorIndication or errorStatus:
        print 'Error: ', errorIndication, errorStatus.prettyPrint(), errorIndex
        reactor.stop()
        return
    for oid, val in varBinds:
        if val is None:
            print oid.prettyPrint()
        else:
            print '%s = %s' % (oid.prettyPrint(), val.prettyPrint())
    reactor.stop()

getCmdGen = cmdgen.GetCommandGenerator()
df = getCmdGen.sendReq(
        snmpEngine, 'gals', ((mibView.getNodeName(('ifHCInOctets',))[0] + (1,), None),)
        )

df.addCallback(receiveResponse)

reactor.run()

from util import GetCommandGenerator

def receive((errorIndication, errorStatus, errorIndex, varBinds, cbCtx)):
    pass


def fetch(snmpEngine, host_name, port_name, port_id):
    ifHCInOctets = (1,3,6,1,2,1,31,1,1,1,6)
    ifHCOutOctets = (1,3,6,1,2,1,31,1,1,1,10)
    getCmdGen = GetCommandGenerator()
    df = getCmdGen.sendReq(
            snmpEngine,
            host_name,
            (
                (ifHCInOctets+(port_id,), None),
                (ifHCOutOctets+(port_id,), None),
                ),
            )

    df.addCallBack(receive)
    

#!/usr/bin/env python

from twisted.internet import defer
from pysnmp.entity.rfc3413 import cmdgen
from twisted.internet.protocol import Protocol
from logging import debug, error, info


class CarbonProtocol(Protocol):
    def __init__(self, values):
        self.values = values

    def sendMessage(self):
        for path, value, timestamp in self.values:
            debug('send %s %s %s' % (path, value, timestamp))
            self.transport.write('%s %s %s\n' % (path, value,
                timestamp))
            self.transport.loseConnection()

def _cbFun(sendRequestHandle, errorIndication,
        errorStatus, errorIndex, varBinds, cbCtx):
    cbCtx.callback((errorIndication, errorStatus, errorIndex, varBinds, cbCtx))

class GetCommandGenerator(cmdgen.GetCommandGenerator):
    def sendReq(
            self,
            snmpEngine,
            addrName,
            varBinds,
            contextEngineId=None,
            contextName=''
            ):
        df = defer.Deferred()
        cmdgen.GetCommandGenerator.sendReq(
                self,
                snmpEngine,
                addrName,
                varBinds,
                _cbFun,
                df,
                contextEngineId,
                contextName
                )
        return df
    def _handleResponse(
            self,
            snmpEngine,
            transportDomain,
            transportAddress,
            messageProcessingModel,
            securityModel,
            securityName,
            securityLevel,
            contextEngineId,
            contextName,
            pduVersion,
            PDU,
            timeout,
            retryCount,
            pMod,
            rspPDU,
            sendRequestHandle,
            (cbFun, cbCtx)
            ):
        cbCtx.callback(
                (None,
                    pMod.apiPDU.getErrorStatus(rspPDU),
                    pMod.apiPDU.getErrorIndex(rspPDU),
                    pMod.apiPDU.getVarBinds(rspPDU),
                    cbCtx)
                )

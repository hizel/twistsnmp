#!/usr/bin/env python

from twisted.internet import defer
from pysnmp.entity.rfc3413 import cmdgen

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

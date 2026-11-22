"""Separate exact and legacy sequence entrypoints in staged build34."""

from build34_exact_submit import once
from build34_exact_vm_ready import stage as previous_stage
from test_build34_exact_ownership import method


DISPATCH = 'IOReturn IOAccelPhxNativeClient::externalMethod('
EXACT_ROUTE = '    if (selector == PHX34_R3_SEL_SUBMIT_RECEIPT)\n'
MODE_GATE = '''    const bool exactSelector = selector == PHX34_R3_SEL_SUBMIT_RECEIPT ||
        selector == PHX34_R3_SEL_WAIT_RECEIPT || selector == PHX34_R3_SEL_ACK_RECEIPT;
    const bool legacySelector = selector == PHXN_SEL_SUBMIT || selector == PHXN_SEL_WAITSEQ;
    if ((exactSelector && !exactOwnership) || (legacySelector && exactOwnership))
        return kIOReturnUnsupported;
'''


def stage(source):
    source = previous_stage(source)
    dispatch = method(source, DISPATCH)
    return once(source, dispatch, once(dispatch, EXACT_ROUTE, MODE_GATE + EXACT_ROUTE))

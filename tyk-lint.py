#!/usr/bin/python3

# Script to warn about config errors and gotchas in tyk's configuration files
# Will need to eventually allow more than one gateway config file and be able to check if they are consistent

from io import UnsupportedOperation
import json
import argparse, sys

DEBUG=False

# a list of functins that can be used to compare trigger values in GatewayConfigChecks with in with actual values in the config file
def isTrue(compare, acutal):
    return acutal

def isFalse(compare, actual):
    return not actual

def isEqual(compare, actual):
    return compare == actual

def isNE(compare, actual):
    return compare != actual

def isGT(compare, actual):
    return actual > compare

def isLT(compare, actual):
    return actual < compare

def isGE(compare, actual):
    return actual >= compare

def isLE(compare, actual):
    return actual <= compare

def isThere(compare, actual):
    return actual

# define all the checks to perform here
GatewayConfigChecks = {
    'health_check.enable_health_checks': {
        'checkFn': isTrue,
        'compare': True,
        'message': 'is set. Performance will suffer'
    },
    'health_check.health_check_value_timeouts': {
        'checkFn': isGT,
        'compare': 0,
        'getvalue': True,
        'message': 'is greater than 0. This will panic many versions of the gateway if the API healthcheck endpoit is called'
    },
    'hash_key_function': {
        'checkFn': isThere,
        'compare': '',
        'message': 'is defined. Check for hash_key_function_fallback and the possibility of lost encrypted certs and keys'
    },
    'health_check_endpoint_name':{
        'checkFn': isNE,
        'compare': '/hello',
        'getValue': True,
        'message': 'is defined. Check that /hello as not been renamed'
    },
    'analytics_config.enable_detailed_recording': {
        'checkFn': isTrue,
        'compare': True,
        'message': 'is set. Performace will suffer'
    },
    'uptime_tests.disable': {
        'checkFn': isFalse,
        'compare': False,
        'message': 'is set. Look for uptime checks in APIs'
    },
    'uptime_tests.config.time_wait': {
        'checkFn': isGT,
        'compare': 25,
        'getValue': True,
        'message': 'is greater than 25. Uptime tests may never trigger'
    }
}

def checkVal(config, checkObj, checkPath):
    if '.' not in checkPath:
        if checkPath in config:
            # check that value against compare.
            if 'getValue' in checkObj and checkObj['getValue']:
                    checkObj['Value'] = config[checkPath]
            if checkObj['checkFn'](checkObj['compare'], config[checkPath]):
                return checkObj['message']
        else:
            if DEBUG:
                return 'is unset'
    else:
        splitPath=checkPath.split('.')
        firstPath=splitPath[0]
        restofPath='.'.join(splitPath[1:])
        return checkVal(config[firstPath], checkObj, restofPath)


def gatewayChecks(g):
    # various checks on the gateway config
    for check in GatewayConfigChecks:
        result = checkVal(g, GatewayConfigChecks[check], check)
        if result:
            if 'getValue' in GatewayConfigChecks[check] and GatewayConfigChecks[check]['getValue']:
                print('[WARN]Gateway:',"'"+check+"'", '('+str(GatewayConfigChecks[check]['Value'])+')', result)
            else:
                print('[WARN]Gateway:',"'"+check+"'", result)
    return


def main():
    parser = argparse.ArgumentParser(description='Check tyk config files for errors and gotchas')
    parser.add_argument('-g', '--gatewayConfig', type=str, help='Gateway config file "tyk.conf"')
    parser.add_argument('-d', '--dashboardConfig', type=str, help='Dashboard config file "tyk_analytics.conf"')
    parser.add_argument('-t', '--TIBConfig', type=str, help='TIB config file "tib.conf"')
    parser.add_argument('-p', '--pumpConfig', type=str, help='Pump config file "pump.conf"')

    parser.add_argument('-v', dest='verbose', action='store_true')
    args = parser.parse_args()

    # load the files
    if args.gatewayConfig:
        with open(args.gatewayConfig) as gateway_json:
            G=json.load(gateway_json)
            gatewayChecks(G)


if __name__ == "__main__":
    main()
#!/usr/bin/python3

# Script to warn about config errors and gotchas in tyk's configuration files
# Will need to eventually allow more than one gateway config file and be able to check if they are consistent

from io import UnsupportedOperation
import json
import argparse, sys

DEBUG=False

# a list of functins that can be used to compare trigger values in *ConfigChecks with in with actual values in the config file
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

# A sample test
#    'health_check.health_check_value_timeouts': {          # this is the config path to check
#        'checkFn': isGT,                                   # the function that will return true to trigger the message being printed
#        'compare': 0,                                      # the vaule to compare. Here we compare 'config value is greater than 0'
#        'reportValue': True,                               # the makes the diagnostic output include the value from the config file
#                                                           # "message" is printed when checkFN returns true when the key values is compared with compare
#        'message': 'is greater than 0. This will panic many versions of the gateway if the API healthcheck endpoint is called'
#    },
# in this case we get the following printed when the value in the gateway config is > 0
# [WARN]Gateway: 'health_check.health_check_value_timeouts' (60) is greater than 0. This will panic many versions of the gateway if the API healthcheck endpoint is called

# Define all the simple checks to perform on the gateway config file
GatewayConfigChecks = {
    'health_check.enable_health_checks': {
        'checkFn': isTrue,
        'compare': True,
        'message': 'is set. Performance will suffer, redis will have added load.'
    },
    'health_check.health_check_value_timeouts': {
        'checkFn': isGT,
        'compare': 0,
        'reportValue': True,
        'message': 'is greater than 0. This will panic many versions of the gateway if the API healthcheck endpoint is called'
    },
    'hash_key_function': {
        'checkFn': isThere,
        'compare': '',
        'reportValue': True,
        'message': 'is defined. Check for hash_key_function_fallback and the possibility of lost encrypted certs and keys if it has been changed'
    },
    'health_check_endpoint_name':{
        'checkFn': isNE,
        'compare': '/hello',
        'reportValue': True,
        'message': 'is defined. /hello has been renamed'
    },
    'analytics_config.enable_detailed_recording': {
        'checkFn': isTrue,
        'compare': True,
        'message': 'is set. Performace will suffer, redis will have added load.'
    },
    'uptime_tests.disable': {
        'checkFn': isFalse,
        'compare': False,
        'message': 'is False. Look for uptime checks in APIs'
    },
    'uptime_tests.config.time_wait': {
        'checkFn': isGT,
        'compare': 25,
        'reportValue': True,
        'message': 'is greater than ~25. Uptime tests may never trigger'
    }
}

# Define all the simple checks to perform on the pump config file
PumpConfigChecks = {
    'dont_purge_uptime_data': {
        'checkFn': isTrue,
        'compare': True,
        'message': 'is set. Uptime checks will never be moved to redis.'
    }
}

# Define all the simple checks to perform on the pump config file
DashboardConfigChecks = {
    'force_api_defaults': {
        'checkFn': isTrue,
        'compare': True,
        'message': 'is set. tyk-sync will not be able to match up synced policies with APIs.'
    }
}

# check if the 'compare' matches the value in the config (by calling the checkFn) and return the 'message' if it matches
def checkVal(config, checkObj, checkPath):
    if '.' not in checkPath:
        checkFn = checkObj['checkFn']
        if checkPath in config:
            # check that value against compare.
            if 'reportValue' in checkObj and checkObj['reportValue']:
                checkObj['Value'] = config[checkPath]
            if checkFn(checkObj['compare'], config[checkPath]):
                return checkObj['message']
        else:
            # harder to handle missing values. Just deal with the fact that missing booleans are 'False'
            if isinstance(checkObj['compare'], bool):
                if 'reportValue' in checkObj and checkObj['reportValue']:
                    checkObj['Value'] = False
                # Missing implies False so use that
                if checkFn(checkObj['compare'], False):
                    return checkObj['message']
            elif DEBUG:
                return 'is unset'
    else:
        splitPath=checkPath.split('.')
        firstPath=splitPath[0]
        restofPath='.'.join(splitPath[1:])
        return checkVal(config[firstPath], checkObj, restofPath)


# check the json of the config file against the given checks
def SimpleChecks(componentName, jsonConfig, ConfigChecks):
    for checkName in ConfigChecks:
        check = ConfigChecks[checkName]
        result = checkVal(jsonConfig, check, checkName)
        if result:
            if 'reportValue' in check and check['reportValue']:
                print('[WARN]' + componentName + ':',"'"+checkName+"'", '('+str(check['Value'])+')', result)
            else:
                print('[WARN]' + componentName + ':',"'"+checkName+"'", result)
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
        with open(args.gatewayConfig) as gatewayJsonFile:
            G=json.load(gatewayJsonFile)
            SimpleChecks('Gateway', G, GatewayConfigChecks)
            gatewayConfigPresent = True
    if args.pumpConfig:
        with open(args.pumpConfig) as pumpJsonFile:
            P=json.load(pumpJsonFile)
            SimpleChecks('Pump', P, PumpConfigChecks)
            pumpConfigPresent = True
    if args.dashboardConfig:
        with open(args.dashboardConfig) as dashboardJsonFile:
            D=json.load(dashboardJsonFile)
            SimpleChecks('Dashboard', D, DashboardConfigChecks)
            dashboardConfigPresent = True

if __name__ == "__main__":
    main()
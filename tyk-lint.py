#!/usr/bin/python3

# Script to Warn about config errors and gotchas in tyk's configuration files
# Will need to eventually allow more than one gateway config file and be able to check if they are consistent

from io import UnsupportedOperation
import json
import argparse, sys
from typing import get_args

DEBUG=False
LOGLEVEL = ["Warn"]

# a list of functions that can be used to compare trigger values in *ConfigChecks with in with actual values in the config file
# these have to be defined before they can be referenced in the dictionaries below
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

def checkGWPolicies(GWconfig, checkObj):
    if getVal(GWconfig, 'policies.policy_source') == 'service':
        # policy string needs to be the same as 'db_app_conf_options.connection_string'
        # and not empty
        connection_string = getVal(GWconfig, 'db_app_conf_options.connection_string')
        policy_connection_string = getVal(GWconfig, 'policies.policy_connection_string')
        #print("[DEBUG]" + policy_connection_string)
        if policy_connection_string == "":
            checkObj['message'] = "policy_connection_string is empty. Gateway won't start"
            checkObj['logLevel'] = ["Fatal"]
            checkObj['Value'] = "fred1"
            return checkObj['message']
        if connection_string != policy_connection_string:
            checkObj['message'] = policy_connection_string + "doesn't match db_app_conf_options.connection_string"
            checkObj['logLevel'] = ["Fatal"]
            checkObj['Value'] = "fred2"
            return checkObj['message']

# A sample test
#    'health_check.health_check_value_timeouts': {          # this is the config path to check
#        'checkFn': isGT,                                   # the function that will return true to trigger the message being printed
#        'compare': 0,                                      # the vaule to compare. Here we compare 'config value is greater than 0'
#        'reportValue': True,                               # the makes the diagnostic output include the value from the config file
#                                                           # "message" is printed when checkFN returns true when the key values is compared with compare
#        'message': 'is greater than 0. This will panic many versions of the gateway if the API healthcheck endpoint is called'
#        'logLevel: ["Warn"]                                # list of log levels to print at. Defaults to Warn
#    },
# in this case we get the following printed when the value in the gateway config is > 0
# [Warn]Gateway: 'health_check.health_check_value_timeouts' (60) is greater than 0. This will panic many versions of the gateway if the API healthcheck endpoint is called

# Define all the simple checks to perform on the gateway config file
GatewayConfigChecks = {
    # if 'health_check.enable_health_checks' is True we will load redis
    'health_check.enable_health_checks': {
        'checkFn': isTrue,
        'compare': True,
        'message': 'is set. Performance will suffer, redis will have added load.',
        'logLevel': ["Perf", "Warn"]
    },
    # if 'health_check.health_check_value_timeouts' is > 0 most versions of the gateway panic (TT-3349)
    # TODO: Not good enough because the health checks need to be enabled too
    'health_check.health_check_value_timeouts': {
        'checkFn': isGT,
        'compare': 0,
        'reportValue': True,
        'message': 'is greater than 0. This will panic many versions of the gateway if the API healthcheck endpoint is called',
        'logLevel': ["Warn"]
    },
    # When 'hash_key_function' is changed during the life of an install keys will be inaccessible unless hash_key_function_fallback is set
    'hash_key_function': {
        'checkFn': isThere,
        'compare': '',
        'reportValue': True,
        'message': 'is defined. Check for hash_key_function_fallback and the possibility of lost keys if it has been changed',
        'logLevel': ["Info"]
    },
    # 'health_check_endpoint_name' renames /hello
    'health_check_endpoint_name':{
        'checkFn': isNE,
        'compare': '/hello',
        'reportValue': True,
        'message': 'is defined. /hello has been renamed',
        'logLevel': ["Info"]
    },
    # 'analytics_config.enable_detailed_recording' will load redis if set to True
    'analytics_config.enable_detailed_recording': {
        'checkFn': isTrue,
        'compare': True,
        'message': 'is set. Performace will suffer, redis will have added load.',
        'logLevel': ["Perf", "Warn"]
    },
    # if 'uptime_tests.disable' is set to false uptime checks will be enabled
    'uptime_tests.disable': {
        'checkFn': isFalse,
        'compare': False,
        'message': 'is False. Look for uptime checks in APIs',
        'logLevel': ["Info"]
    },
    # if 'uptime_tests.config.time_wait' is more than about 25 seconds, uptime tests will never trigger an outage. 2.9.6~rcxxx is the only fixed version
    # but it looks like 3.0.9 and 4.0.1 will fix this (TT-2479)
    'uptime_tests.config.time_wait': {
        'checkFn': isGT,
        'compare': 25,
        'reportValue': True,
        'message': 'is greater than ~25 seconds. Uptime tests may never trigger',
        'logLevel': ["Warn"]
    },
    'policies': {
        'checkFn': checkGWPolicies
    }
}

# Define all the simple checks to perform on the pump config file
PumpConfigChecks = {
    # 'dont_purge_uptime_data' must be True for uptime data to pump
    'dont_purge_uptime_data': {
        'checkFn': isTrue,
        'compare': True,
        'message': 'is set. Uptime checks will never be moved to redis.',
        'logLevel': ["Warn"]
    }
}

# Define all the simple checks to perform on the pump config file
DashboardConfigChecks = {
    # 'force_api_defaults' will stop tyk-sync from being able to match up APIs and policies when you push them to the dashboard
    'force_api_defaults': {
        'checkFn': isTrue,
        'compare': True,
        'message': 'is set. tyk-sync will not be able to match up synced policies with APIs.',
        'logLevel': ["Fatal"]
    }
}

# get a value from the given config 
def getVal(config, checkPath):
    if '.' not in checkPath:
        if checkPath in config:
            if DEBUG:
                print("[DEBUG]getVal returning '"+str(config[checkPath])+"' for " + checkPath)
            return config[checkPath]
        else:
            return None
    else:
        splitPath=checkPath.split('.')
        firstPath=splitPath[0]
        restofPath='.'.join(splitPath[1:])
        if firstPath in config:
            return getVal(config[firstPath], restofPath)        

# check if the 'compare' matches the value in the config (by calling the checkFn) and return the 'message' if it matches
# Populates checkObj['Value'] if 'reportValue' is true
def checkVal(config, checkObj, checkPath):
        checkFn = checkObj['checkFn']
        configVal = getVal(config, checkPath)
        if 'compare' in checkObj:
            # simple compare against given value
            if configVal is not None:
                # check that value against compare.
                if 'reportValue' in checkObj and checkObj['reportValue']:
                    checkObj['Value'] = configVal
                if checkFn(checkObj['compare'], configVal):
                    return checkObj['message']
            else:
                # harder to handle missing values. Just deal with the fact that missing booleans are 'False'
                if isinstance(checkObj['compare'], bool):
                    if 'reportValue' in checkObj and checkObj['reportValue']:
                        checkObj['Value'] = False
                    # Missing implies False so use that
                    if checkFn(checkObj['compare'], False):
                        return checkObj['message']
        else:
            # call a the checkFn with the full config
            return checkFn(config, checkObj)

# are we configured to print the log level of this check?
def shouldPrint(logLevelList):
    # print("Checking if " + " ".join(logLevelList) + " is in " + " ".join(LOGLEVEL))
    for level in logLevelList:
        if level in LOGLEVEL:
            return True

# a check can have multiple log levels. Report the one that matches
def getLogLeveMatch(logLevelList):
    for level in logLevelList:
        if level in LOGLEVEL:
            return level

def printResult(check, componentName, checkName, result):
    if 'logLevel' in check:
        logLevelList = check['logLevel']
    else:
        # default to Info if not specified in the check
        logLevelList = ['Info']
    if shouldPrint(logLevelList):
        if 'reportValue' in check and check['reportValue']:
            print('[' + getLogLeveMatch(logLevelList) + ']' + componentName + ':',"'"+checkName+"'", '('+str(check['Value'])+')', result)
        else:
            print('[' + getLogLeveMatch(logLevelList) + ']' + componentName + ':',"'"+checkName+"'", result)

# check the json of the config file against the given checks
def SingleConfigFileChecks(componentName, jsonConfig, ConfigChecks):
    for checkName in ConfigChecks:
        if DEBUG:
            print("[DEBUG]Checking '" + checkName + "'")
        check = ConfigChecks[checkName]
        result = checkVal(jsonConfig, check, checkName)
        if result is not None and result:
            if DEBUG:
                print("[DEBUG]Result is '" + result + "'")
            printResult(check, componentName, checkName, result)
    return

def main():
    parser = argparse.ArgumentParser(description='Check tyk config files for errors and gotchas')
    parser.add_argument('-g', '--gatewayConfig', type=str, help='Gateway config file "tyk.conf"')
    parser.add_argument('-d', '--dashboardConfig', type=str, help='Dashboard config file "tyk_analytics.conf"')
    parser.add_argument('-t', '--TIBConfig', type=str, help='TIB config file "tib.conf"')
    parser.add_argument('-p', '--pumpConfig', type=str, help='Pump config file "pump.conf"')
    parser.add_argument('-l', '--logLevel', type=str, help='Level of checks to report. One of: "Fatal", "Warn", "Info", "Perf". Default is "warn"')
    parser.add_argument('-v', dest='verbose', action='store_true')
    args = parser.parse_args()

    # setup the log level
    global LOGLEVEL
    if args.logLevel:
        if args.logLevel in [ 'f', 'fatal', 'Fatal']:
            LOGLEVEL = ["Fatal"]
        elif args.logLevel in [ 'w', 'warn', 'Warn']:
            LOGLEVEL = ["Warn", "Fatal"]
        elif args.logLevel in ['i', 'info', 'Info']:
            LOGLEVEL = ["Info", "Warn", "Fatal"]
        elif args.logLevel in ['p', 'perf', 'Perf']:
            LOGLEVEL = ["Perf"]
        else:
            print("[FATAL]Unknown log level")
            sys.exit(1)
    else:
        # default to Warn and above if not specified
        LOGLEVEL = ["Warn", "Fatal"]
    
    # load the files
    if args.gatewayConfig:
        with open(args.gatewayConfig) as gatewayJsonFile:
            G=json.load(gatewayJsonFile)
            SingleConfigFileChecks('Gateway', G, GatewayConfigChecks)
            gatewayConfigPresent = True
    if args.pumpConfig:
        with open(args.pumpConfig) as pumpJsonFile:
            P=json.load(pumpJsonFile)
            SingleConfigFileChecks('Pump', P, PumpConfigChecks)
            pumpConfigPresent = True
    if args.dashboardConfig:
        with open(args.dashboardConfig) as dashboardJsonFile:
            D=json.load(dashboardJsonFile)
            SingleConfigFileChecks('Dashboard', D, DashboardConfigChecks)
            dashboardConfigPresent = True
    # need to call the checks with multiple config files here

if __name__ == "__main__":
    main()
#!/usr/bin/python3

# Script to Warn about config errors and gotchas in tyk's configuration files
# Will need to eventually allow more than one gateway config file and be able to check if they are consistent

from io import UnsupportedOperation
import json
import argparse, sys
from typing import get_args
import functools

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


# from https://stackoverflow.com/questions/43491287/elegant-way-to-check-if-a-nested-key-exists-in-a-dict
def haskey(config, path):
    try:
        functools.reduce(lambda x, y: x[y], path.split("."), config)
        return True
    except KeyError:
        return False

# from https://stackoverflow.com/questions/43491287/elegant-way-to-check-if-a-nested-key-exists-in-a-dict
# Throwing in this approach for nested get for the heck of it...
def getkey(config, path, *default):
    try:
        return functools.reduce(lambda x, y: x[y], path.split("."), config)
    except KeyError:
        if default:
            return default[0]
        raise

#####################################################################################################
#####################################################################################################
#####################################  Gateway config checks ########################################
#####################################################################################################
#####################################################################################################

# To use '“disable_dashboard_zeroconf”: false' you need to make sure that policy.policy_connection_string and db_app_conf_options.connection_string are not defined.
# If policy.policy_connection_string and db_app_conf_options.connection_string are defined, they need to be right no matter what disable_dashboard_zeroconf is set to
def checkGWConnectionString(GWconfig):
    app_connection_string = getkey(GWconfig, 'db_app_conf_options.connection_string', "")
    policy_connection_string = getkey(GWconfig, 'policies.policy_connection_string', "")
    if DEBUG:
        print(f"app_connection_string = {app_connection_string!r}, policy_connection_string = {policy_connection_string!r}")
    # deal with API definitions (db_app config items)
    if getkey(GWconfig, 'use_db_app_configs', False):
        # dashboard has APIs for us
        if getkey(GWconfig, 'disable_dashboard_zeroconf', False):
            # zero conf is disabled
            if app_connection_string == "":
                # dashboard connection string is missing
                logFatal(GWconfig, "db_app_conf_options.connection_string is empty or missing and zeroconf is turned off. Gateway won't start.")
        else:
            # zeroconf is enabled
            if app_connection_string == "":
                logFatal(GWconfig, "db_app_conf_options.connection_string is empty and zeroconf is enabled. Gateway won't start.")
            else:
                logInfo(GWconfig, "db_app_conf_options.connection_string is populated and zeroconf is enabled. Not much use having zeroconf on")
    else:
        # we're not looking to the dashboard for APIs
        logInfo(GWconfig, "use_db_app_configs is false. Gateway is running in CE or RPC mode")
    # deal with policy settings
    if getkey(GWconfig, 'policies.policy_source', "") == 'service':
        if getkey(GWconfig, 'disable_dashboard_zeroconf', False):
            # disable_dashboard_zeroconf is true so policies.policy_connection_string must be set
            if policy_connection_string == "":
                logFatal(GWconfig, "db_app_conf_options.connection_string is empty or missing and zeroconf is turned off. Gateway won't start.")
        else:
            # using disable_dashboard_zeroconf=false. policies.policy_connection_string must be set or totally missing
            if haskey(GWconfig, "policies.policy_connection_string"):
                if policy_connection_string == "":
                    logFatal(GWconfig, "policies.policy_connection_string is empty and zeroconf is enabled. Gateway won't start.")
    # if policy_connection_string and db_app_conf_options.connection_string are not empty, check that they are the same
    if policy_connection_string != "" and app_connection_string != "" and app_connection_string != policy_connection_string:
        logFatal(GWconfig, "db_app_conf_options.connection_string and policies.policy_connection_string are different. They must be the same")

# if enable_analytics and analytics_config.enable_detailed_recording
# then detailed analytics will be sent to redis which can be a big performance hit
def checkGWAnalytics(GWConfig):
    if getkey(GWConfig, 'enable_analytics', False):
        if getkey(GWConfig, 'analytics_config.enable_detailed_recording', False):
            logWarn(GWConfig, "analytics_config.enable_detailed_recording is active. Performace will suffer, redis will have added load.")

#####################################################################################################
#####################################################################################################
######################################### Log Functions #############################################
#####################################################################################################
#####################################################################################################
def logFatal(ConfigJson, message):
    configFileName = ConfigJson['__CONFIG-FILE']
    if shouldPrint(["Fatal"]):
        print(f"[Fatal]{configFileName}: {message}")

def logWarn(ConfigJson, message):
    configFileName = ConfigJson['__CONFIG-FILE']
    if shouldPrint(["Warn"]):
        print(f"[Warn]{configFileName}: {message}")

def logInfo(ConfigJson, message):
    configFileName = ConfigJson['__CONFIG-FILE']
    if shouldPrint(["Info"]):
        print(f"[Info]{configFileName}: {message}")

# A sample test
#    'health_check.health_check_value_timeouts': {          # this is the config path to check
#        'checkFn': isGT,                                   # the function that will return true to trigger the message being printed
#        'compare': 0,                                      # the vaule to compare. Here we compare 'config value is greater than 0'
#        'reportValue': True,                               # the makes the diagnostic output include the value from the config file
#                                                           # "message" is printed when checkFN returns true when the key values is compared with compare
#        'message': 'is greater than 0. This will panic many versions of the gateway if the API healthcheck endpoint is called'
#        'logLevel: ["Warn"]                                # list of log levels to print at. Defaults to Warn
#    },

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
        'message': 'is greater than 0. This will panic many versions of the gateway if the API healthcheck endpoint is called.',
        'logLevel': ["Warn"]
    },
    # When 'hash_key_function' is changed during the life of an install keys will be inaccessible unless hash_key_function_fallback is set
    'hash_key_function': {
        'checkFn': isThere,
        'compare': '',
        'reportValue': True,
        'message': 'is defined. Check for hash_key_function_fallback and the possibility of lost keys if it has been changed.',
        'logLevel': ["Info"]
    },
    # 'health_check_endpoint_name' renames /hello
    'health_check_endpoint_name':{
        'checkFn': isNE,
        'compare': '/hello',
        'reportValue': True,
        'message': 'is defined. /hello has been renamed.',
        'logLevel': ["Info"]
    },
    # if 'uptime_tests.disable' is set to false uptime checks will be enabled
    'uptime_tests.disable': {
        'checkFn': isFalse,
        'compare': False,
        'message': 'is False. Look for uptime checks in APIs.',
        'logLevel': ["Info"]
    },
    # if 'uptime_tests.config.time_wait' is more than about 25 seconds, uptime tests will never trigger an outage. 2.9.6~rcxxx is the only fixed version
    # but it looks like 3.0.9 and 4.0.1 will fix this (TT-2479)
    'uptime_tests.config.time_wait': {
        'checkFn': isGT,
        'compare': 25,
        'reportValue': True,
        'message': 'is greater than ~25 seconds. Uptime tests may never trigger.',
        'logLevel': ["Warn"]
    },
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

# check if the 'compare' matches the value in the config (by calling the checkFn) and return the 'message' if it matches
# Populates checkObj['Value'] if 'reportValue' is true
def checkVal(config, checkObj, checkPath):
        checkFn = checkObj['checkFn']
        configVal = getkey(config, checkPath, False)
        if haskey(checkObj, 'compare'):
            # simple compare against given value
            if configVal is not None:
                # check that value against compare.
                if haskey(checkObj, 'reportValue') and getkey(checkObj, 'reportValue', False):
                    checkObj['Value'] = configVal
                if checkFn(checkObj['compare'], configVal):
                    return checkObj['message']
            else:
                # harder to handle missing values. Just deal with the fact that missing booleans are 'False'
                if isinstance(checkObj['compare'], bool):
                    if haskey(checkObj, 'reportValue') and getkey(checkObj, 'reportValue', False):
                        checkObj['Value'] = False
                    # Missing implies False so use that
                    if checkFn(checkObj['compare'], False):
                        return checkObj['message']
        else:
            # call a the checkFn with the full config
            return checkFn(config, checkObj)

# are we configured to print the log level of this check?
def shouldPrint(logLevelList):
    if DEBUG:
        print(f"[DEBUG][shouldPrint]Checking if {logLevelList!r} is in {LOGLEVEL!r}")
    for level in logLevelList:
        if level in LOGLEVEL:
            return True

# a check can have multiple log levels. Report the one that matches
def getLogLeveMatch(logLevelList):
    for level in logLevelList:
        if level in LOGLEVEL:
            return level

def printResult(check, configFileName, checkName, result):
    if 'logLevel' in check:
        logLevelList = check['logLevel']
    else:
        # default to Info if not specified in the check
        logLevelList = ['Info']
    if shouldPrint(logLevelList):
        if 'reportValue' in check and check['reportValue']:
            print(f"[{getLogLeveMatch(logLevelList)}]{configFileName}: {checkName!r} ({check['Value']!r}) {result}")
        else:
            print(f"[{getLogLeveMatch(logLevelList)}]{configFileName}: {checkName!r} {result}")

# check the json of the config file against the given checks
def SingleConfigFileChecks(jsonConfig, ConfigChecks):
    configFileName = jsonConfig['__CONFIG-FILE']
    for checkName in ConfigChecks:
        if DEBUG:
            print(f"[DEBUG][SingleConfigFileChecks]checking {configFileName!r} for {checkName!r}")
        check = ConfigChecks[checkName]
        result = checkVal(jsonConfig, check, checkName)
        if DEBUG:
            print(f"[DEBUG][SingleConfigFileChecks]result from checkVal({checkName!r}) is {result!r}")
        if result is not None and result:
            printResult(check, configFileName, checkName, result)
    return

# Call all the gateway check functions
def ComplexGatewayChecks(GWConfig):
    checkGWConnectionString(GWConfig)
    checkGWAnalytics(GWConfig)

def main():
    global LOGLEVEL
    global DEBUG
    parser = argparse.ArgumentParser(description='Check tyk config files for errors and gotchas')
    parser.add_argument('-g', '--gatewayConfig', type=str, help='Gateway config file "tyk.conf"')
    parser.add_argument('-d', '--dashboardConfig', type=str, help='Dashboard config file "tyk_analytics.conf"')
    parser.add_argument('-t', '--TIBConfig', type=str, help='TIB config file "tib.conf"')
    parser.add_argument('-p', '--pumpConfig', type=str, help='Pump config file "pump.conf"')
    parser.add_argument('-l', '--logLevel', type=str, help='Level of checks to report. One of: "Fatal", "Warn", "Info", "Perf". Default is "warn"')
    parser.add_argument('-D', '--DEBUG', dest='DEBUG', action='store_true', help="Enable debug output")

    args = parser.parse_args()
    if args.DEBUG:
        DEBUG=True

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
            G['__CONFIG-FILE'] = args.gatewayConfig
            SingleConfigFileChecks(G, GatewayConfigChecks)
            ComplexGatewayChecks(G)
            gatewayConfigPresent = True
    if args.pumpConfig:
        with open(args.pumpConfig) as pumpJsonFile:
            P=json.load(pumpJsonFile)
            P['__CONFIG-FILE'] = args.pumpConfig
            SingleConfigFileChecks(P, PumpConfigChecks)
            pumpConfigPresent = True
    if args.dashboardConfig:
        with open(args.dashboardConfig) as dashboardJsonFile:
            D=json.load(dashboardJsonFile)
            D['__CONFIG-FILE'] = args.dashboardConfig
            SingleConfigFileChecks(D, DashboardConfigChecks)
            dashboardConfigPresent = True
    # need to call the checks with multiple config files here

if __name__ == "__main__":
    main()
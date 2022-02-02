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

#####################################################################################################
######################################### Log Functions #############################################
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

#####################################################################################################
########################################## key lookups ##############################################
#####################################################################################################

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
#####################################  Gateway config checks ########################################
#####################################################################################################

# this is a collection of more simple checks on the gateway config.
def GatewaySimpleChecks(GWConfig):
    # if 'health_check.enable_health_checks' is True redis load will increase
    if haskey(GWConfig, 'health_check.enable_health_checks'):
        if getkey(GWConfig, 'health_check.enable_health_checks', False):
            logWarn(GWConfig, 'health_check.enable_health_checks is set. Performance will suffer, redis will have added load.')
            if haskey(GWConfig, 'health_check.health_check_value_timeouts'):
                health_check_value_timeouts = getkey(GWConfig, 'health_check.health_check_value_timeouts', 0)
                if health_check_value_timeouts > 0:
                    # if 'health_check.health_check_value_timeouts' is > 0 most versions of the gateway panic (TT-3349)
                    logWarn(GWConfig, f"health_check.health_check_value_timeouts({health_check_value_timeouts}) is greater than 0 which will panic many versions of the gateway")
    # When 'hash_key_function' is changed during the life of an install keys will be inaccessible unless hash_key_function_fallback is set
    if haskey(GWConfig, 'hash_key_function'):
        hash_key_function = getkey(GWConfig, 'hash_key_function', "")
        if hash_key_function != "":
            logInfo(GWConfig, f"hash_key_function is {hash_key_function!r}. When hash_key_function is changed during the life of an install keys will be inaccessible unless 'hash_key_function_fallback' is set")
    # 'health_check_endpoint_name' renames /hello
    if haskey(GWConfig, 'health_check_endpoint_name'):
        health_check_endpoint_name = getkey(GWConfig, 'health_check_endpoint_name', "")
        if health_check_endpoint_name != '/hello' and health_check_endpoint_name != "":
            logInfo(GWConfig, f'health_check_endpoint_name has been renamed to {health_check_endpoint_name!r}')
    # if 'uptime_tests.disable' is missing or false uptime checks will be enabled
    if not getkey(GWConfig, 'uptime_tests.disable', False):
        logInfo(GWConfig, 'API endpoint health checks are enabled')
        if haskey(GWConfig, 'uptime_tests.config.time_wait'):
            uptime_test_config_time_wait=getkey(GWConfig, 'uptime_tests.config.time_wait', 0)
            if uptime_test_config_time_wait > 25:
                # if 'uptime_tests.config.time_wait' is more than about 25 seconds, uptime tests will never trigger an outage. 2.9.6~rcxxx is the only fixed version
                # but it looks like 3.0.9 and 4.0.1 will fix this (TT-2479)
                logWarn(GWConfig, f'uptime_tests.config.time_wait({uptime_test_config_time_wait}) is greater than 25 seconds. Uptime tests may never detect a down endpoint.')
    # if enable_analytics and analytics_config.enable_detailed_recording are true
    # then detailed analytics will be sent to redis which can be a big performance hit
    if getkey(GWConfig, 'enable_analytics', False):
        if getkey(GWConfig, 'analytics_config.enable_detailed_recording', False):
            logWarn(GWConfig, "analytics_config.enable_detailed_recording is active. Performace will suffer, redis will have added load.")

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

#####################################################################################################
####################################### Pump config checks ##########################################
#####################################################################################################

def PumpSimpleChecks(PumpConfig):
    # if 'dont_purge_uptime_data' is true uptime logs will not be available
    if getkey(PumpConfig, 'dont_purge_uptime_data', False):
        logWarn(PumpConfig, 'dont_purge_uptime_data is set, uptime logs will not be available')
    # 'health_check_endpoint_name' renames /hello
    if haskey(PumpConfig, 'health_check_endpoint_name'):
        health_check_endpoint_name = getkey(PumpConfig, 'health_check_endpoint_name', "")
        if health_check_endpoint_name != '/hello' and health_check_endpoint_name != "":
            logInfo(PumpConfig, f'health_check_endpoint_name has been renamed to {health_check_endpoint_name!r}')
    # 'health_check_endpoint_port' defaults to 8083
    if haskey(PumpConfig, 'health_check_endpoint_port'):
        health_check_endpoint_port = getkey(PumpConfig, 'health_check_endpoint_port', 8083)
        if health_check_endpoint_port != 8083:
            logInfo(PumpConfig, f'health_check_endpoint_port has been changed to {health_check_endpoint_port!r}')

#####################################################################################################
#################################### Dashboard config checks ########################################
#####################################################################################################

def DashboardSimpleChecks(DashboardConfig):
    # 'force_api_defaults' will stop tyk-sync from being able to match up APIs and policies when you push them to the dashboard
    if getkey(DashboardConfig, 'force_api_defaults', False):
        logFatal(DashboardConfig, "force_api_defaults is set. tyk-sync will not be able to match up synced policies with APIs.")
    # 'health_check_endpoint_name' renames /hello
    if haskey(DashboardConfig, 'health_check_endpoint_name'):
        health_check_endpoint_name = getkey(DashboardConfig, 'health_check_endpoint_name', "")
        if health_check_endpoint_name != '/hello' and health_check_endpoint_name != "":
            logInfo(DashboardConfig, f'health_check_endpoint_name has been renamed to {health_check_endpoint_name!r}')
    # 'listen_port' changes default port from 300
    if haskey(DashboardConfig, 'listen_port'):
        listen_port = getkey(DashboardConfig, 'listen_port', 3000)
        if listen_port != 3000:
            logWarn(DashboardConfig, f'listen_port has been changed to {listen_port!r}')

#####################################################################################################
##################################### Multiple config checks ########################################
#####################################################################################################

def SecretsCheck(GWConfig, DashboardConfig, PumpConfig):
    # tyk_analytics.conf: tyk_api_config.Secret -> tyk.conf: secret
    if haskey(GWConfig, 'secret') and haskey(DashboardConfig, 'tyk_api_config.Secret'):
        GWsecret = getkey(GWConfig, 'secret')
        DashboardSecret = getkey(DashboardConfig, 'tyk_api_config.Secret')
        if GWsecret != DashboardSecret:
            DashboardConfigFile = DashboardConfig['__CONFIG-FILE']
            logFatal(GWConfig, f"Gateway 'secret: {GWsecret}' doesn't match dashboard {DashboardConfigFile}: 'tyk_api_config.Secret: {DashboardSecret}'")
    # tyk_analytics.conf: shared_node_secret -> tyk.conf: node_secret -> tib.conf: TykAPISettings.GatewayConfig.AdminSecret
    # TODO: parse the TIB config file
    if haskey(GWConfig, 'node_secret') and haskey(DashboardConfig, 'shared_node_secret'):
        GWNodeSecret = getkey(GWConfig, 'node_secret')
        DashboardNodeSecret = getkey(DashboardConfig, 'shared_node_secret')
        if GWNodeSecret != DashboardNodeSecret:
            DashboardConfigFile = DashboardConfig['__CONFIG-FILE']
            logFatal(GWConfig, f"Gateway 'node_secret: {GWNodeSecret}' doesn't match dashboard {DashboardConfigFile}: 'shared_node_secret: {DashboardNodeSecret}'")

# Call all the gateway check functions
def GatewayConfigChecks(GWConfig):
    checkGWConnectionString(GWConfig)
    GatewaySimpleChecks(GWConfig)

def DashboardConfigChecks(DashboardConfig):
    DashboardSimpleChecks(DashboardConfig)

def PumpConfigChecks(PumpConfig):
    PumpSimpleChecks(PumpConfig)

def MultifileChecks(GWConfig, DashboardConfig, PumpConfig):
    SecretsCheck(GWConfig, DashboardConfig, PumpConfig)
    #MongoConnectionStringChecks(GWConfig, DashboardConfig, PumpConfig)
    #RedisConnectionStringChecks(GWConfig, DashboardConfig, PumpConfig)

def main():
    global LOGLEVEL
    global DEBUG
    G = {}
    D = {}
    P = {}
    parser = argparse.ArgumentParser(description='Check tyk config files for errors and gotchas')
    parser.add_argument('-g', '--gatewayConfig', type=str, help='Gateway config file "tyk.conf"')
    parser.add_argument('-d', '--dashboardConfig', type=str, help='Dashboard config file "tyk_analytics.conf"')
    parser.add_argument('-t', '--TIBConfig', type=str, help='TIB config file "tib.conf"')
    parser.add_argument('-p', '--pumpConfig', type=str, help='Pump config file "pump.conf"')
    parser.add_argument('-l', '--logLevel', type=str, help='Level of checks to report. One of: "Fatal", "Warn", "Info". Default is "Warn"')
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
        #elif args.logLevel in ['p', 'perf', 'Perf']:
        #    LOGLEVEL = ["Perf"]
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
            GatewayConfigChecks(G)
    if args.dashboardConfig:
        with open(args.dashboardConfig) as dashboardJsonFile:
            D=json.load(dashboardJsonFile)
            D['__CONFIG-FILE'] = args.dashboardConfig
            DashboardConfigChecks(D)
    if args.pumpConfig:
        with open(args.pumpConfig) as pumpJsonFile:
            P=json.load(pumpJsonFile)
            P['__CONFIG-FILE'] = args.pumpConfig
            PumpConfigChecks(P)

    # need to call the checks with multiple config files here
    MultifileChecks(G, D, P)

if __name__ == "__main__":
    main()

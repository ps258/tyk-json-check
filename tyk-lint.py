#!/usr/bin/python3

# Script to warn about config errors and gotchas in tyk's configuration files
# Will need to eventually allow more than one gateway config file and be able to check if they are consistent

import json
import argparse, sys

def isTrue(acutal):
    return acutal

def isFalse(actual):
    return not actual

def isEqual(desired, actual):
    return desired == actual

def isGT(desired, actual):
    return actual > desired

def isLT(desired, actual):
    return actual < desired

def isGE(desired, actual):
    return actual >= desired

def isLE(desired, actual):
    return actual <= desired


GatewayConfigChecks = {
    'health_check.enable_health_checks': 
        {
            'checkFn': isTrue,
            'compare': True,
            'message': 'Performance will suffer'
        },
    'health_check.health_check_value_timeouts':
        {
            'checkFn': isGT,
            'compare': 0,
            'message': 'This will panic many versions of the gateway if the healthcheck endpoit is called'

        }
    
}


def gatewayChecks(g):
    # various checks on the gateway config
    if 'health_check' in g:
        if 'enable_health_checks' in g['health_check']:
            if g['health_check']['enable_health_checks']:
                print("[WARN]Gateway: health_check.enable_health_checks is set. Performance will suffer")
        if 'health_check_value_timeouts' in g['health_check']:
            if g['health_check']['health_check_value_timeouts'] > 0:
                print("[WARN]Gateway: health_check.health_check_value_timeouts is non-zero. This will panic many versions of the gateway if the endpoit is called")

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
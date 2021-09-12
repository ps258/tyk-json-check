package main

import (
	"flag"
	"fmt"
	"io/ioutil"
	"os"

	"github.com/TykTechnologies/tyk/cli/linter"
)

var (
	gwJsonFile   string
	dshbJsonFile string
	apiJsonFile  string
	pumpJsonFile string
)

func init() {
	flag.StringVar(&gwJsonFile, "gateway", "", "Gateway config file")
	flag.StringVar(&dshbJsonFile, "dashboard", "", "Dashboard config file")
	flag.StringVar(&pumpJsonFile, "pump", "", "Pump config file")
	flag.StringVar(&apiJsonFile, "api", "", "API definition file")
}

func main() {
	// load and marshal the config files
	// then depending on which ones are loaded perform a series of sanity checks.
	confSchema, err := ioutil.ReadFile("schema.json")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	var confPaths []string
	confPaths = append(confPaths, gwJsonFile)
	path, lines, err := linter.Run(string(confSchema), confPaths)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if len(lines) == 0 {
		fmt.Printf("found no issues in %s\n", path)
		os.Exit(0)
	}
	fmt.Printf("issues found in %s:\n", path)
	for _, line := range lines {
		fmt.Println(line)
	}
	os.Exit(1)
}

# Kansa carbon black integration
Implements kansa without windows remoting needing to be enabled in the environment. As Carbon Black already has SYSTEM rights, most of this stuff should be trivial.

* https://github.com/davehull/Kansa

# Before you start:
* pip3 install -r requirements.txt 
* Have a cbapi config file ready (~/.carbonblack/credentials.response) with a [default] system (Details: https://github.com/carbonblack/cbapi-python)
* Run ./setup.sh, which will copy necessary data from the Kansa github repo and set things up

## Examples:
Generate list of targets (Based on groupid 1 within the last day~):
```bash
$ python3 getsensors.py
```

Run kansa on these targets, and get data back:
```bash
$ python3 kansa.py --target somehost.evil.corp
```

Get help:
```bash
$ python3 kansa.py --help
```

This will run Kansa on the targets specified with all available modules. You will then find all output data in a folder matching Output\_d{14} (timestamped)

## Implemented / fixed
* Handle sessions based on max sessions
* Handle timeouts and machines going offline
* Parse configuration file for modules
* Added setup script for getting data from https://github.com/davehull/Kansa 
* Automate finding targets that are alive from Carbon Black
* Test threading thoroughly for multiple targets 
* Check for offline sessions if they come online
* Handle maximum sessions based on input
* Hardcoded folderlocations 
* FIX error handling for sensors
* Calculate time till finished
* Make a loading bar :)
* Track how far in the script it's done

## Todo:
* Analysis - Need a remote host for the analysis (or run script from windows host) OR remake scripts. 
* Multithread result checking (more than one item.result(timeout=x)
* Verify if pushbin works for extra modules
* Check which modules have to be modified
* Move data for analysis after each iteration
* Fix upper and lowercase for executables 
* Fix save location for executables
* Add verbose and debug logging 

## Workflow
1. Find active hosts based on input
2. Pack data based on Modules/Modules.conf
3. Zip and transfer data to remote targets
4. Run Kansa on max sessions untill everything is analyzed
5. Retrieve results 
6. Unpack into result_* folder based on timestamp
7. Analyze

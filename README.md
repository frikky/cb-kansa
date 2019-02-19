# Kansa carbon black integration
Implements kansa without windows remoting needing to be enabled in the environment. As Carbon Black already has SYSTEM rights, most of this stuff should be trivial.

* https://github.com/davehull/Kansa

# Before you start:
* pip3 install -r requirements.txt 
* Have a cbapi config file ready (~/.carbonblack/credentials.response) with a [default] system (Details: https://github.com/carbonblack/cbapi-python)
* Run ./setup.sh, which will copy necessary data from the Kansa github repo and set things up

## Example:
Generate list of targets (Based on groupid 1 within the last day~):
```bash
$ python3 getsensors.py
```

Run kansa on these targets, and get data back:
```bash
$ python3 kansa.py --targetlist alltargets.txt 
```

Get help:
```bash
$ python3 kansa.py --help
```

This will run Kansa on the targets specified with all available modules. You will then find all output data in a folder matching Output\_d{14} (timestamped)

## Todo:
* Analysis - Might need a remote host for the analysis to not remake the scripts. 
* Fix upper and lowercase for executables 
* Fix save location for executables
* FIX error handling for sensors

## Done ish
* Configuration file for modules
* Added setup script for getting data from dave hull
* Automate finding targets that are alive from Carbon Black - Made a PoC
* Test threading thoroughly for multiple targets  
* Hardcoded folderlocations 

## Workflow
1. Find active hosts based on input
2. Pack data based on Modules/Modules.conf
3. Zip and transfer data to remote targets
4. Run Kansa on all targets
5. Retrieve results 
6. Unpack into result_* folder based on timestamp
7. Analyze

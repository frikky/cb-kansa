# Kansa carbon black integration
Implements kansa without windows remoting needing to be enabled in the environment. As Carbon Black already has SYSTEM rights, most of this stuff should be trivial.

There are bugs, as this is currently just a PoC.

* https://github.com/davehull/Kansa

# Before you start:
* pip install cbapi 
* Have a cbapi config file ready
* Run ./setup.sh, which will copy necessary data from the Kansa github repo 
* Good to go!

## Example:
Generate list of targets (Based on groupid 1 within the last day~):
```bash
$ python getsensors.py
```

Run kansa on these targets, and get data back:
```bash
$ python3 kansa.py --targetlist alltargets.txt --pushbin true
```

This will run Kansa on the targets specified with all available modules. You will then find all output data in a folder matching Output\_d{14} (timestamped)

## Todo:
* Analysis - Might need a remote host for the analysis to not remake the scripts. 
* Test threading thoroughly for multiple targets - They have job based api :)
* Fix upper and lowercase for executables 
* Fix save location for executables
* Hardcoded folderlocations 
* Change the ugly powershell commands to be pretty (:
* FIX error handling for sensors

## Done ish
* Configuration file for modules
* Added setup script for getting data from dave hull
* Automate finding targets that are alive from Carbon Black - Made a PoC

## Workflow
Get targetlist, Package data, loop targets and run kansa on the target

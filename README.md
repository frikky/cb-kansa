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
```bash
$ python kansa.py -targetlist <targetfile> -pushbin true
```

This will run Kansa on the targets specified with all available modules. You will then find all output data in a folder matching Output\_d{14} (timestamped)

## Todo:
* Analysis - Might need a remote host for the analysis, to not remake the scripts. 
* Test threading thoroughly for multiple targets
* Fix upper and lowercase for executables 
* Fix save location for executables
* Automate finding targets that are alive from Carbon Black
* Hardcoded folderlocations etc
* Change the ugly powershell commands to be pretty (:

## Done ish
* Configuration file for modules
* Added setup script for getting data from dave hull

## Workflow
Get targetlist, Package data, loop targets and run kansa on the target

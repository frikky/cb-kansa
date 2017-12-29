# Kansa carbon black integration
Implements kansa without windows remoting needing to be enabled in the environment. As Carbon Black is already SYSTEM, most of this stuff should be trivial.

* https://github.com/davehull/Kansa

# Before you start:
* Have cbapi installed
* Have a cbapi config file ready
* Get Kansa into the directory (cb-kansa/kansa.ps1, cb-kansa/Modules, etc..)

# Example:
```bash
\> python kansa.py -targetlist <targetfile> -pushbin true
```

This will run Kansa on the targets specified with all available modules

# Todo:
* Analysis - Find how the data should be saved and analysed 
* Specify modules
* Configuration file
* Test threading thoroughly for multiple targets
* Fix upper and lowercase for executables 
* Automate finding targets that are alive from Carbon Black
* Hardcoded folderlocations etc
* Change the ugly powershell commands to be pretty
* Add a powerforensics file script as well :)

# Modified files for testing (everything is saved as normal):
* Get-Autorunsc.ps1 - Added C:\temp\\\* as a usable path for autoruns.
* 

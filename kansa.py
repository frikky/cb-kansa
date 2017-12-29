import os
import zipfile 
import requests
import argparse 
from shutil import copy, copytree, rmtree

import cbapi # Used for error handling
from cbapi.response import *

parser = argparse.ArgumentParser("Kansa", description="Carbon Black parser for Kansa")

# Send target
parser.add_argument("-targetlist", default="", help="Add a targetlist")
#parser.add_argument("--TargetCount", help="Do stuff")
parser.add_argument("-target", default="", help="Add a target")
parser.add_argument("-ModulePath", default="", help="Add modules to be used")
parser.add_argument("-pushbin", default=False, help="Push depencies")

class Kansa(object):
    def __init__(self): 
        self.args = parser.parse_args()
        self.targets = []
        self.modules = []
        self.cb = CbResponseAPI()

    # Handles input parameters
    def handle_arguments(self):
        targets = []
        if self.args.targetlist:
            if self.check_target_list():
                self.targets = open(self.args.targetlist, "r").read().splitlines()
            else:
                print "File \"%s\" doesn't exist" % self.args.targetlist
                exit()

        # Doesnt overwrite targetlist
        if self.args.target and not self.args.targetlist:
            self.targets.append(self.args.target)

        if self.args.ModulePath:
            for item in self.args.ModulePath.split(","):
                self.modules.append(item)

            print "\n".join(self.modules)
        else:
            # FIX - need to do subfolders etc.
            # FIX - maybe this should follow the conf file :/
            modulepath = "Modules/Modules.conf"
            configfile = self.get_configuration_paths(modulepath)
            for item in configfile: 
                self.modules.append(item) 

            self.modules.append(modulepath)

            """
            # Old use with all modules
            for folder in os.listdir("Modules"):
                # Skipping files - cba properly for testing
                try:
                    for item in os.listdir("Modules/%s" % folder):
                        self.modules.append("Modules/%s/%s" % (folder, item))
                except OSError:
                    # Hardcoded for conf
                    if folder == "Modules.conf":
                        self.modules.append("Modules/Modules.conf")
                    continue
            """

    # Parses configurationfile
    def get_configuration_paths(self, configpath):
        paths = []
        for line in open(configpath, "r").read().split("\n"):  
            if not line:
                continue

            if not line.endswith(".ps1"):
                continue

            if not line.startswith("#"):
                line = line.replace("\\", "/")
                paths.append("Modules/%s" % line) 

        return paths

    # FIX - don't have stuff hardcoded :) - POC 
    # Finds the data that should be in the sent zipfile
    def pack_target_data(self, foldername):
        if os.path.exists(foldername):
            rmtree(foldername)

        # Need executables and stuff
        os.mkdir(foldername)
        copy("kansa.ps1", "%s/%s" % (foldername, "kansa.ps1"))

        # Loop over all module files, doesn't push possible depencies
        if not self.args.pushbin:
            copytree("Modules", "%s/%s" % (foldername, "Modules"))
            return

        # Finds module binpaths and copies them
        modulepath = "%s/%s" % (foldername, "Modules")

        os.mkdir(modulepath)
        os.mkdir("%s/%s" % (modulepath, "bin"))
        binpaths = []

        # Checks all modules if they have any executable associated
        for item in self.modules:
            binpath = self.get_item(item) 

            if not binpath:
                try:
                    copy(item, "%s/%s" % (foldername, item))
                except IOError:
                    # This seems to work specifically for Kansa. 
                    # No need to os walk and directory creation magic
                    os.mkdir("%s/%s/%s" % (foldername, item.split("/")[-3], item.split("/")[-2]))
                    copy(item, "%s/%s" % (foldername, item))
                continue

            # FIX - check what it's ran on first 
            binpath = binpath.replace("\\", "/")

            # Skip duplicates
            if binpath not in binpaths:
                binpaths.append(binpath)

            # Continue without the module if the binpath doesn't exist (maybe exit?)
            if not os.path.exists(binpath):
                continue

            filename = binpath.split("/")[-1]

            copy(item, "%s/%s" % (foldername, item))
            copy(binpath, "%s/%s" % (foldername, binpath)) 

    # Gets the requried depencies from a used module
    def get_item(self, filepath):
        for line in open(filepath, "r").read().split("\n"):
            if line.startswith("BINDEP"):
                return line.split(" ")[-1]

    # Zips the data to be sent to the remote host
    def compress_target_data(self, foldername):
        folderzip = zipfile.ZipFile("%s.zip" % foldername, "w", zipfile.ZIP_DEFLATED)
        for root, dirs, files in os.walk(foldername):
            for file in files:
                folderzip.write(os.path.join(root, file))

        folderzip.close()
        return "%s.zip" % foldername

    # Checks if the file exists
    def check_target_list(self):
        return os.path.exists(self.args.targetlist)

    # Does all the hard work
    def loop_targets(self, datafoldername, folderlocation, local_location):
        if not self.targets:
            print "Missing targets - exiting."
            exit()
    
        # Manages filenames in a horrible way
        new_filename = ""
        if "/" in local_location:
            new_filename = local_location.split("//")[:-1]
        elif "\\" in local_location:
            new_filename = local_location.split("\\")[:-1]
        else:
            new_filename = local_location

        # Some folder definitions, including save location
        fullfolderlocation = "%s%s\\%s" % (folderlocation, datafoldername, datafoldername)
        default_remote_location = "%s%s" % (folderlocation, new_filename)

        output_folder = ""

        # This is where everything on the targets happens
        # http://cbapi.readthedocs.io/en/latest/live-response.html
        for target in self.targets:
            sensor = self.cb.select(Sensor).where("hostname:%s" % target).first()
            print "Sending data to %s with %d modules" % (target, len(self.modules))
            try:
                with sensor.lr_session() as session:
                    # Puts and prepares the files for running
                    self.put_local_file(session, local_location, default_remote_location)
                    self.unzip_remote(session, folderlocation, local_location)

                    # Runs Kansa on the localhost, and returns with the foldername
                    kansa_ret = self.run_kansa(session, fullfolderlocation)
                    if not kansa_ret:
                        print "Skipping %s" % target
                        print self.cleanup_target(session, datafoldername)
                        continue

                    output_folder = self.find_foldername(kansa_ret)

                    # Uses the foldername to zip, and get it back for later analysis
                    self.zip_remote(session, fullfolderlocation, output_folder)
                    zip_data = session.get_file("%s/%s.zip" % (fullfolderlocation, output_folder))
                    self.save_zip_data(target, zip_data)
                    print self.cleanup_target(session, datafoldername)
            except AttributeError:
                continue

        # Temporary local cleanup
        # FIX - With threading, it might jump here too fast
        rmtree(datafoldername)
        os.remove("%s.zip" % datafoldername)

        # Returns the foldername used for analysis. This will be the timestamp of the last machine.
        return output_folder

    # Cleans up the remote hosts files
    def cleanup_target(self, session, folderpath):
        print "Cleaning up remote host."
        # Use force if it fails? Might be in use. 
        command = "powershell.exe \"Remove-Item \'C:\\temp\\%s\' -Recurse -Force\"" % folderpath
        ret = session.create_process(command)
        return ret

    # Saves it in a temporary location (FIX - Not sure what to do here yet)
    def save_zip_data(self, targetname, zip_data):
        if not os.path.exists("data"):
            print "Creating data folder"
            os.mkdir("data")
        if not os.path.exists("data/%s" % targetname):
            print "Creating %s folder" % targetname
            os.mkdir("data/%s" % targetname)
            
        with open("data/%s/data.zip" % targetname, "w+") as tmp:
            tmp.write(zip_data)

        print "Zipped data locally"
        
    # Finds the foldername specified in the return data used for zipping
    def find_foldername(self, kansa_ret):
        print "Finding foldername in return"
        for line in kansa_ret.split("\n"):
            if "Foldername" in line:
                return line.split(" ")[-1]

    # Pass arguments for kannsa to run like normal
    def run_kansa(self, session, foldername):
        print "Starting analysis with Kansa."
        targetlist = "targetlist.txt"

        # Creates a targetlist, as without targetlist, winremoting is required.
        # The last commands (ls/write-host) are used to find the output folder as this is not part 
        # Fix - handle modules here somehow (self.modules)
        commands = [
            "(echo $env:COMPUTERNAME > %s)" % targetlist,
            #"powershell.exe -exec bypass -File kansa.ps1 -targetlist %s -Modulepath \'.\Modules\'" % targetlist,
            "powershell.exe -exec bypass -File kansa.ps1 -targetlist %s" % targetlist,
            "(Write-Host \'Foldername:\' $(ls | sls -Pattern \'Output_\d{14}\'))"
        ]

        powershell_cmd = 'powershell.exe \"%s\"' % ";".join(commands)

        # FIX - Win32 error code 0x8007010B might occur (or others)
        try:
            ret = session.create_process(powershell_cmd, working_directory=foldername, wait_timeout=300)
        except cbapi.live_response_api.LiveResponseError:
            return False

        print "Done with analysis - Grabbing files"

        return ret

    # Zips the file to get it back from the remote host
    def zip_remote(self, session, folderpath, zipname):
        print "Zipping remote file"
        command = 'powershell.exe \"Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::CreateFromDirectory(\'%s\\%s\', \'%s\\%s.zip\')\"' % (folderpath, zipname, folderpath, zipname)
        ret = session.create_process(command)
        
        return ret

    # Unzips and removes the zipfile
    def unzip_remote(self, session, filepath, zipfile):
        "Unzip payload on remote system"
        filepath = "%s%s" % (filepath, zipfile)
        new_filename = filepath[:-4]

        command = 'powershell.exe \"Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::ExtractToDirectory(\'%s\', \'%s\'); rm \'%s\'\"' % (filepath, new_filename, filepath)
        ret = session.create_process(command)

        return ret

    # Runs all commands involved within a single session
    def put_local_file(self, session, local_location, remote_location): 
        with open(local_location, "rb") as tmp:
            try:
                session.put_file(tmp, remote_location)
            except cbapi.live_response_api.LiveResponseError:
                # FIX - Remove file and reupload, as this most likely means duplication
                pass

            print "Zipfile added. Starting extraction"

    # Have to do some magic since extractall sucks, and cba doing more for now
    def unzip(self, folderpath):
        try:
            z = zipfile.ZipFile('%s/data.zip' % folderpath)
        except IOError:
            return

        z.extractall(folderpath)

    # Reorganizes the data for use with kansa analysis
    def prepare_analysis(self, datafolder, analysisfolder):
        print "Moving files for analysis"

        if not os.path.exists(analysisfolder):
            os.mkdir(analysisfolder)

        filecount = 0
        computercount = 0
        foldercreate = True

        # Finds hosts
        for folder in os.listdir(datafolder):
            self.unzip("%s/%s" % (datafolder, folder))
            
            # Used while testing
            if folder.endswith(".zip"):
                continue

            # Finds hostfiles
            for filename in os.listdir("%s/%s" % (datafolder, folder)): 
                if not filename.endswith(".csv"): 
                    continue
                        
                filenamesplit = filename.split("\\")

                # Creates the folder 
                if foldercreate:
                    curfolder = filenamesplit[0]
                    try:
                        os.mkdir("%s/%s" % (analysisfolder, curfolder))
                    except OSError:
                        foldercreate = False 

                # Moves the file to the associated location
                os.rename(
                    "%s/%s/%s" % (datafolder, folder, filename), 
                    "%s/%s/%s" % (analysisfolder, filenamesplit[0], filenamesplit[1])
                )

                filecount += 1

            # Dont need to recreate folders, so done for efficiency 
            foldercreate = False
            computercount += 1

            # Removes the original folder as its empty 
            #rmtree(datafolder)

        print "%s is now ready for analysis with %d files and %d system(s)" % (analysisfolder, filecount, computercount)

# Testing for uploading data to the endpoint 
if __name__ == "__main__":
    # Prepares data for connection with CB sensor
    kansa = Kansa()
    foldername = "targetdata"
    folderlocation = "c:\\temp\\"

    kansa.handle_arguments()
    kansa.pack_target_data(foldername)
    zipname = kansa.compress_target_data(foldername)

    # Sends the actual data to the targets 
    print "Done preparing data for sending"
    foldername = kansa.loop_targets(foldername, folderlocation, zipname)

    # ANALYSIS
    analysisfolder = "Output_20171229203926"
    datafolder = "data"
    kansa.prepare_analysis(datafolder, analysisfolder)

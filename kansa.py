import os
import zipfile 
import requests
import sys
import argparse 
import commands
import urllib3
from datetime import datetime
from shutil import copy, copytree, rmtree 

import cbapi # Used for error handling
from cbapi.response import *

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
parser = argparse.ArgumentParser("Kansa", description="Carbon Black parser for Kansa")

# Send target
parser.add_argument("--targetlist", default="", help="Add a targetlist")
parser.add_argument("--target", default="", help="Run on a single target")
parser.add_argument("--targetlocation", default="C:\\ProgramData\\", help="Location to save on remote host")
parser.add_argument("--targetfoldername", default="targetdata_%s" % (str(datetime.now().timestamp()).split(".")[0]), help="The foldername in the target location")
parser.add_argument("--ModulePath", default="", help="Add modules to be used")
parser.add_argument("--pushbin", default=False, help="Push depencies")

class Kansa(object):
    def __init__(self): 
        self.args = parser.parse_args()
        self.targets = []
        self.modules = []
        self.skipped = []
        self.cb = CbResponseAPI()

    # Handles input parameters
    def handle_arguments(self):
        targets = []
        if self.args.targetlist:
            if self.check_target_list():
                self.targets = open(self.args.targetlist, "r").read().splitlines()
            else:
                print("File \"%s\" doesn't exist" % self.args.targetlist)
                exit()

        # Doesnt overwrite targetlist
        if self.args.target and not self.args.targetlist:
            self.targets.append(self.args.target)

        modulepath = "Modules/Modules.conf" 
        configfile = self.get_configuration_paths(modulepath)
        for item in configfile: 
            self.modules.append(item) 

        if len(configfile) < 5:
            print("Loaded the following modules: %s" % ", ".join(configfile))
        else:
            print("Loaded %d modules")

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

            if not line.startswith("#"):
                line = line.replace("\\", "/")
                paths.append("Modules/%s" % line) 

        return paths

    # FIX - don't have stuff hardcoded :) - POC 
    # Finds the data that should be in the sent zipfile
    def pack_target_data(self):
        foldername = self.args.targetfoldername
        if os.path.exists(foldername):
            rmtree(foldername)

        # Need executables and stuff
        os.mkdir(foldername)
        copy("kansa.ps1", "%s/%s" % (foldername, "kansa.ps1"))

        # Loop over all module files, doesn't push possible depencies
        if not self.args.pushbin:
            os.mkdir("%s/Modules" % foldername)
            for item in self.modules:
                if " " in item:
                    item = item.split(" ")[0] 

                filepathsplit = item.split("/")

                filepath = "/".join(filepathsplit[:-1])
                try:
                    os.mkdir("%s/%s" % (foldername, filepath))
                except FileExistsError:
                    pass
                
                copy(item, "%s/%s" % (foldername, filepath))

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
    def compress_target_data(self):
        foldername = self.args.targetfoldername
        folderzip = zipfile.ZipFile("%s.zip" % foldername, "w", zipfile.ZIP_DEFLATED)
        for root, dirs, files in os.walk(foldername):
            for file in files:
                folderzip.write(os.path.join(root, file))

        folderzip.close()
        return "%s.zip" % foldername

    # Checks if the file exists
    def check_target_list(self):
        return os.path.exists(self.args.targetlist)

    def get_all_results(self, object, fullfolderlocation, output_folder):
        for sensor in self.all_sensors:
            jobcheck = self.cb.live_response.submit_job(object, sensor)

            try:
                # Check if sensor is online at all?
                self.save_zip_data(sensor.computer_name, jobcheck.result())
            except (cbapi.errors.TimeoutError, cbapi.live_response_api.LiveResponseError) as e:
                print(e)
                continue

    def run_command(self, object, critical=True):
        if len(self.all_sensors) <= 0:
            print("No more sensors. All failed")
            exit()

        # Not sure what max concurrent should be
        # FIXME
        maxconcurrent = 50
        jobs = []
        for sensor in self.all_sensors:
            jobs.append(self.cb.live_response.submit_job(object, sensor))

        # This verifies if worked 100% 
        if not critical:
            print("Running %d concurrent jobs" % len(jobs))
            cnt = 0
            removed = 0
            for item in jobs:
                result = item.result(timeout=60)
                if result == False:
                    self.all_sensors.remove(self.all_sensors[cnt-removed]) 
                    removed += 1
                    
                cnt += 1

        # FIX - should remove sensors that aren't being scanned while underway

        # Does all the hard work
    def loop_targets(self, local_location):
        datafoldername = self.args.targetfoldername

        if not self.targets:
            print("Missing targets - exiting.")
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
        fullfolderlocation = "%s%s\\%s" % (self.args.targetlocation, datafoldername, datafoldername)
        default_remote_location = "%s%s" % (self.args.targetlocation, new_filename)
        output_folder = "result_%s" % (str(datetime.now().timestamp()).split(".")[0])

        # This is where everything on the targets happens
        # http://cbapi.readthedocs.io/en/latest/live-response.html

        # FIX - Not sure if this should loop targets or loop commands
        job = commands.handleAllJobs(local_location, default_remote_location, self.args.targetlocation, fullfolderlocation, datafoldername, outputfolder=output_folder)

        # Finds all target sensors
        self.all_sensors = []
        for target in self.targets:
            sensor = self.cb.select(Sensor).where("hostname:%s" % target)

            # This can prolly be done in the search
            for item in sensor:
                if item.status == "Uninstall Pending":
                    continue

                if item.status != "Offline":
                    self.all_sensors.append(item)
                else:
                    self.skipped.append(item)

                break

        if len(self.skipped) > 5:
            print("Skipped %d sensors because they're offline." % len(self.skipped))  
        elif len(self.skipped) > 0 and len(self.skipped) <= 5:
            text = "Skipped the following sensors because they're offline: "
            for item in self.skipped:
                text += "%s, " % item.hostname

            print(text[:-2])

        if len(self.all_sensors) <= 0:
            print("No sensors to scan - exiting")
            exit()

        if len(self.all_sensors) < 5:
            text = "Loaded the following sensors: "
            for item in self.all_sensors:
                text += "%s, " % item.hostname

            print(text[:-2])
        else:
            print("Loaded %d online sensor(s)" % len(self.all_sensors))

        print("Putting files on all targets")
        self.run_command(job.put_local_file)

        print("Unzipping on all targets")
        self.run_command(job.unzip_remote)

        print("Running kansa on all targets")
        kansa_ret = self.run_command(job.run_kansa)

        print("Zipping remote datafolder")
        self.run_command(job.zip_remote)

        print("Getting all files - this will take a while")
        self.get_all_results(job.get_zip_data, fullfolderlocation, output_folder)

        # Good to have either way, as the user might have gotten some of the data, but not all etc.
        print("Cleaning up local host and remote targets.")
        self.run_command(job.cleanup_target)

        # Returns the foldername used for analysis. This will be the timestamp of the last machine.
        return output_folder

    # Saves it in a temporary location (FIX - Not sure what to do here yet)
    def save_zip_data(self, targetname, zip_data):
        if not os.path.exists("data"):
            print("Creating data folder")
            os.mkdir("data")
        if not os.path.exists("data/%s" % targetname):
            print("Creating %s folder" % targetname)
            os.mkdir("data/%s" % targetname)

        with open("data/%s/data.zip" % targetname, "wb+") as tmp:
            tmp.write(zip_data)

        print("Zipped data locally")
        
    # Have to do some magic since extractall sucks, and cba doing more for now
    def unzip(self, folderpath):
        try:
            z = zipfile.ZipFile('%s/data.zip' % folderpath)
        except IOError:
            return

        z.extractall(folderpath)

    # Reorganizes the data for use with kansa analysis
    # This step is uneccesary, but I don't want to redo the mess above just yet :)
    def prepare_analysis(self, datafolder, analysisfolder):
        print("Moving files for analysis")

        if not os.path.exists(datafolder):
            os.mkdir(datafolder)

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

        print("%s is now ready for analysis with %d file(s) and %d system(s)" % (analysisfolder, filecount, computercount))

# Cleans up the remote hosts files
    def cleanup_local(self):
        #rmtree(datafoldername)
        #os.remove("%s.zip" % datafoldername)

        foldernamecheck = self.args.targetfoldername
        if "_" in self.args.targetfoldername:
            foldernamecheck = self.args.targetfoldername.split("_")[0]

        for item in os.listdir():
            #if item.startswith("Output"):
            #    rmtree(item)
            if item.startswith(foldernamecheck):
                try:
                    rmtree(item)
                except NotADirectoryError:
                    os.remove(item)

        try:
            rmtree("__pycache__")
        except OSError:
            pass

        try:
            rmtree("targetdata.zip")
        except OSError:
            pass


# Testing for uploading data to the endpoint 
if __name__ == "__main__":
    # Prepares data for connection with CB sensor
    kansa = Kansa()

    kansa.handle_arguments()
    kansa.pack_target_data()
    zipname = kansa.compress_target_data()

    # Sends the actual data to the targets 
    analysisfolder = kansa.loop_targets(zipname)

    # ANALYSIS
    datafolder = "data"
    kansa.prepare_analysis(datafolder, analysisfolder)

    kansa.cleanup_local()

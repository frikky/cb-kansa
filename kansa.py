import os
import zipfile 
import requests
import argparse 
from shutil import copy, copytree, rmtree
import commands
import urllib3

import cbapi # Used for error handling
from cbapi.response import *

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
parser = argparse.ArgumentParser("Kansa", description="Carbon Black parser for Kansa")

# Send target
parser.add_argument("--targetlist", default="", help="Add a targetlist")
#parser.add_argument("--TargetCount", help="Do stuff")
parser.add_argument("--target", default="", help="Run on a single target")
parser.add_argument("--targetlocation", default="C:\\temp\\", help="Location to save on remote host")
parser.add_argument("--ModulePath", default="", help="Add modules to be used")
parser.add_argument("--pushbin", default=False, help="Push depencies")

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
                print("File \"%s\" doesn't exist" % self.args.targetlist)
                exit()

        # Doesnt overwrite targetlist
        if self.args.target and not self.args.targetlist:
            self.targets.append(self.args.target)

        if self.args.ModulePath:
            for item in self.args.ModulePath.split(","):
                self.modules.append(item)

            print("\n".join(self.modules))
        else:
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

    def get_all_results(self, object, fullfolderlocation, output_folder):
        for sensor in self.all_sensors:
            jobcheck = self.cb.live_response.submit_job(object, sensor)

            self.save_zip_data(sensor.computer_name, jobcheck.result())

    def run_command(self, object):
        for sensor in self.all_sensors:
            jobcheck = self.cb.live_response.submit_job(object, sensor)

        # FIX - should remove sensors that aren't being scanned while underway
        return jobcheck.result()

    #def run_command(self, job, fullfolderlocation):
    #    output_folder = "Output_2018123123"
    #    job.outputfolder = output_folder
    #    
    #    for sensor in self.all_sensors:
    #        print("Running commands on %s" % sensor.computer_name)
    #        self.cb.live_response.submit_job(job.put_local_file, sensor)
    #        print("Unzipping data on %s" % sensor.computer_name)
    #        self.cb.live_response.submit_job(job.unzip_remote, sensor)
    #        print("Running Kansa on %s" % sensor.computer_name)
    #        self.cb.live_response.submit_job(job.run_kansa, sensor)
    #        print("Running unzipping on %s" % sensor.computer_name)
    #        self.cb.live_response.submit_job(job.zip_remote, sensor)
    #        print("Getting all files - this will take a while")
    #        self.get_all_results(job.get_zip_data, fullfolderlocation, output_folder)

    # Does all the hard work
    def loop_targets(self, datafoldername, local_location):
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

        output_folder = ""

        # This is where everything on the targets happens
        # http://cbapi.readthedocs.io/en/latest/live-response.html

        # FIX - Not sure if this should loop targets or loop commands
        job = commands.handleAllJobs(local_location, default_remote_location, self.args.targetlocation, fullfolderlocation, datafoldername, outputfolder="")

        # Finds all target sensors
        self.all_sensors = []
        for target in self.targets:
            sensor = self.cb.select(Sensor).where("hostname:%s" % target).first()
            self.all_sensors.append(sensor)

        print("Putting files on all targets")
        self.run_command(job.put_local_file)

        print("Unzipping on all targets")
        self.run_command(job.unzip_remote)

        print("Running kanza on all targets")
        kansa_ret = self.run_command(job.run_kansa)

        output_folder = self.find_foldername(kansa_ret)
        job.outputfolder = output_folder

        print("Zipping remote datafolder")
        self.run_command(job.zip_remote)

        print("Getting all files - this will take a while")
        self.get_all_results(job.get_zip_data, fullfolderlocation, output_folder)

        # Good to have either way, as the user might have gotten some of the data, but not all etc.
        print("Cleaning up all targets")
        self.run_command(job.cleanup_target)

        print("Cleaning up local host.")
        rmtree(datafoldername)
        os.remove("%s.zip" % datafoldername)

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
        
    # Finds the foldername specified in the return data used for zipping
    def find_foldername(self, kansa_ret):
        print("Finding foldername in return")
        for line in kansa_ret.decode("utf-8").split("\n"):
            if "Foldername" in line:
                return line.split(" ")[-1]

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

        print("%s is now ready for analysis with %d files and %d system(s)" % (analysisfolder, filecount, computercount))

# Testing for uploading data to the endpoint 
if __name__ == "__main__":
    # Prepares data for connection with CB sensor
    kansa = Kansa()
    foldername = "targetdata"

    kansa.handle_arguments()
    kansa.pack_target_data(foldername)
    zipname = kansa.compress_target_data(foldername)

    # Sends the actual data to the targets 
    print("Done preparing data for sending")
    analysisfolder = kansa.loop_targets(foldername, zipname)

    # ANALYSIS
    datafolder = "data"
    kansa.prepare_analysis(datafolder, analysisfolder)

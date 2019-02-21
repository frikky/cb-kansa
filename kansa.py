import os
import zipfile 
import requests
import sys
import time
import argparse 
import commands
import urllib3
import concurrent
import logging
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
parser.add_argument("--maxsessions", default=9, help="Max concurrent sessions in carbon black")
parser.add_argument("--timeout", default=5, help="Timeout in seconds per request. Default: 5")

logfolder = "./logs"
if not os.path.exists(logfolder):
    print("Made %s for logging" % logfolder)
    os.mkdir(logfolder)

logging.basicConfig(filename="%s/kansa.log" % logfolder, level=logging.INFO)
logging.basicConfig(filename="%s/debug.log" % logfolder, level=logging.DEBUG)
print("Logging to %s/kansa.log" % logfolder)

class Kansa(object):
    def __init__(self): 
        self.args = parser.parse_args()
        self.targets = []
        self.modules = []
        self.skipped = []
        self.online_sensors = []
        self.all_sensors = []
        self.jobs = []
        self.cb = CbResponseAPI()
        self.finished = 0
        self.firsttime = 0
        self.starttime = datetime.now().timestamp()
        try:
            self.max_sessions = int(self.args.maxsessions)
            if self.max_sessions <= 0:
                print("Error: maxsessions needs to be > 0")
                logging.error("Error: maxsessions needs to be > 0")
                exit()

            print("Running with %d concurrent sessions" % self.max_sessions)
            logging.info("Running with %d concurrent sessions" % self.max_sessions)

        except ValueError as e:
            print("Error: %s" % e)
            logging.error("Error: %s" % e)
            exit()
        try:
            self.timeout = int(self.args.timeout)
            if self.timeout < 5:
                print("Error: timeout needs to be at least > 5 because of carbon black delay")
                logging.error("Error: timeout needs to be at least > 5 because of carbon black delay")
                exit()

            print("Running with default timeout: %d" % self.timeout)
            logging.info("Running with default timeout: %d" % self.timeout)

        except ValueError as e:
            print("Error: %s" % e)
            logging.error("Error: %s" % e)
            exit()

        # Setting up logging stuff
        
    # Handles input parameters
    def handle_arguments(self):
        targets = []
        if self.args.targetlist:
            if self.check_target_list():
                self.targets = open(self.args.targetlist, "r").read().splitlines()
            else:
                print("File \"%s\" doesn't exist" % self.args.targetlist)
                logging.error("File \"%s\" doesn't exist" % self.args.targetlist)
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
            logging.info("Loaded the following modules: %s" % ", ".join(configfile))
        else:
            print("Loaded %d modules")
            logging.info("Loaded %d modules")

        self.modules.append(modulepath)

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

            # Does all the hard work
    def loop_targets(self, local_location):
        datafoldername = self.args.targetfoldername

        if not self.targets:
            print("Missing targets - exiting.")
            logging.error("Missing targets - exiting.")
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
        self.job = commands.handleAllJobs(local_location, default_remote_location, self.args.targetlocation, fullfolderlocation, datafoldername, outputfolder=output_folder)

        # Finds all target sensors
        for target in self.targets:
            sensor = self.cb.select(Sensor).where("hostname:%s" % target)

            # This can prolly be done in the search
            for item in sensor:
                if item.status == "Uninstall Pending":
                    continue

                self.all_sensors.append(item)

                if item.status != "Offline":
                    self.online_sensors.append(item)
                else:
                    self.skipped.append(item)

                break

        if len(self.skipped) > 5:
            print("Skipped %d sensors because they're offline." % len(self.skipped))  
            logging.warning("Skipped %d sensors because they're offline." % len(self.skipped))  
        elif len(self.skipped) > 0 and len(self.skipped) <= 5:
            text = "Skipped the following sensors because they're offline: "
            for item in self.skipped:
                text += "%s, " % item.hostname

            print(text[:-2])
            logging.info(text[:-2])

        if len(self.online_sensors) <= 0:
            print("No sensors to scan - exiting")
            logging.error("No sensors to scan - exiting")
            exit()

        if len(self.online_sensors) < 5:
            text = "Loaded the following sensors: "
            for item in self.online_sensors:
                text += "%s, " % item.hostname

            print(text[:-2])
            logging.info(text[:-2])
        else:
            print("Loaded %d online sensor(s)" % len(self.online_sensors))
            logging.info("Loaded %d online sensor(s)" % len(self.online_sensors))

        # Get active sessions
        # FIXME - Make this how the sessions are handled
        # Below is the start of something

        # Should do all session handling
        self.handle_sessions(fullfolderlocation, output_folder)
        return output_folder

    #def get_active_sessions(self):

    def handle_sessions(self, fullfolderlocation, output_folder):
        # Append everything to dictionary hostname: jobfinished
        self.curlist = []
        cnt = 0

        for sensor in self.all_sensors:
            self.curlist.append({"hostname": sensor.hostname})
            self.curlist[cnt]["analyzed"] = False 
            self.curlist[cnt]["inprogress"] = False 
            self.curlist[cnt]["sensor"] = sensor 
            self.curlist[cnt]["timeout"] = self.timeout

            if sensor in self.online_sensors:
                self.curlist[cnt]["online"] = True
            else:
                self.curlist[cnt]["online"] = False 

            cnt += 1

        #print("Finished generated hostlist")
        logging.info("Finished generated hostlist")

        finished = False
        cnt = 0
        currentsessions = 0
        iteration = 0
        self.currentsessions = 0

        logging.info("Started session handling loop")
        self.printProgressBar(prefix = 'Progress:', suffix = '(Online: %d/%d, Finished: 0, Sessions: %d)' % (len(self.online_sensors), len(self.curlist), self.currentsessions), length = 60)
        while(True):
            # Add jobs for items in currentsessions
            # Loop jobs with timeout
            # If finished = append to an array of data and return here:
            # finished = #self.get_all_results(job.get_zip_data, fullfolderlocation, output_folder)
            # for each finished: remove the finished one, and append a new one 
            # Dictionary: {name: hostname, jobran: false/true} 

            # Make currentsession counter every loop
            # This wont work hmm

            # FIXME
            #try:
            #    active_session_count = self.get_session_count() 
            #except cbapi.errors.ApiError:
            #    active_session_count = 0
            active_session_count = 0

            #print("Active sessions: %d, iteration: %d" % (self.currentsessions+active_session_count, iteration))
            logging.info("Active sessions: %d, iteration: %d" % (self.currentsessions+active_session_count, iteration))
            if self.currentsessions == 0 and iteration != 0:
                # Verify, as there might be stuff leftover
                found = False
                for item in self.curlist:
                    if not item["analyzed"]:
                        print("Found something not analyzed ()")
                        logging.info("Found something not analyzed ()")
                        print("THIS PROBABLY MEANS SOMEONE ELSE ARE RUNNING THIS SCRIPT")
                        logging.warning("THIS PROBABLY MEANS SOMEONE ELSE ARE RUNNING THIS SCRIPT")
                        found = True
                        break

                if not found:
                    print("FINISHED FOR ALL TARGETS? :)")
                    logging.info("FINISHED FOR ALL TARGETS? :)")
                    break

            if active_session_count > self.currentsessions:
                self.currentsessions = active_session_count

            # Runs first iteration of commands
            # Basically not in use if the first round works out fine
            if self.currentsessions < self.max_sessions:
                newhosts = []
                for item in self.curlist:
                    if item["analyzed"] or not item["online"]:
                        continue

                    # Move on to check for results with timeout
                    if self.currentsessions == self.max_sessions:
                        break

                    if item["inprogress"]:
                        continue

                    item["inprogress"] = True
                    newhosts.append(item["hostname"])

                    self.new_run_command(self.job.put_local_file, item["sensor"])
                    self.new_run_command(self.job.unzip_remote, item["sensor"])
                    self.new_run_command(self.job.run_kansa, item["sensor"])
                    self.new_run_command(self.job.zip_remote, item["sensor"])

                    # Add to job
                    # Set item[analyzed] to false
                    self.currentsessions += 1

                if len(newhosts) > 0:
                    pass
                    #print("Putting files on %s" % ", ".join(newhosts))
                    logging.info("Putting files on %s" % ", ".join(newhosts))
                    #print("Unzipping %s" % ", ".join(newhosts))
                    logging.info("Unzipping %s" % ", ".join(newhosts))
                    #print("Running kansa on %s" % ", ".join(newhosts))
                    logging.info("Running kansa on %s" % ", ".join(newhosts))
                    #print("Zipping remote datafolder %s" % ", ".join(newhosts))
                    logging.info("Zipping remote datafolder %s" % ", ".join(newhosts))

            # Run analysis here before checking for online sensors again 
            self.curlist = self.new_get_all_results(self.job.get_zip_data, fullfolderlocation, output_folder)

            # Check ALL sensors for every iteration again?
            for item in self.curlist:
                # Don't care about analyzed in list
                if item["analyzed"]:
                    continue

                newsensors = self.cb.select(Sensor).where("hostname:%s" % item["hostname"])
                try:
                    for cursensor in newsensors:
                        # Verifies if same (duplicates exist) with ID
                        if cursensor.id != item["sensor"].id:
                            continue

                        # Checks same host if status has changed
                        if cursensor.status != "Offline" and item["online"] != True:
                            #print("%s just turned online." % item["hostname"])
                            logging.info("%s just turned online." % item["hostname"])
                            item["online"] = True
                            self.online_sensors.append(cursensor)
                        elif cursensor.status == "Offline":
                            if item["online"]:
                                self.online_sensors.append(cursensor)

                            logging.info("%s is offline." % item["hostname"])
                            item["online"] = False 
                            item["inprogress"] = False 

                        # Break anyway, since you never reach here unelss the same sensor
                        break

                except TypeError as e:
                    #print("Error in sensor iteration 2: %s" % e)
                    logging.info("Error in sensor iteration 2: %s" % e)


            iteration += 1

    # Immediately starts a new session 
    # Should return if sessions is 9 already
    def start_new_session(self):
        for item in self.curlist:
            if item["analyzed"] or not item["online"]:
                continue

            # Move on to check for results with timeout
            if self.currentsessions == self.max_sessions:
                break

            if item["inprogress"]:
                continue

            item["inprogress"] = True
            #print("Started new session on %s" % item["hostname"])
            logging.info("Started new session on %s" % item["hostname"])

            self.new_run_command(self.job.put_local_file, item["sensor"])
            self.new_run_command(self.job.unzip_remote, item["sensor"])
            self.new_run_command(self.job.run_kansa, item["sensor"])
            self.new_run_command(self.job.zip_remote, item["sensor"])

            # Set a time here
            #item["starttime"] = 

            # Add to job
            # Set item[analyzed] to false
            self.currentsessions += 1

    def new_get_all_results(self, object, fullfolderlocation, output_folder):
        finishedsensornames = []

        # Loop self.curlist 
        for i in range(len(self.curlist)):
            if not self.curlist[i]["inprogress"]:
                continue

            sensor = self.curlist[i]["sensor"]
            jobcheck = self.cb.live_response.submit_job(object, sensor)

            try:
                # Check if sensor is online at all?
                zipdata = jobcheck.result(timeout=self.curlist[i]["timeout"])

                # only gets here if it doesn't crash
                self.save_zip_data(sensor.computer_name, zipdata)
                self.curlist[i]["inprogress"] = False
                self.curlist[i]["analyzed"] = True 
                #print("Finished saving zipdata for %s" % self.curlist[i]["hostname"])
                logging.info("Finished saving zipdata for %s" % self.curlist[i]["hostname"])
                self.new_run_command(self.job.cleanup_target, self.curlist[i]["sensor"])
                self.currentsessions -= 1

                self.finished += 1
                self.printProgressBar(prefix = 'Progress:', suffix = '(Online: %d/%d, Finished: %d, Sessions: %d)' % (len(self.online_sensors), len(self.curlist), self.finished, self.currentsessions), length = 60)

                #active_session_count = self.get_session_count() 

                # FIXME
                active_session_count = 0
                #print("Active sessions: %d" % active_session_count)
                logging.info("Active sessions: %d" % active_session_count)

                # Immediately start new session
                #if active_session_count < self.max_sessions: 
                if self.currentsessions < self.max_sessions: 
                    self.start_new_session()

                self.printProgressBar(prefix = 'Progress:', suffix = '(Online: %d/%d, Finished: %d, Sessions: %d)' % (len(self.online_sensors), len(self.curlist), self.finished, self.currentsessions), length = 60)

            except (cbapi.errors.TimeoutError, concurrent.futures._base.TimeoutError) as e:
                # Increase time by 10 for each failure
                increase_amount = 10
                logging.info("Increased amount from %d to %d on host %s" % (self.curlist[i]["timeout"], self.curlist[i]["timeout"]+increase_amount, self.curlist[i]["hostname"]))
                self.printProgressBar(prefix = 'Progress:', suffix = '(Online: %d/%d, Finished: %d, Sessions: %d)' % (len(self.online_sensors), len(self.curlist), self.finished, self.currentsessions), length = 60)

                self.curlist[i]["timeout"] += increase_amount

            except cbapi.live_response_api.LiveResponseError as e: 
                continue

        return self.curlist

    def new_run_command(self, object, sensor, critical=True):
        self.jobs.append(self.cb.live_response.submit_job(object, sensor))

    # Saves it in a temporary location (FIX - Not sure what to do here yet)
    def save_zip_data(self, targetname, zip_data):
        if not os.path.exists("data"):
            #print("Creating data folder")
            logging.info("Creating data folder")
            os.mkdir("data")
        if not os.path.exists("data/%s" % targetname):
            #print("Creating %s folder" % targetname)
            logging.info("Creating %s folder" % targetname)
            os.mkdir("data/%s" % targetname)

        with open("data/%s/data.zip" % targetname, "wb+") as tmp:
            tmp.write(zip_data)
        
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
        logging.info("Moving files for analysis")

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
        logging.info("%s is now ready for analysis with %d file(s) and %d system(s)" % (analysisfolder, filecount, computercount))

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

    # Why isn't there any api call for this??
    # Based on live response 'session list'
    def get_session_count(self):
        sessions = self.cb.get_object("/api/v1/cblr/session")

        active = 0
        for item in sessions:
            if item["status"] == "active":
                active += 1

        return active

        #sensor = self.cb.info()
        #print(sensor)

    # Print iterations progress
    # Thanks https://stackoverflow.com/questions/3173320/text-progress-bar-in-the-console :)
    # Off by 1.8% (prolly per item thing)
    def printProgressBar (self, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█'):
        """
            Call in a loop to create terminal progress bar
            @params:
            iteration   - Required  : current iteration (Int)
            total       - Required  : total iterations (Int)
            prefix      - Optional  : prefix string (Str)
            suffix      - Optional  : suffix string (Str)
            decimals    - Optional  : positive number of decimals in percent complete (Int)
            length      - Optional  : character length of bar (Int)
            fill        - Optional  : bar fill character (Str)
        """

        percent = ("{0:." + str(decimals) + "f}").format(100 * (self.finished / float(len(self.curlist))))
        filledLength = int(length * self.finished // len(self.curlist))
        bar = fill * filledLength + '-' * (length - filledLength)

        if filledLength > 0:
            timenow = datetime.now().timestamp()
            elapsed_time = timenow - self.starttime
            time_left = 100 * elapsed_time / filledLength - elapsed_time

            if self.firsttime == 0:
                self.firsttime = time_left
                self.time_left = time_left

            if time_left < self.time_left:
                if time_left >= 0:
                    self.time_left = time_left

            # Not sure why, but 2.2 is close
            #thistime = self.time_left-self.firsttime/2.1
            thistime = self.time_left-self.firsttime/2.1
            if thistime <= 2 or filledLength >= 98:
                suffix = "%s, time left: SOON^tm" % suffix
            else:
                suffix = "%s, time left: %f" % (suffix, thistime)

            print('\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix), end = '\r')
        else:
            suffix = "%s time left: calculating" % (suffix)
            print('\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix), end = '\r')
            
        if self.finished == len(self.curlist): 
            print()

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

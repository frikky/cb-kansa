import cbapi # Used for error handling

class handleAllJobs(object):
    def __init__(self, local_location, remote_location, folderlocation, fullfolderlocation, datafoldername, outputfolder=""):
        self.local_location = local_location # Saves local location for the data
        self.remote_location = remote_location # Saves destination location of data
        self.folderlocation = folderlocation
        self.fullfolderlocation = fullfolderlocation
        self.datafoldername = datafoldername
        self.outputfolder = outputfolder

    # Runs all commands involved within a single session
    def put_local_file(self, session): 
        with open(self.local_location, "rb") as tmp:
            try:
                ret = session.put_file(tmp, self.remote_location)
                return ret
            except cbapi.live_response_api.LiveResponseError as e:
                # FIX - Remove file and reupload, as this most likely means duplication
                # Most likely error: Win32 error code 0x80070003 (ERROR_PATH_NOT_FOUND)
                print("Host %d error: %s" % (session.sensor_id, e))
                return False

        return True 

    # Unzips and removes the zipfile
    def unzip_remote(self, session):
        filepath = "%s%s" % (self.folderlocation, self.local_location)
        new_filename = filepath[:-4]

        command = 'powershell.exe \"Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::ExtractToDirectory(\'%s\', \'%s\'); rm \'%s\'\"' % (filepath, new_filename, filepath)
        ret = session.create_process(command)

        return True

    # Pass arguments for kansa to run like normal
    def run_kansa(self, session):
        foldername = self.outputfolder
        if "/" in self.outputfolder:
            if not self.outputfolder.endswith("/"):
                foldername = self.outputfolder.split("/")[-1]
            else:
                foldername = self.outputfolder.split("/")[-1]

        if "." in foldername: 
            foldername = foldername.split(".")[0]

        self.newfoldername = foldername
            
        # So what is the location I want?
        commands = [
            "powershell.exe -exec bypass -File kansa.ps1 -target $env:COMPUTERNAME -OutputFolder %s -ModulePath ./Modules -Verbose" % foldername
        ]

        powershell_cmd = 'powershell.exe \"%s\"' % ";".join(commands)

        # FIX - Win32 error code 0x8007010B might occur (or others)
        try:
            ret = session.create_process(powershell_cmd, working_directory=self.fullfolderlocation, wait_timeout=300)
        except cbapi.live_response_api.LiveResponseError as e:
            #print("Host %d error: %s" % (session.sensor_id, e))

            return False

        return ret

    # Zips the file to get it back from the remote host
    def zip_remote(self, session):
        command = 'powershell.exe \"Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::CreateFromDirectory(\'%s\\%s\', \'%s\\%s.zip\')\"' % (self.fullfolderlocation, self.outputfolder, self.fullfolderlocation, self.outputfolder)
        ret = session.create_process(command)
        
        return ret

    def get_zip_data(self, session):
        folderlocation = "%s/%s.zip" % (self.fullfolderlocation, self.outputfolder)
        zip_data = session.get_file(folderlocation)
        return zip_data

    # Cleans up the remote hosts files
    def cleanup_target(self, session):
        command = "powershell.exe \"Remove-Item \'%s%s\' -Recurse -Force\"" % (self.folderlocation, self.datafoldername)
        print(command)
        ret = session.create_process(command)
        return ret

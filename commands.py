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
            except cbapi.live_response_api.LiveResponseError:
                return False
                # FIX - Remove file and reupload, as this most likely means duplication
                pass

        return False

    # Unzips and removes the zipfile
    def unzip_remote(self, session):
        "Unzip payload on remote system"
        filepath = "%s%s" % (self.folderlocation, self.local_location)
        new_filename = filepath[:-4]

        command = 'powershell.exe \"Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::ExtractToDirectory(\'%s\', \'%s\'); rm \'%s\'\"' % (filepath, new_filename, filepath)
        ret = session.create_process(command)

        return True

    # Pass arguments for kannsa to run like normal
    def run_kansa(self, session):
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
            ret = session.create_process(powershell_cmd, working_directory=self.fullfolderlocation, wait_timeout=300)
        except cbapi.live_response_api.LiveResponseError:
            return False

        return ret

    # Zips the file to get it back from the remote host
    def zip_remote(self, session):
        command = 'powershell.exe \"Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::CreateFromDirectory(\'%s\\%s\', \'%s\\%s.zip\')\"' % (self.fullfolderlocation, self.outputfolder, self.fullfolderlocation, self.outputfolder)
        ret = session.create_process(command)
        
        return ret

    def get_zip_data(self, session):
        zip_data = session.get_file("%s/%s.zip" % (self.fullfolderlocation, self.outputfolder))
        return zip_data

    # Cleans up the remote hosts files
    def cleanup_target(self, session):
        command = "powershell.exe \"Remove-Item \'C:\\temp\\%s\' -Recurse -Force\"" % self.datafoldername 
        ret = session.create_process(command)
        return ret

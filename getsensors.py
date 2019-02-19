from cbapi.response import *
import time

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

cb = CbResponseAPI()


# Horrible check, should check by hours or something
today= time.strftime("%Y-%m-%d")

# Gets all sensors in a group/host w/e
def getsensors(gid):
    # Groupsensors - pick a number > 0 :)
    # Run  with .first() and print to find all the parameters
    sensor = cb.select(Sensor).where("groupid:%d" % gid)

    # By hostname, can indicate location etc.
    #sensor = cb.select(Sensor).where("hostname:")

    allsensors = []

    # Append to list if checkin was today?
    for item in sensor:
        if not str(item.last_checkin_time).split(" ")[0] == today:
            continue

        allsensors.append(item.computer_name)

    return allsensors

def writetofile(filepath, allsensors):
    with open(filepath, "w+") as tmp:
        tmp.write("\n".join(allsensors))

# Use .first() to get first match
#print sensor
if __name__ == "__main__":
    groupid = 1
    filename = "alltargets.txt"

    allsensors = getsensors(groupid)
    writetofile(filename, allsensors)
    print "Added %d sensors to %s." % (len(allsensors), filename)

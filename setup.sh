#!/bin/bash

echo "Setting up the kansa directory etc."

git clone https://github.com/Davehull/Kansa
mv Kansa/Modules/ Modules/
mv Kansa/Analysis Analysis/

# Setting up for custom modules (mostly modified cus of timeout issues)
modulesfolder="custommodules"
IFS="/"
find $modulesfolder -maxdepth 2 | while read -r dir
do
	if [[ $dir != *ps1 ]]; then
		continue
	fi

	# Split on IFS
	read -ra ADDR <<< $dir
	modulefoldername=${ADDR[1]}
	module=${ADDR[2]}

	cp $dir Modules/$modulefoldername/$module
done


# Running custom kansa.ps1 (localhost / $env:COMPUTERNAME = local, not session), so this is now unncesseary
#mv Kansa/kansa.ps1 kansa.ps1
rm -rf Kansa/

echo "\n[!] Be sure to change Modules/modules.conf as this is a default as per now."

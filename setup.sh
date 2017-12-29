#!/bin/sh

echo "Setting up the kansa directory etc."

git clone https://github.com/Davehull/Kansa
mv Kansa/Modules/ Modules/
mv Kansa/Analysis Analysis/
mv Kansa/kansa.ps1 kansa.ps1
rm -rf Kansa/

echo "\n[!] Be sure to change Modules/modules.conf as this is a default as per now."

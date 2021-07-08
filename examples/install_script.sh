#!/bin/bash
set -euxo pipefail

##This script assumes that wget, tar, make, git and cmake are installed on your system.

BASEDIR=$(pwd)
##superSTR dependency - HTSLIB 1.11
wget https://github.com/samtools/htslib/releases/download/1.11/htslib-1.11.tar.bz2
tar xvjf htslib-1.11.tar.bz2
rm htslib-1.11.tar.bz2 
cd htslib-1.11/
./configure --prefix=$BASEDIR/htslib/
export HTSLIB_ROOT=$BASEDIR/htslib
make
make install
##superSTR
cd $BASEDIR
git clone https://github.com/bahlolab/superSTR
cd superSTR/C/
cmake .
make

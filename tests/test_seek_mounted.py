#!/usr/bin/env python
import os, sys

if not len(sys.argv) == 2:
    print "usage [path]"
    os.exit(1)
D = sys.argv[1]

if not os.path.exists(D):
    print "path needs to be mountpoint"
    os.exit(1)
    
fp = open(os.path.join(D, "writetest"), "w")

fp.write("test" * 1024)
fp.seek(1)
fp.write("blubb" * 10)
fp.seek(2048)
fp.write("end")
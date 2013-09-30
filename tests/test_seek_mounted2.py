#!/usr/bin/env python

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..")))
sys.path.insert(0, os.getcwd())
import threading
import subprocess
import random
import hashlib
import thread, threading
import libdumpfs as dumpfs
import StringIO

def get_hash(fp_in):
    in_hash = hashlib.md5()
    while True:
        data = fp_in.read(4096)
        if not data:
            break
        in_hash.update(data)
    return in_hash

def do_large_write(INFILE, OUTFILE):    
    tf = dumpfs.TransferFile()

    #INFILE = "/tmp/dumpin"
    #OUTFILE = INFILE + ".out.dumpfs"
    
    size = os.path.getsize(INFILE)
    
    ss = size/10
    print ss
    parts = [(ss * i, random.randrange(min(ss*(i+1), size - 10), min(ss*(i+3), size))) for i in xrange(10)]
    parts[-1] = (parts[-1][0], size)
    print parts

    random.shuffle(parts)

        #d = ["a", "b", "c", "d", "e"]
    #f = open(INFILE, "wb")
    #for x in d:
    #    f.write(x * 1024)
    #f.close()
    #parts = [(0, 1300), (600, 2300), (2000, 5*1024)]
    #random.shuffle(parts)

    fp_in = open(INFILE, "rb")
    fp_out = open(OUTFILE, "wb")
    
    #in_hash = get_hash(fp_in)
        
    #print "hash: %s" %in_hash.hexdigest()


    for ra in parts:
        fp_in.seek(ra[0])
        data = ""
        #tr = ra[1] - ra[0]
        print ra[0], " - ", ra[1]
        fp_out.seek(ra[0])
        while True:
            #print tr, len(data), tr - len(data), ra[1]
            #print "tell %s" %fp_in.tell()
            #ndata = fp_in.read(tr - len(data))
            pos = fp_in.tell()
            ndata = fp_in.read(4096)
            #print pos, ndata
            #print len(ndata)
            if len(ndata) == 0:
                if pos >= ra[1]:
                    break
                print "read error"
                return
            #print len(data), pos
            fp_out.write(ndata) #, pos)
            if pos >= ra[1]:
                break
            #if len(ndata) == 0:
            #    print "read error"
            #    return
            data += ndata
            #data = fp_in.read(ra[1])
            #print "W"*10
            
            #print "WE" * 10
    #assert unp.decode_file(OUTFILE)
    #fp_out2 = open(OUTDEC, "r")
    #fp_out2.flush()
    #fp_out2.seek(0)
    #out_hash = hashlib.md5(fp_out2.read())
    #out_hash = get_hash(fp_out2)
    #print "out hash: " + out_hash.hexdigest()
    #assert out_hash.hexdigest() == in_hash.hexdigest()
    print "written"

import optparse
import sys, os


parser = optparse.OptionParser(usage="usage: %prog [options] INFILE OUTFILE")

(options, args) = parser.parse_args()

if len(args) != 2:
    parser.print_usage()
    sys.exit(2)
do_large_write(args[0], args[1])
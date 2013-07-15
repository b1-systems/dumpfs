#from .. import dumpfs
import sys, os
print os.getcwd()
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..")))
sys.path.insert(0, os.getcwd())
print sys.path
import threading
import subprocess
import random
import hashlib
import thread, threading
import libdumpfs as dumpfs
import StringIO

# test header parsing

def test_package():

    buf = StringIO.StringIO()

    test_data = "bla99\x00\xff"
    
    p1 = dumpfs.Package(dumpfs.OP_DATA)
    p1.write(test_data)
    buf.write(str(p1))

    buf.seek(0)

    p2 = dumpfs.Package(dumpfs.OP_UNKNOWN)
    p2.parse(buf)

    assert p2.type_ == p1.type_
    assert p2.seek == p1.seek
    assert p2.data_length() == p1.data_length()
    assert "".join(p2.data) == "".join(p1.data)

    
    # test stream output
    outbuf = StringIO.StringIO()
    buf.seek(0)
    p2 = dumpfs.Package(dumpfs.OP_UNKNOWN)
    p2.parse(buf, outbuf)
    
    assert outbuf.getvalue() == test_data
    
    # large buffer test
    blen = 4*2**16
    test_data2 = "".join([chr(random.randint(0,255)) for x in xrange(blen)])
    p3 = dumpfs.Package(dumpfs.OP_DATA)
        
    p3.write(test_data2[:blen/2])
    p3.write(test_data2[blen/2:])

    buf = StringIO.StringIO()
    
    buf.write(str(p3))
    
    buf.seek(0)
    p3 = dumpfs.Package(dumpfs.OP_UNKNOWN)
    p3.parse(buf)
    
    assert "".join(p3.data) == test_data2
    
    buf = StringIO.StringIO()
    # more seek test
    p4 = dumpfs.Package(dumpfs.OP_DATA, seek=3829760)
    p4.write("abc")
    buf.write(str(p4))
    buf.seek(0)
    p5 = dumpfs.Package(dumpfs.OP_UNKNOWN)
    p5.parse(buf)
    
    assert p4.seek == p5.seek
    assert p5.data[0] == "abc"
    
    
def test_decoder():
    unp = dumpfs.Unpacker()
    
    OUTFILE = "/tmp/dumpfs_testdata.txt.dumpfs"
    PUREFILE = "/tmp/dumpfs_testdata.txt"
    
    fp = open(OUTFILE, "wb+")
    
    p1 = dumpfs.Package(dumpfs.OP_DATA)
    p1.write("blabla")
    fp.write(str(p1))
    
    p1 = dumpfs.Package(dumpfs.OP_DATA, seek=1)
    p1.write("blabla")
    fp.write(str(p1))
    
    p1 = dumpfs.Package(dumpfs.OP_EOF)
    fp.write(str(p1))
    
    fp.close()
    
    assert unp.decode_file(OUTFILE)
    assert open(PUREFILE, "rb").read() == "bblabla"
  
    os.unlink(PUREFILE)
    os.unlink(OUTFILE)
    
    

def test_transfer():
    tf = dumpfs.TransferFile()

    INFILE = "/tmp/dumpin"
    OUTFILE = "/tmp/dumpout.dumpfs"
    OUTDEC = "/tmp/dumpout"

    print "create testdata"

    size = 1024*1024

    ss = size/10
    parts = [(ss * i, random.randrange(min(ss*(i+1), size), min(ss*(i+3), size))) for i in xrange(10)]
    parts[-1] = (parts[-1][0], size)

    random.shuffle(parts)

    print parts
    
    subprocess.check_call(["dd", "if=/dev/urandom", "of=%s" % INFILE, "bs=%s" %size, "count=1"])
    #d = ["a", "b", "c", "d", "e"]
    #f = open(INFILE, "wb")
    #for x in d:
    #    f.write(x * 1024)
    #f.close()
    #parts = [(0, 1300), (600, 2300), (2000, 5*1024)]
    #random.shuffle(parts)

    fp_in = open(INFILE, "rb")
    fp_out = open(OUTFILE, "wb")

    in_hash = hashlib.md5(fp_in.read())
    print "hash: %s" %in_hash.hexdigest()


    class ReadThread(threading.Thread):
        def run(self):
            while True:
                #print "00" * 10
                data = tf.read(1024)
                if not data:
                    break
                fp_out.write(str(data))
            fp_out.flush()
                #print "--" * 10


    def write_thread(in_):
        for ra in parts:
            fp_in.seek(ra[0])
            data = ""
            tr = ra[1] - ra[0]
            while len(data) != tr:
                #print tr, len(data), tr - len(data), ra[1]
                #print "tell %s" %fp_in.tell()
                ndata = fp_in.read(tr - len(data))
                #print len(ndata)
                if len(ndata) == 0:
                    print "read error"
                    return
                data += ndata
            #data = fp_in.read(ra[1])
            #print "W"*10
            tf.write(data, ra[0])
            #print "WE" * 10
        tf.close()

    #rt = thread.start_new_thread(read_thread, (fp_out,))
    rt = ReadThread()
    rt.start()
    write_thread(fp_in)
    print "end of write"
    try:
        rt.join()
        fp_out.flush()
    except KeyboardInterrupt as e:
        print e
        sys.exit(1)
    print "unpack"
    # unpack
    
    unp = dumpfs.Unpacker()
    assert unp.decode_file(OUTFILE)
    fp_out2 = open(OUTDEC, "r")
    fp_out2.flush()
    fp_out2.seek(0)
    out_hash = hashlib.md5(fp_out2.read())
    assert out_hash.hexdigest() == in_hash.hexdigest()
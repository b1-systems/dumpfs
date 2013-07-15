import threading
import struct
import re
import os

MAX_SIZE = 10 * 1024
FAKE_SIZE = (512 * 1024 * 1024) # 2 TB

MAX_BUFFER = 1024 * 1024

MAGIC=(0x23,0xf1,0xd2)
OP_UNKNOWN=0x00
OP_DATA=0x01
OP_COMPRESSION=0x02
OP_EOF=0x10

OPS = {
    OP_UNKNOWN: "UNKNOWN",
    OP_DATA: "OP_DATA",
    OP_COMPRESSION: "OP_COMPRESSION",
    OP_EOF: "OP_EOF",
}


S_HEADER = "<BBBBQ"
S_HEADER_LEN = struct.calcsize(S_HEADER)
S_DATA = "<Q"
S_DATA_LEN = struct.calcsize(S_DATA)
S_DATA_FULL = S_HEADER + "Q"


class Package(object):
    """Represents a OP code in Stream"""
    
    def __init__(self, type_, seek = 0):
        self.type_ = type_
        self.seek = seek
        self.data = []
        self.freeze = False
        self._str = None
        self.length = None

    def buffersize(self):
        rv = 0
        for b in self.data:
            rv += len(b)
        return rv

    def get_length(self):
        if self.length:
            return self.length
        else:
            return self.buffersize()
            
    def _update_cache(self):
        if not self.freeze:
            self._str = self.serialize()
            return
        if not self._str:
            self._str = self.serialize()

    def __str__(self):
        self._update_cache()
        return self._str

    def __len__(self):
        return len(self.header()) + self.data_length()
    
    #def __getslice__(self, i, j):
    #    self._update_cache()
    #    rv = Package(self.type_)
    #    rv.data = [self._str[i:j]]
    #    rv.freeze = self.freeze
    #    rv.seek = self.seek + i
    #    return rv
        

    def write(self, data):
        if self.freeze:
            raise Exception("package frozen")
        self.data.append(data)
        
    def data_length(self):
        rv = 0
        for dat in self.data:
            rv += len(dat)
        return rv
        
    def header(self):
        if self.type_ == OP_EOF:
            rv = struct.pack(S_HEADER, MAGIC[0], MAGIC[1], MAGIC[2], self.type_, 0)
        elif self.type_ == OP_DATA:
            length = self.data_length() + S_DATA_LEN # + seek length
            #print "-"*20
            #print MAGIC[0], MAGIC[1], MAGIC[2], self.type_, (self.seek or 0), length
            #print "-"*20
            rv = struct.pack(S_DATA_FULL, MAGIC[0], MAGIC[1], MAGIC[2], self.type_, length, (self.seek or 0))
        else:
            raise Exception("unknown op type")
        #print "header:"
        #print repr(rv)
        return rv
    
    def parse(self, fpin, fpout=None):
        nd = self.parse_header(fpin)
        if nd:
            self.parse_data(fpin, fpout)
    
    def parse_header(self, fp):
        data = ""
        while len(data) < S_HEADER_LEN:
            #print "read header %s" %len(data)
            #print "pos 0x%x" %fp.tell()
            ndata = fp.read(S_HEADER_LEN - len(data))
            if len(ndata) == 0:
                raise EOFError, "premature eof"
            data += ndata
        header = struct.unpack(S_HEADER, data)
        if header[0:3] != MAGIC:
            raise Exception, "Header error"
        self.type_ = type_ = header[3]
        if not OPS.has_key(self.type_):
            raise Exception, "Can't find op type"
        self.length =  header[4]
        #print "pp %s %s" %(self.type_, self.length)
        if self.type_ == OP_DATA:
            data = fp.read(S_DATA_LEN)
            #print 14*"%"
            #print repr(data)
            #print struct.unpack(S_DATA, data)
            self.seek = struct.unpack(S_DATA, data)[0]
            # data payload
            return True
        return False
    
    def parse_data(self, fp, fpout=None):
        cpos = S_DATA_LEN # extra header removed
        #print "pd %s" %self.seek
        if fpout:
            fpout.seek(self.seek)
        while cpos < self.length:
            data = fp.read(min(self.length - cpos, 2**16))
            if not len(data):
                return
            cpos += len(data)
            if fpout:
                fpout.write(data)
            else:
                self.write(data)
    
        
    def serialize(self):
        h = self.header()
        if self.type_ == OP_DATA:
            h += ''.join(self.data)
        return h
    def __repr__(self):
        return "<Package %s offset:%s len:%s>" % (OPS[self.type_], self.seek, self.get_length())
    

class Unpacker(object):
    """
    Unpacks a stream of packages
    """
    def __init__(self):
        pass
    
    def decode_file(self, input_file):
        fp_in = open(input_file, "rb")
        output_file = re.sub("\.dumpfs$", "", input_file)
        fp_out = open(output_file, "wb")
        return self.decode_stream(fp_in, fp_out)
    
    def decode_stream(self, fp_in, fp_out):
        if fp_in.name:
            size = os.path.getsize(fp_in.name)
        eof = False
        i = 0
        while True:
            #print i, fp_in.tell(), fp_out.tell()
            i += 1
            pack = Package(OP_UNKNOWN)
            try:
                has_data = pack.parse_header(fp_in)
                #print repr(pack)
                if has_data:
                    pack.parse_data(fp_in, fp_out)                    
                eof = (pack.type_ == OP_EOF)
            except EOFError as e:
                if eof:
                    return True
                print e
                print "error decoding stream. Not received proper end of stream"
                return False
        

class TransferFile(object):
    """
    To transfer the content of between the two threads without having a local
    file, this TransferFile is used. It contains a list of buffers that will
    be spilled out by read. Read is blocking until another thread puts in more
    Data or closes the file.
    """
    def __init__(self):
        self.buffers = [] #MAGIC]
        self.current_buffer = ""
        self.eof = False
        self.sem = threading.Semaphore(0)
        self.overflow = threading.Semaphore(MAX_SIZE)
        self.lastpos = 0
        self.buffers_lock = threading.Lock()
    
    def buffersize(self):
        rv = 0
        for b in self.buffers:
            rv += len(b)
        return rv
    
    def read(self, length):
        # pop n bytes
        
        if self.eof and len(self.buffers) == 0:
            return

        rv = None
        #while True:
        while True:
            self.sem.acquire()
        
            if not len(self.buffers) and not len(self.current_buffer) and self.eof: # EOF
                rv = None
                break

            if not self.current_buffer:
                self.buffers_lock.acquire()
                
                b = self.buffers.pop(0)
                b.freeze = True
                self.current_buffer = str(b)
                
                self.buffers_lock.release()
                self.overflow.release()
            else:
                self.sem.release() # we didn't pop the buffer, so we have to increase the semaphore again

            if len(self.current_buffer) <= length:
                rv = self.current_buffer
                self.current_buffer = ""
            else:
                rv, self.current_buffer = self.current_buffer[:length], self.current_buffer[length:]

            #self.buffers_lock.release()
            
            #bl = min(length, len(b))
            #if bl == len(b): # we can use the complete buffer element
                #rv = b
                
                #break
            #else: # we can only use a slice
                #rv = b[:bl]
                #self.buffers[0] = b[bl:] # put the rest into the buffer list
                
                #break
            #if len(self.buffers) == 0 and len(rv) > 0:
                #break
            break
        return rv
        
    def write(self, buf, pos=None):
        # skip while in 
        if self.eof:
            return

        self.buffers_lock.acquire()
        if pos is None:
            pos = self.lastpos
        
        lbuf = None
        if len(self.buffers):
            lbuf = self.buffers[-1]
        
        if lbuf and not lbuf.freeze and pos == (lbuf.seek + lbuf.buffersize() + 1) \
            and lbuf.buffersize() < MAX_BUFFER:
            # we can append to old buffer
            lbuf.data.append(buf)
        else:
            lbuf = Package(OP_DATA, seek = pos)
            lbuf.data.append(buf)
            #print "nb" + repr(lbuf)
            self.buffers.append(lbuf)

        self.lastpos += len(buf)

        self.buffers_lock.release()
        self.sem.release()
        self.overflow.acquire()
        
    def clear(self):
        while len(self.buffers):
            self.read(409600)
    
    def close(self):
        self.buffers_lock.acquire()
        self.buffers.append(Package(OP_EOF))
        self.eof = True
        self.buffers_lock.release()
        self.sem.release()
        

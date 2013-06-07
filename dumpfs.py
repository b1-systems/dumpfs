#!/usr/bin/python

FTP_USER="test"
FTP_PASS="test"
FTP_HOST="localhost"
FTP_DATEFORMAT=r"%Y-%m-%d_%H:%M"
FTP_PATH="{hostname}/{date}"
TIMEOUT=30


import fuse
from fuse import Fuse

import time

import traceback
import threading
import thread

import sys
import stat    # for file properties
import os      # for filesystem modes (O_RDONLY, etc)
import errno   # for error number codes (ENOENT, etc)
               # - note: these must be returned as negatives
import ftplib
import socket
import ConfigParser

import syslog

syslog.openlog("dumpfs", syslog.LOG_PID, syslog.LOG_DAEMON)


def dirFromList(list):
    """
    Return a properly formatted list of items suitable to a directory listing.
    [['a', 'b', 'c']] => [[('a', 0), ('b', 0), ('c', 0)]]
    """
    return [[(x, 0) for x in list]]

def getDepth(path):
    """
    Return the depth of a given path, zero-based from root ('/')
    """
    if path == '/':
        return 0
    else:
        return path.count('/')

def getParts(path):
    """
    Return the slash-separated parts of a given path as a list
    """
    if path == '/':
        return [['/']]
    else:
        return path.split('/')

def format_path():
    d = {
      "hostname": socket.gethostname(),
      "date": time.strftime(FTP_DATEFORMAT)
    }
    return FTP_PATH.format(**d)
    
print format_path()
      


current_files = {}
current_path = None
current_open_counter = 0
subdirectories = ["/"]


MAX_SIZE = 10 * 1024
FAKE_SIZE = (512 * 1024 * 1024) # 2 TB


class TransferFile(object):
    """
    To transfer the content of between the two threads without having a local
    file, this TransferFile is used. It contains a list of buffers that will
    be spilled out by read. Read is blocking until another thread puts in more
    Data or closes the file.
    """
    def __init__(self):
        self.buffers = []
        self.eof = False
        self.sem = threading.Semaphore(0)
        self.overflow = threading.Semaphore(MAX_SIZE)
    
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
        while True:
            self.sem.acquire()
        
            if not len(self.buffers): # EOF
                break

            b = self.buffers[0]
            bl = min(length, len(b))
            if bl == len(b): # we can use the complete buffer element
                rv = b
                self.buffers.pop(0)
                self.overflow.release()
                break
            else: # we can only use a slice
                rv = b[:bl]
                self.buffers[0] = b[bl:] # put the rest into the buffer list
                self.sem.release() # we didn't pop the buffer, so we have to increase the semaphore again
                break
            
            if len(self.buffers) == 0 and len(rv) > 0:
                break
        return rv
        
    def write(self, buf):
        # skip while in 
        if self.eof:
            return

        self.buffers.append(buf)
        self.sem.release()
        self.overflow.acquire()
        
    
    
    def close(self):
        self.eof = True
        self.sem.release()
        


class DumpFileClass(object):
    keep      = False
    direct_io = False
    keep_cache = False
    length = 0
    _init = False


    # causes bad behaviour
    #def __new__(cls, path, *args, **kw):
        #print "__NEW__", cls, path, args, kw
        #if False and current_files.has_key(path):
            #return current_files[path]
        #else:
            #rv = object.__new__(cls, path, *args, **kw)
            ## init

            #return rv
    
    
    def __init__(self, path, *args, **kw):
        global current_open_counter
        if self._init:
            print "SKIP INIT"
            return
        self._init = True
        self.path = path
        self.buffer = TransferFile()
        self.exception = False  # indicate strange errors, do noop then
        self.writethread = None
        self.ftp = ft = ftplib.FTP(timeout=TIMEOUT)
        ft.set_debuglevel(1)
        current_open_counter += 1
        self.update_path()
        
        current_files[path] = self
        print "NEW FILE class created", path, args, kw
        syslog.syslog(syslog.LOG_INFO, "start dumping file: " + str(path))

    def update_path(self):
        global current_open_counter, current_path
        if current_open_counter < 2 or current_path is None:
            current_path = format_path()
          
    def _start_writethread(self):
        print "WRITE THREAD SPAWNED"
        try:
            self.ftp.connect(FTP_HOST, timeout=TIMEOUT)
            self.ftp.login(FTP_USER, FTP_PASS)
        except Exception, e:
            print "Error logging into FTP"
            syslog.syslog(syslog.LOG_ERR, "error logging into ftp: " + str(e))
            self.exception = True
            return
        self.create_directory()
        try:
            self.ftp.storbinary("STOR %s" %self.path.split("/")[-1], self.buffer, blocksize=409600)
            self.ftp.close()
        except Exception, e:
            print "Exception in FTP Transfer" + str(e)
            syslog.syslog(syslog.LOG_ERR, "error dumping file: " + str(e))
            self.exception = True
            
        print "TRANSFER FINISHED"

    def create_directory(self):
        targets = current_path.split("/") + self.path.split("/")[:-1]
        for c in targets:
            try:
                self.ftp.mkd(c)
            except ftplib.error_perm, e:
                print e
            self.ftp.cwd(c)
      
        
    def write(self, buf, *args, **kw):
        if self.exception:
            return 0
        
        self.length += len(buf)
        self.buffer.write(buf)
        
        if not self.writethread:
            print "STARTTHREAD"
            self.writethread = thread.start_new_thread(self._start_writethread, ())
            # we have to sleep shortly here, to get the new thread kicked ...
            time.sleep(0.5)
            print "ENDSTARTTHREAD"
        
        return len(buf)

    def close(self):
        print "close file"
        
    def release(self, *args, **kw):
        global current_open_counter
        print "release", args, kw
        self.buffer.close()
        current_open_counter -= 1
        del current_files[self.path]

    def ftruncate(self, *args, **kw):
        print "ftruncate", args, kw
        self.length = 0
        # FIXME: what to do on truncate ?

    def truncate(self, *args, **kw):
        print "truncate", args, kw
        self.length = 0
        # FIXME: what to do on truncate ?

        
        
class DumpFS(Fuse):
    """
    """

    def __init__(self, *args, **kw):
        Fuse.__init__(self, *args, **kw)
        self.file_class = DumpFileClass
        
        print 'Init complete.'
        
    def getattr(self, path):
        """
        - st_mode (protection bits)
        - st_ino (inode number)
        - st_dev (device)
        - st_nlink (number of hard links)
        - st_uid (user ID of owner)
        - st_gid (group ID of owner)
        - st_size (size of file, in bytes)
        - st_atime (time of most recent access)
        - st_mtime (time of most recent content modification)
        - st_ctime (platform dependent; time of most recent metadata change on Unix,
                    or the time of creation on Windows).
        """

        print '*** getattr', path


        print current_files
        
        if not path in subdirectories and not current_files.has_key(path):
            print "NOEXISTS"
            return -errno.ENOENT
      
        
        st = fuse.Stat()
        if path in subdirectories:
            st.st_mode = stat.S_IFDIR | 0777
        else:
            file_ = current_files[path]
            st.st_mode = stat.S_IFREG | 0755
            st.st_size = file_.length

        st.st_nlink = 1
        st.st_atime = int(time.time())
        st.st_mtime = st.st_atime
        st.st_ctime = st.st_atime

        return st
        
        depth = getDepth(path) # depth of path, zero-based from root
        pathparts = getParts(path) # the actual parts of the path

        print "rv", [16877, 0, 0, 1, 0, 0, 0, 0, 0, 0]
        return (16877, 0, 0, 1, 0, 0, 0, 0, 0, 0)
        
        return -errno.ENOSYS

    def getxattr(self, *args, **kwargs):
        #print "getxattr", args, kwargs
        return -errno.ENOSYS
        

    def getdir(self, path):
        """
        return: [[('file1', 0), ('file2', 0), ... ]]
        """

        print '*** getdir', path
        if path not in subdirectories:
            return -errno.ENOSYS
        # always return an empty diretory
        rv = [('.', 0), ('..', 0)]
        # push all current open files onto the list
        print current_files
        for cpath,cfile in current_files.iteritems():
            if cpath[:len(path)] == path:
                rv.append([cpath[len(path):], 0])
        
        return [rv]
        #return -errno.ENOSYS

    def readdir(self, path, offset):
        if path not in subdirectories:
            yield -errno.ENOSYS
            return
        for e in '.', '..':
            yield fuse.Direntry(e)
        done = []
        for d in subdirectories:
            print d
            if d[:len(path)] == path:
                nd = d[len(path):].split("/")[0]
                if nd and not nd in done:
                    yield fuse.Direntry(nd)
                    done.append(nd)
        for cpath,cfile in current_files.iteritems():
            if cpath[:len(path)] == path:
                yield fuse.Direntry(cpath[1:]) 
        
        
    def mythread ( self ):
        print '*** mythread'
        return -errno.ENOSYS

    def chmod ( self, path, mode ):
        print '*** chmod', path, oct(mode)
        return -errno.ENOSYS

    def chown ( self, path, uid, gid ):
        print '*** chown', path, uid, gid
        return -errno.ENOSYS

    def fsync ( self, path, isFsyncFile, whatever ):
        print '*** fsync', path, isFsyncFile, whatever
        return -errno.ENOSYS

    def link ( self, targetPath, linkPath ):
        print '*** link', targetPath, linkPath
        return -errno.ENOSYS

    def mkdir ( self, path, mode ):
        print '*** mkdir', path, oct(mode)
        return -errno.ENOSYS

    def mknod ( self, path, mode, dev ):
        print '*** mknod', path, oct(mode), dev
        return -errno.ENOSYS

    #def open ( self, path, flags ):
    #    print '*** open', path, flags
    #    return -errno.ENOSYS

    def read ( self, path, length, offset ):
        print '*** read', path, length, offset
        return -errno.ENOSYS

    def readlink ( self, path ):
        print '*** readlink', path
        return -errno.ENOSYS

    #def release ( self, path, flags, file_ ):
    #    print '*** release', path, flags, file_
        
        #if file_ and file_.path in current_files:
            #print "current file cleared"
            #del current_files[file_.path]

        #return -errno.ENOSYS

    def rename ( self, oldPath, newPath ):
        print '*** rename', oldPath, newPath
        return -errno.ENOSYS

    def rmdir ( self, path ):
        print '*** rmdir', path
        return -errno.ENOSYS

    def statfs ( self ):
        print '*** statfs'
        return fuse.StatVfs( #f_bsize=4096, f_blocks=FAKE_SIZE, f_bavail=FAKE_SIZE)
                            f_bsize=4096, f_frsize=4096, f_blocks=FAKE_SIZE, f_bfree=FAKE_SIZE, f_bavail=FAKE_SIZE, f_files=100000, f_ffree=99000, f_favail=99000, f_flag=4096, f_namemax=255)
        #return dict(f_bsize=512, f_blocks=4096, f_bavail=2048)
        return -errno.ENOSYS

    def symlink ( self, targetPath, linkPath ):
        print '*** symlink', targetPath, linkPath
        return -errno.ENOSYS

    def unlink ( self, path ):
        print '*** unlink', path
        return -errno.ENOSYS

    def utime ( self, path, times ):
        print '*** utime', path, times
        return -errno.ENOSYS

    #def write ( self, path, buf, offset ):
    #    print '*** write', path, buf, offset
    #return -errno.ENOSYS

def parse_config():
    global FTP_HOST, FTP_USER, FTP_PASS, FTP_DATEFORMAT, FTP_PATH, TIMEOUT
    cp = ConfigParser.ConfigParser()
    files = ["/etc/dumpfs.conf", "dumpfs.conf"]
    if "DUMPFS_CONFIG" in os.environ:
        files.append(os.environ["DUMPFS_CONFIG"])
    loaded = cp.read(files)
    if not loaded:
        print "Could not load any config file of %s" %files
        print "Please check permissions"
        sys.exit(1)
    print "Loaded config files %s" %loaded
    
    FTP_HOST = cp.get("ftp", "server")
    FTP_USER = cp.get("ftp", "login")
    FTP_PASS = cp.get("ftp", "password")
    FTP_DATEFORMAT = cp.get("ftp", "dateformat")
    FTP_PATH = cp.get("ftp", "path")
    try:
        TIMEOUT = cp.get("ftp", "timeout")
    except (KeyError, ConfigParser.NoOptionError), e:
        pass
    
    for i,d in cp.items("directories"):
        subdirectories.append("/%s" %d)
    
    syslog.syslog(syslog.LOG_NOTICE, "dumpfs started with target: %s@%s" %(FTP_USER, FTP_HOST))

if __name__ == "__main__":
    fuse.fuse_python_api = (0, 2)
    parse_config()
    #fuse.feature_needs("has_ftruncate")
    fs = DumpFS()
    fs.flags = 0
    nargs = sys.argv[:]
    print "ARGS", nargs
    # we extend the parsed args to make mounting parameters simpler
    nopts = ["max_write=%s" %(10*1024*1024),
             "kernel_cache",
             "default_permissions"]
    if fuse.APIVersion() >= 28:
        nopts.append("big_writes")
    if os.getuid() == 0:
        nopts.append("allow_other")
    else:
        if " ".join(sys.argv).find("allow_other") == -1:
            print "mounting as root is suggested or pass \"-o allow_other\" as option"
    
    nargs.append("-o")
    nargs.append(",".join(nopts))
    
    print nargs
    fs.parse(nargs, errex=1)
    fs.multithreaded = 1
    try:
        fs.main()
    except Exception, e:
        print "error initializing fuse: %s" %e
        syslog.syslog(syslog.LOG_ERR, "error initializing fuse: %s" %e)


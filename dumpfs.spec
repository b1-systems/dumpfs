# Copyright (c) 2011 B1 Systems GmbH, Nuernberg, Germany.
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself (unless the
# license for the pristine package is not an Open Source License, in which
# case the license is the MIT License). An "Open Source License" is a
# license that conforms to the Open Source Definition (Version 1.9)
# published by the Open Source Initiative.
 
# norootforbuild
 
Name:       dumpfs
Version:    0.3.1
Release:    0
License:    GPLv2
Summary:    Write Only Filesystem for dumps on FTP servers
Group:      System
Source:     dumpfs.py
Source1:    dumpfs.conf
Source2:    dumpfs.init
BuildRoot:  %{_tmppath}/%{name}-%{version}-build
PreReq:     %insserv_prereq
Requires:   python >= 2.6, python-fuse
#BuildRequires: cmake, gcc
BuildArch:  noarch
 
%description
dumpfs is a write only filesystem designed for generating large crash dumps
on a remote ftp.
 
%prep
#%setup -q

%build
#cmake -DCMAKE_SKIP_RPATH=ON \
#      -DCMAKE_INSTALL_PREFIX=%{_prefix}
#%{__make} %{?jobs:-j%jobs}

%install
mkdir -p $RPM_BUILD_ROOT/usr/bin
mkdir -p $RPM_BUILD_ROOT/etc/init.d
install -m 0755 %{SOURCE0} $RPM_BUILD_ROOT/usr/bin/dumpfs
install -m 0600 %{SOURCE1} $RPM_BUILD_ROOT/etc/dumpfs.conf
install -m 0755 %{SOURCE2} $RPM_BUILD_ROOT/etc/init.d/byd-dumpfs
#install -m 0755 $RPM_SOURCE_DIR/src/dumpfilter.init $RPM_BUILD_ROOT/etc/init.d/dumpfilter
#install -m 0755 $RPM_ROOT_DIR/src/dumpfilter.py $RPM_BUILD_ROOT/usr/sbin/dumpfilter
#install $RPM_ROOT_DIR/src/dumpfilter.ini $RPM_BUILD_ROOT/etc/dumpfilter/dumpfilter.ini
#install $RPM_ROOT_DIR/src/dumpfilter.gdb $RPM_BUILD_ROOT/etc/dumpfilter/dumpfilter.gdb
#%{__make} DESTDIR=%{buildroot} install
 
%clean
%{?buildroot:%__rm -rf "%{buildroot}"}
 
%files
%defattr(-,root,root)
%config /etc/dumpfs.conf
/etc/init.d/byd-dumpfs
/usr/bin/dumpfs
 
%changelog

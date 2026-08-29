# See https://docs.fedoraproject.org/en-US/packaging-guidelines/Python/#_example_spec_file

%define debug_package %{nil}

%define _name changenotifier

%define mybuildnumber %{?build_number}%{?!build_number:1}

Name:           %{_name}
Version:        0.1.1
Release:        %{mybuildnumber}%{?dist}
Summary:        Get HTTP notifications or run commands when files are changed

License:        GPLv3+
URL:            https://github.com/Rudd-O/%{_name}
Source:         %{_name}-%{version}.tar.gz

BuildArch:        noarch
BuildRequires:    python3-devel python3-setuptools make systemd-rpm-macros
Requires:         inotify-tools
Requires(post):   gawk grep
Requires(preun):  gawk grep
Requires(postun): gawk grep

%global _description %{expand:
This program allows you to get notifications via HTTP REST calls, or run
arbitrary programs, when files in the folders it monitors appear, are deleted
or are done being written to.}

%description %_description

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires -t


%build
%pyproject_wheel


%install
%pyproject_install

%pyproject_save_files %{_name}

make install DESTDIR=$RPM_BUILD_ROOT UNITDIR=%{_unitdir} USERUNITDIR=%{_userunitdir}



%check
%{!?disable_tests:%{tox}}%{?disable_tests:true}


%post
active=$(%{_bindir}/systemctl list-units --type=service --state=running --no-legend | awk ' { print $1 } ' | grep ^${name}@)
for unit in $active ; do
%systemd_post "$unit"
done
%systemd_user_post %{name}.service

%preun
active=$(%{_bindir}/systemctl list-units --type=service --state=running --no-legend | awk ' { print $1 } ' | grep ^%{name}@)
for unit in $active ; do
%systemd_preun "$unit"
done
%systemd_user_preun %{name}.service

%postun
active=$(%{_bindir}/systemctl list-units --type=service --state=running --no-legend | awk ' { print $1 } ' | grep ^%{name}@)
for unit in $active ; do
%systemd_postun_with_restart "$unit"
done
%systemd_user_postun_with_restart %{name}.service


%files -f %{pyproject_files}
%{_bindir}/%{name}
%attr(0644, root, root) %{_unitdir}/%{name}@.service
%attr(0644, root, root) %{_userunitdir}/%{name}.service

%doc README.md docs/*.md


%changelog
* Fri Aug 28 2026 Manuel Amador <rudd-o@rudd-o.com> 0.0.1
- First RPM packaging release

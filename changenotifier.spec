# See https://docs.fedoraproject.org/en-US/packaging-guidelines/Python/#_example_spec_file

%define debug_package %{nil}

%define _name changenotifier

%define mybuildnumber %{?build_number}%{?!build_number:1}

Name:           %{_name}
Version:        0.1.0
Release:        %{mybuildnumber}%{?dist}
Summary:        Get HTTP notifications or run commands when files are changed

License:        GPLv3+
URL:            https://github.com/Rudd-O/%{_name}
Source:         %{_name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel python3-setuptools make systemd-rpm-macros
Requires:       inotify-tools

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
%tox


%post
%systemd_post %{name}.service

%preun
%systemd_preun %{name}.service

%postun
%systemd_postun_with_restart %{name}.service
%systemd_user_postun_with_restart %{name}.service

%files -f %{pyproject_files}
%{_bindir}/%{name}
%attr(0644, root, root) %{_unitdir}/%{name}@.service
%attr(0644, root, root) %{_userunitdir}/%{name}.service

%doc README.md docs/*.md


%changelog
* Fri Aug 28 2026 Manuel Amador <rudd-o@rudd-o.com> 0.0.1
- First RPM packaging release

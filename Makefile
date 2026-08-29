VERSION := $(shell grep ^Version: *spec | sed 's/Version: *//')
SOURCE := dist/changenotifier-$(VERSION).tar.gz
SRPM := dist/$(shell rpmspec -q --qf "%{name}-%{version}-%{release}.src.rpm\n" *.spec)
RPM := dist/$(shell rpmspec -q --qf "noarch/%{name}-%{version}-%{release}.noarch.rpm\n" *.spec)
SYSCONFDIR := /etc
UNITDIR := $(SYSCONFDIR)/systemd/system
USERUNITDIR := $(SYSCONFDIR)/systemd/user
ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

.PHONY: qa tox clean dist ruff deps-fedora install srpm rpm rpm-notests

clean:
	rm -rf .tox *.egg-info dist .mypy_cache .ruff_cache

# Requires RPM python3-tox-current-env installed.
# Also requires mypy, tox, ruff, pytest.
tox:
	tox --current-env

$(SOURCE): src/changenotifier/*.py MANIFEST.in pyproject.toml tox.ini mypy.ini Makefile README.md docs/* docs/* *.spec systemd/*/*.service
	python3 -m build

dist: $(SOURCE)

$(SRPM): $(SOURCE)
	rpmbuild --define '%_sourcedir dist' --define '%_srcrpmdir dist' -bs *spec

srpm: $(SRPM)

$(RPM): $(SRPM)
	rpmbuild --define '%_rpmdir dist' --rebuild $(SRPM)

rpm: $(RPM)

rpm-notests: $(SRPM)
	rpmbuild --define '%disable_tests true' --define '%_rpmdir dist' --rebuild $(SRPM)

qa: tox

ruff:
	ruff check --select I --select C src/changenotifier/ --fix

install: systemd/*/*.service
	cd $(ROOT_DIR) && install -D -m 0644 systemd/system/*.service -t $(DESTDIR)$(UNITDIR)/
	cd $(ROOT_DIR) && install -D -m 0644 systemd/user/*.service -t $(DESTDIR)$(USERUNITDIR)/
	echo Now please systemctl --system daemon-reload >&2

deps-fedora:
	dnf install -yq --setopt=install_weak_deps=False python3-requests python3-types-requests python3-pyxdg rpm-build ruff python3-mypy systemd-rpm-macros python-rpm-macros pyproject-rpm-macros python3-tox-current-env python3-build python3-setuptools python3-pytest python3-ruff python3-devel python3-pip

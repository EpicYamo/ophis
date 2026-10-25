PYTHON ?= python3
export PYTHONPATH := src

.PHONY: help test run tray preview cli udev install uninstall clean

help:
	@echo "make test     - run the unit tests (no hardware needed)"
	@echo "make run      - start the GUI against the real device"
	@echo "make tray     - start in the background with a tray icon"
	@echo "make preview  - start the GUI with a fake device"
	@echo "make cli      - print device information"
	@echo "make udev     - install the udev rule (sudo)"
	@echo "make install  - add the commands and a desktop entry (~/.local)"
	@echo "make uninstall- remove them again"
	@echo "make clean    - remove cached bytecode"

test:
	$(PYTHON) -m unittest discover -s tests -v

run:
	$(PYTHON) -m ophis.gui.app

tray:
	$(PYTHON) -m ophis.tray

preview:
	$(PYTHON) -m ophis.gui.app --preview

cli:
	$(PYTHON) -m ophis.cli info

udev:
	sudo cp data/99-razer-hidraw.rules /etc/udev/rules.d/
	sudo udevadm control --reload-rules
	sudo udevadm trigger

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf build dist *.egg-info

PREFIX ?= $(HOME)/.local
BINDIR := $(PREFIX)/bin
APPDIR := $(PREFIX)/share/applications
ICONDIR := $(PREFIX)/share/icons/hicolor/scalable/apps
SRCDIR := $(CURDIR)/src

install:
	@mkdir -p $(BINDIR) $(APPDIR) $(ICONDIR)
	@printf '#!/bin/sh\nexec /usr/bin/env PYTHONPATH=$(SRCDIR) $(PYTHON) -m ophis.cli "$$@"\n' > $(BINDIR)/ophis
	@printf '#!/bin/sh\nexec /usr/bin/env PYTHONPATH=$(SRCDIR) $(PYTHON) -m ophis.gui.app --tray --show "$$@"\n' > $(BINDIR)/ophis-gui
	@printf '#!/bin/sh\nexec /usr/bin/env PYTHONPATH=$(SRCDIR) $(PYTHON) -m ophis.tray "$$@"\n' > $(BINDIR)/ophis-tray
	@chmod +x $(BINDIR)/ophis $(BINDIR)/ophis-gui $(BINDIR)/ophis-tray
	@cp data/io.github.epicyamo.Ophis.svg $(ICONDIR)/
	@printf '[Desktop Entry]\nType=Application\nName=Ophis\nComment=Razer Blade control center\nExec=$(BINDIR)/ophis-gui\nIcon=io.github.epicyamo.Ophis\nTerminal=false\nCategories=System;Settings;HardwareSettings;\nStartupWMClass=io.github.epicyamo.Ophis\n' > $(APPDIR)/io.github.epicyamo.Ophis.desktop
	@command -v update-desktop-database >/dev/null && update-desktop-database $(APPDIR) || true
	@command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -f -t $(PREFIX)/share/icons/hicolor || true
	@echo "installed: ophis, ophis-gui, ophis-tray and the desktop entry"
	@echo "files live under $(PREFIX); remove them with: make uninstall"

uninstall:
	@rm -f $(BINDIR)/ophis $(BINDIR)/ophis-gui $(BINDIR)/ophis-tray
	@rm -f $(APPDIR)/io.github.epicyamo.Ophis.desktop
	@rm -f $(ICONDIR)/io.github.epicyamo.Ophis.svg
	@command -v update-desktop-database >/dev/null && update-desktop-database $(APPDIR) || true
	@echo "removed the ophis commands and the desktop entry"

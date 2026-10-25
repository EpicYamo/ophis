PYTHON ?= python3

.PHONY: help test run tray preview cli udev install uninstall deb clean windows

help:
	@echo "Shared:"
	@echo "  make test      - run the unit tests (no hardware needed)"
	@echo "  make clean     - remove cached bytecode and build output"
	@echo ""
	@echo "Linux (delegated to linux/Makefile):"
	@echo "  make run       - start the GTK GUI against the real device"
	@echo "  make tray      - start in the background with a tray icon"
	@echo "  make preview   - start the GUI with a fake device"
	@echo "  make cli       - print device information"
	@echo "  make udev      - install the udev rule (sudo)"
	@echo "  make deb       - build dist/ophis_<version>_all.deb"
	@echo "  make install   - add the commands and a desktop entry (~/.local)"
	@echo "  make uninstall - remove them again"
	@echo ""
	@echo "Windows:"
	@echo "  powershell -ExecutionPolicy Bypass -File windows/build.ps1"

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

run tray preview cli udev install uninstall deb:
	$(MAKE) -C linux PYTHON=$(PYTHON) $@

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf build dist *.egg-info

windows:
	@echo "Windows packaging runs on Windows:"
	@echo "  powershell -ExecutionPolicy Bypass -File windows/build.ps1"

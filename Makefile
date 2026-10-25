PYTHON ?= python3
export PYTHONPATH := src

.PHONY: help test run tray preview cli udev clean

help:
	@echo "make test     - run the unit tests (no hardware needed)"
	@echo "make run      - start the GUI against the real device"
	@echo "make tray     - start in the background with a tray icon"
	@echo "make preview  - start the GUI with a fake device"
	@echo "make cli      - print device information"
	@echo "make udev     - install the udev rule (sudo)"
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

import sys

if "--restore" in sys.argv[1:]:
    # Headless: re-send the saved profile (no GTK needed). Run by the udev-triggered user service.
    from .restore import main
else:
    from .app import main

sys.exit(main())

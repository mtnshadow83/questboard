# Pingle

Ping notification system for Questboard. **In development.**

Watches the `/pings` board for ticket activity (created, status change, closed) and fires Win95-styled desktop popup notifications via PyQt5.

## Usage

```
pythonw pingle.py          # run daemon (background)
python pingle.py --once    # fire pending notifications and exit
```

## Pinger (dev tool)

```
pythonw pinger.pyw         # desktop button that fires test notifications
```

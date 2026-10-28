"""authwatch: security alerts from the auth log and the host's sockets.

Detects SSH logins, sudo use, bursts of failed logins and new listening
ports, and posts each one to Alertmanager. It only detects: nothing here
changes a firewall, SSH setting or account.
"""

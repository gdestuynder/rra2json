Get oauth2 credentials
======================

See http://gspread.readthedocs.org/en/latest/oauth2.html for a guided version of this.

As your user, login to https://console.developers.google.com/project/ and create a new project.
Go to "API&Auth/APIs".
Give that project API rights for the Drive API.
Go to "API&Auth/Credentials".
Click "Create client ID" as "Service ID".
You'll get a JSON key back (JWT), that's your credentials.


.. note::

	Make sure you authorize your Service email to all the spreadsheets you'll want to have access to! By default it
has no accesses.

See https://gist.github.com/gdestuynder/31b8cc3316292d14253f for format

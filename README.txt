Introduction
============

This package defines a browser view ``@@poimail`` that reads an email
from the request and creates an issue for that or adds a response to
an issue.  It is a bridge between smtp2zope_ and `Products.Poi`_.

.. _smtp2zope: http://pypi.python.org/pypi/smtp2zope
.. _`Products.Poi`: http://pypi.python.org/pypi/Products.Poi


Compatibility
-------------

This has been tested with Plone 3.3.5 and Products.Poi 1.2.11.  Should
work fine with Plone 4.x and Poi 2.x as well.


Usage
-----

A standard setup would look like this:

- You have a Plone Site at http://example.org/.

- This Plone Site has ``Products.Poi`` and ``poi.receivemail`` in its
  eggs.

- The site has a Poi tracker at http://example.org/tracker.

- You have installed ``smtp2zope`` on the same machine (possibly in
  the same buildout, but a virtualenv is fine too) and its script is
  available at ``/path/to/smtp2zope``.

- You have a mail server on this machine that has an alias like this::

    helpdesk@example.org "|/path/to/smtp2zope http://example.org/tracker/@@poimail"

  or this::

    helpdesk@example.org "|/path/to/smtp2zope http://admin:secret@example.org/tracker/@@poimail 1000000"

- Now when someone sends an email to helpdesk@example.org a new issue
  is created in the tracker.  When the subject of the email matches an
  existing issue, it is added as response to that issue.

- When a user is found in the Plone Site that matches the sender
  address, we pretend to be that user when creating the issue or
  response.  Otherwise, the Creator is anonymous or is the user that
  is identified through basic authentication in the url that is passed
  as argument to ``smtp2zope``.

import logging
from email.Errors import HeaderParseError
from email import message_from_string
try:
    from email import utils as email_utils
    email_utils  # pyflakes
except ImportError:
    # BBB Python 2.4
    from email import Utils as email_utils
from email import Header

from zope.event import notify
from AccessControl import Unauthorized
from AccessControl.SecurityManagement import getSecurityManager
from AccessControl.SecurityManagement import setSecurityManager
from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.User import UnrestrictedUser
from OFS.Image import File
from Products.Archetypes.event import ObjectInitializedEvent
from Products.CMFCore.utils import getToolByName
from Products.Five import BrowserView
from Products.CMFPlone.utils import _createObjectByType
from Products.Poi.adapters import IResponseContainer
from Products.Poi.adapters import Response

from poi.receivemail.config import LISTEN_ADDRESSES
from poi.receivemail.config import FAKE_MANAGER
from poi.receivemail.config import ADVANCED_SUBJECT_MATCH

logger = logging.getLogger('poimail')


def cleanup_search_string(s):
    # Taken from livesearch_reply.py
    bad_chars = ["(", ")"]
    for char in bad_chars:
        s = s.replace(char, '"%s"' % char)
    for char in '?-+*':
        s = s.replace(char, ' ')
    return s


class Receiver(BrowserView):

    def __call__(self):
        mail = self.request.get('Mail')
        mail = mail.strip()
        if not mail:
            msg = u'No mail found in request'
            logger.warn(msg)
            return msg
        message = message_from_string(mail)

        logger.debug('--------')
        logger.debug(mail)
        logger.debug('--------')
        logger.debug(message)
        from_addresses = self.get_addresses(message, 'From')
        to_addresses = self.get_addresses(message, 'To')
        if not from_addresses or not to_addresses:
            msg = u'No From or To address found in request'
            logger.warn(msg)
            return msg
        # Pick the first one; strange anyway if there would be more.
        from_name, from_address = from_addresses[0]
        portal = getToolByName(self.context, 'portal_url').getPortalObject()
        email_from_address = portal.getProperty('email_from_address')
        if from_address.lower() == email_from_address.lower():
            # This too easily means that a message sent by Poi ends up
            # being added as a reply on an issue that we have just
            # created.
            msg = u'Ignoring mail from portal email_from_address'
            logger.info(msg)
            return msg

        subject_line = message.get('Subject')
        subjects = []
        decoded = Header.decode_header(subject_line)
        for decoded_string, charset in decoded:
            if charset:
                decoded_string = decoded_string.decode(charset)
            subjects.append(decoded_string)
        subject = u' '.join(subjects)

        logger.debug("Tracker at %s received mail from %r to %r with "
                     "subject %r", self.context.absolute_url(),
                     from_address, to_addresses, subject)
        details, mimetype = self.get_details_and_mimetype(message)
        if not details:
            details = u"Warning: no details found in email"
            mimetype = 'text/plain'
            logger.warn(details)
        logger.debug('Got payload with mimetype %s from email.', mimetype)

        # Create an attachment from the complete email.  Somehow the
        # result is nicer when it is put in a response than in an
        # issue.  Not much we can do about that probably.
        attachment = File('email.eml', 'E-mail', mail)

        tags = self.get_tags(message)
        if tags:
            logger.debug("Determined tags: %r", tags)
        else:
            logger.debug("Could not determine tags.")

        # Store original security manager.
        sm = getSecurityManager()
        # Possibly switch to a different user.
        self.switch_user(from_address)

        issue = self.find_issue(subject, tags, message)
        if issue is None:
            manager = self.get_manager(message, tags)
            logger.debug("Determined manager: %s", manager)
            try:
                issue = self.create_issue(
                    title=subject, details=details, contactEmail=from_address,
                    attachment=attachment, responsibleManager=manager,
                    subject=tags)
            except Unauthorized, exc:
                logger.error(u'Unauthorized to create issue: %s', exc)
                return u'Unauthorized'
            logger.info('Created issue from email at %s', issue.absolute_url())
        else:
            try:
                self.add_response(issue, text=details, mimetype=mimetype,
                                  attachment=attachment)
            except Unauthorized, exc:
                logger.error(u'Unauthorized to add response: %s', exc)
                return u'Unauthorized'
            logger.info('Added mail as response to issue %s',
                        issue.absolute_url())
        # Restore original security manager
        setSecurityManager(sm)
        return mail

    def switch_user(self, from_address):
        """Switch the user.

        This possibly does two things:

        1. Switch to the user that belongs to the given email address.

        2. Give the user the Manage role for the duration of this
           request.

        This view is normally used by the smtp2zope script (or
        something similar) on the local machine.  That script may
        submit anonymously.  That could mean the current user does not
        have enough permissions to submit an issue or add a response.
        So we elevate his privileges by giving him the Manager role.
        But when we do that, this means anonymous users could abuse
        this to submit through the web.  That is not good.  So we only
        elevate privileges when the request originates on the local
        computer.
        """
        sm = getSecurityManager()
        remote_address = self.request.get('HTTP_X_FORWARDED_FOR')
        if not remote_address:
            # Note that request.get('HTTP_something') always returns
            # at least an empty string, also when the key is not in
            # the request, so a default value would be ignored.
            remote_address = self.request.get('REMOTE_ADDR')
        if remote_address not in LISTEN_ADDRESSES:
            return

        # First, see if we can get an existing user based on the From
        # address.
        pas = getToolByName(self.context, 'acl_users')
        users = pas.searchUsers(email=from_address)
        # Also try lowercase
        from_address = from_address.lower()
        if not users:
            users = pas.searchUsers(email=from_address)
        # If 'email' is not in the properties (say: ldap), we can get
        # far too many results; so we do a double check.  Also,
        # apparently ldap can leave '\r\n' at the end of the email
        # address, so we strip it.  And we compare lowercase.
        users = [user for user in users if user.get('email') and
                 user.get('email').strip().lower() == from_address]
        user = None
        changed = False
        if users:
            user_id = users[0]['userid']
            user = pas.getUserById(user_id)
            if user:
                changed = True
        if not user:
            user = sm.getUser()
            # Getting the user id can be tricky.
            if hasattr(user, 'name'):
                # Works for Anonymous Users
                user_id = user.name
            elif hasattr(user, 'getUserId'):
                # Plone users
                user_id = user.getUserId()
            elif hasattr(user, 'getId'):
                # Root zope users
                user_id = user.getId()
            else:
                # Right...
                return

        # See if this user already has the Manager role, otherwise add it.
        if FAKE_MANAGER and not user.allowed(self.context, ('Manager', )):
            logger.debug("Faking Manager role for user %s", user_id)
            user = UnrestrictedUser(user_id, '', ['Manager'], '')
            changed = True
        # Now see if we changed something.
        if not changed:
            return
        newSecurityManager(self.request, user)
        logger.debug("Switched to user %s", user_id)

    def get_addresses(self, message, header_name):
        """Get addresses from the header_name.

        This is usually 'From' or 'To', but other headers may contain
        addresses too, so we allow all, unlike we used to do.

        We expect just one From address and one To address, but
        multiple addresses can also be checked.

        May easily be something ugly like this:
        =?utf-8?q?Portal_Administrator_?=<m.van.rees@zestsoftware.nl>

        From the Python docs:

        decode_header(header)

          Decode a message header value without converting charset.

          Returns a list of (decoded_string, charset) pairs containing
          each of the decoded parts of the header.  Charset is None
          for non-encoded parts of the header, otherwise a lower-case
          string containing the name of the character set specified in
          the encoded string.

          An email.Errors.HeaderParseError may be raised when certain
          decoding error occurs (e.g. a base64 decoding exception).
        """
        if not header_name:
            raise ValueError

        address = message.get(header_name)
        try:
            decoded = Header.decode_header(address)
        except HeaderParseError:
            logger.warn("Could not parse header %r", address)
            return []
        logger.debug('Decoded header: %r', decoded)
        for decoded_string, charset in decoded:
            if charset is not None:
                # Surely this is no email address but a name.
                continue
            if '@' not in decoded_string:
                continue

            return email_utils.getaddresses((decoded_string, ))
        return []

    def get_manager(self, message, tags):
        """Determine the responsible manager.

        A custom implementation could pick a manager based on the tags
        that have already been determined.
        """
        default = '(UNASSIGNED)'
        return default

    def get_tags(self, message):
        """Determine the tags that should be set for this issue.

        You could add tags based on e.g. the To or From address.
        """
        return []

    def add_response(self, issue, text, mimetype, attachment):
        new_response = Response(text)
        new_response.mimetype = mimetype
        new_response.attachment = attachment
        folder = IResponseContainer(issue)
        folder.add(new_response)

    def find_issue_by_number(self, subject, tags='', message=''):
        """Find an issue for which this email is a response.

        In this simple version we only search for email subjects that
        look like they are a response to an email that Poi has sent
        out.  We are just interested in '#123' somewhere in the
        subject, as long as the current tracker has an issue with that
        number.
        """
        number = subject[subject.find('#') + 1:]
        number = number[:number.find(' ')]
        try:
            # We only try this; we do not need the integer value.
            int(number)
        except ValueError:
            number = None
        if number is None:
            return
        issue = getattr(self.context, number, None)
        if issue:
            logger.debug('Found issue by number: #%s', number)
            return issue

    def find_issue(self, subject, tags, message):
        """Find an issue for which this email is a response.

        The default way of finding an issue is simple: we search
        '#123' in the email subject and see if we have such an issue
        number.

        You may want to set ADVANCED_SUBJECT_MATCH to True to search
        for issues matching the given title and tags as well.  Note
        that a Subject like 'printer does not work' or 'Hi' will
        likely match too many unrelated issues, so that may defeat the
        advanced matching.

        The message is passed in as argument as well, to make
        alternative schemes possible.
        """
        if not ADVANCED_SUBJECT_MATCH:
            # We only want the simple form.
            return self.find_issue_by_number(subject, tags, message)
        for bad in ('Re:', 'Fw:', 'Fwd:', 'Antw:'):
            subject = subject.replace(bad, '').replace(bad.upper(), '')
        subject = subject.strip()
        if not subject:
            # C'mon people: learn how to use email!
            return
        # Now we might have something like this:
        # '[Issue Tracker] #45 - Nieuw issue: Heehee'
        tracker_prefix = '[%s]' % self.context.Title()
        if subject.find(tracker_prefix) != -1:
            # Looks like an answer to an issue report from this
            # tracker.  See if we have such an issue number.
            issue = self.find_issue_by_number(subject, tags, message)
            if issue:
                return issue

        search_path = '/'.join(self.context.getPhysicalPath())
        catalog = getToolByName(self.context, 'portal_catalog')
        # Search for issue in this tracker with the same Title and
        # Subject/keywords/tags/categories.  Pick the most recentely
        # created one.

        filter = dict(
            path=search_path,
            Title=cleanup_search_string(subject),
            sort_on='created',
            sort_order='reverse')
        if tags:
            filter['Subject'] = tags
        results = catalog.searchResults(filter)
        if results:
            logger.debug('Found issue by title: %r', subject)
            return results[0].getObject()
        return None

    def get_details_and_mimetype(self, message):
        """Get text and mimetype for the details field of the issue.

        The mimetype is not always needed, but it is good to know
        whether we have html or plain text.

        We prefer to get plain text.  Actually, getting the html from
        the email looks quite okay as long as we put it through the
        safe html transform.
        """
        payload = message.get_payload()
        if not message.is_multipart():
            mimetype = message.get_content_type()
            return payload, mimetype
        for part in payload:
            text, mimetype = self.part_to_text_and_mimetype(part)
            text = text.strip()
            # Might be empty?
            if text:
                return text, mimetype
        return '', 'text/plain'

    def part_to_text_and_mimetype(self, part):
        if part.get_content_type() == 'text/plain':
            return part.get_payload(), 'text/plain'
        tt = getToolByName(self.context, 'portal_transforms')
        if part.get_content_type() == 'text/html':
            mimetype = 'text/x-html-safe'
            safe = tt.convertTo(mimetype, part.get_payload(),
                                mimetype='text/html')
            # Poi responses fail on view when you have the x-html-safe
            # mime type.  Fixed in Poi 1.2.12 (unreleased) but hey, we
            # only need that safe mimetype for the conversion.
            mimetype = 'text/html'
        else:
            # This might not work in all cases, e.g. for attachments,
            # but that is not tested yet.
            mimetype = 'text/plain'
            safe = tt.convertTo(mimetype, part.get_payload())
        if safe is None:
            logger.warn("Converting part to mimetype %s failed.", mimetype)
            return u'', 'text/plain'
        return safe.getData(), mimetype

    def create_issue(self, **kwargs):
        """Create an issue in the given tracker, and perform workflow and
        rename-after-creation initialisation.
        """
        tracker = self.context
        newId = tracker.generateUniqueId('PoiIssue')
        _createObjectByType('PoiIssue', tracker, newId,
                            **kwargs)
        issue = getattr(tracker, newId)
        issue._renameAfterCreation()
        # Some fields have no effect when set with the above
        # _createObjectByType call.
        if 'subject' in kwargs:
            issue.setSubject(kwargs['subject'])

        # Some fields are required.  We pick the first available
        # option.
        issue.setIssueType(tracker.getAvailableIssueTypes()[0]['id'])
        issue.setArea(tracker.getAvailableAreas()[0]['id'])

        # This is done by default already when you do not specify anything:
        #issue.setSeverity(tracker.getDefaultSeverity())
        # This should be set based on the email address that it comes in for:
        #issue.setResponsibleManager('(UNASSIGNED)')

        # This could be interesting:
        #issue.setSteps(steps, mimetype='text/x-web-intelligent')

        if not issue.isValid():
            logger.warn('Issue is not valid. Post will fail.')

        # Creation has finished, so we remove the archetypes flag for
        # that, otherwise the issue gets renamed when someone edits
        # it.
        issue.unmarkCreationFlag()
        notify(ObjectInitializedEvent(issue))
        workflow_tool = getToolByName(tracker, 'portal_workflow')
        # The 'post' transition is only available when the issue is valid.
        workflow_tool.doActionFor(issue, 'post')
        issue.reindexObject()
        return issue

"""
Module designed to make creating and sending emails easy.

1.  Email
    - Uses the Python 3 standard library MIMEMultipart email
      object to construct the email.
"""

import smtplib
from collections import deque
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from getpass import getpass

from jsonconfig import Config

from ._eventloop import MESSAGELOOP
from ._interface import Message


SMTP_SERVERS = {
    'gmail': ('smtp.gmail.com', 465),
    'yahoo': ('smtp.yahoo.com', 465),
    }


class Email(Message):
    """
    Create and send emails using the built-in email package.

    Args:
        :from_: (str) originating email address
            i.e. 'me@here.com'
        :to: (str or list) primary message recipients
             i.e. 'you@there.com' or
                  ['her@there.com', 'him@there.com']
        :server: (str) url of smtp server
            i.e. 'smtp.gmail.com'
        :port: (int) smtp server port
            i.e. 465 or 587
        :password: (str) password for email account
        :cc: (str or list) carbon-copy recipients
        :bcc: (str or list) blind carbon-copy recipients
        :subject: (str) email message subject line
        :body: (str) body text of the message to send
        :attachments: (str or list) files to attach
            i.e. './file1', or
                ['/home/you/file1.txt', '/home/you/file2.pdf']
        :name: (str) use a separate account profile specified by name
        :save: (bool) save pertinent values in the messages config file,
            such as from_, server, port, password (encrypted keyring) to make
            sending messages faster.

    Attributes:
        :message: (MIMEMultipart) current form of the message to be constructed
        :sent_messages: (deque) all messages sent with current SlackWebHook
            object, acting as a log of messages sent in the current session.

    Usage:
        Create an email object with required Args above.
        Send email with self.send() or self.send_async() methods.

    Note:
        Some email servers may require you to modify security setting, such as
        gmail allowing "less secure apps" to access the account.  Otherwise
        failure may occur when attempting to send.
    """

    def __init__(
        self, from_, to=None, server=None, port=465,
        password=None, cc=None, bcc=None, subject='', body='',
        attachments=None, name=None, save=False
    ):

        msg = 'email'

        if name is None:
            profile = 'messages'
        else:
            profile = 'messages_' + name

        with Config(profile) as cfg:
            if msg not in cfg.data.keys():
                cfg.data[msg] = {}
            self.from_ = cfg.data[msg].get('from_', from_)
            self.to, self.cc, self.bcc = to, cc, bcc
            self.server = (server or
                    cfg.data[msg].get('server', self.get_server(self.from_)))
            self.port = cfg.data[msg].get('port', port)

            self.password = password or cfg.pwd.get(name + '_' + msg, None)
            if self.password is None:
                self.password = getpass('\nPassword: ')

            if save:
                for key in ['from_', 'server', 'port']:
                    cfg.data[msg][key] = getattr(self, key)

                cfg.pwd[name + '_' + msg] = self.password
                cfg.kwargs['dump']['indent'] = 4

        self.subject = subject
        self.body = body
        self.attachments = attachments or []
        self.message = None
        self.sent_messages = deque()


    def __repr__(self):
        return '<messages.Email class> at: ' + str(id(self))


    def __str__(self):
        """print(Email(**args)) method."""
        return('MIMEMultipart Email:'
               '\n\tServer: {}:{}'
               '\n\tFrom: {}'
               '\n\tTo: {}'
               '\n\tCc: {}'
               '\n\tBcc: {}'
               '\n\tSubject: {}'
               '\n\tbody: {}...'
               '\n\tattachments: {}'
               .format(self.server, self.port, self.from_, self.to,
                       self.cc, self.bcc, self.subject, self.body[0:40],
                       self.attachments))


    @staticmethod
    def get_server(address):
        """Return an SMTP servername guess from outgoing email address."""
        domain = address.split('@')[1]
        return 'smtp.' + domain


    @staticmethod
    def list_to_string(recipient):
        """
        Format the recipient for the MIMEMultipart() email type.
        If the recipient is a list, then it returns the list as a
        comma separated string.
        example: input=['you@here.com', 'her@there.com']
                 output='you@there.com, her@there.com'
        """
        if recipient:
            if isinstance(recipient, list):
                return ', '.join(recipient)
            return recipient


    def generate_email(self):
        """Put the parts of the email together."""
        self.message = MIMEMultipart()
        self.add_header()
        self.add_body()
        self.add_attachments()


    def add_header(self):
        """Add email header info."""
        self.message['From'] = self.from_
        self.message['Subject'] = self.subject


    def add_body(self):
        """Add body content of email."""
        if self.body:
            b = MIMEText('text', 'plain')
            b.set_payload(self.body)
            self.message.attach(b)


    def add_attachments(self):
        """Add required attachments."""
        num_attached = 0
        if self.attachments:
            if isinstance(self.attachments, str):
                self.attachments = [self.attachments]

            for item in self.attachments:
                doc = MIMEApplication(open(item, 'rb').read())
                doc.add_header('Content-Disposition', 'attachment',
                               filename=item)
                self.message.attach(doc)
                num_attached += 1
        return num_attached


    def get_session(self):
        """Start session with email server."""
        if self.port == 465:
            session = self.get_ssl()
        elif self.port == 587:
            session = self.get_tls()
        session.login(self.from_, self.password)
        return session


    def get_ssl(self):
        """Get an SMTP session with SSL."""
        return smtplib.SMTP_SSL(self.server, self.port)


    def get_tls(self):
        """Get an SMTP session with TLS."""
        session = smtplib.SMTP(self.server, self.port)
        session.ehlo()
        session.starttls()
        session.ehlo()
        return session


    def send(self):
        """
        Send the message.
        Append the repr(self) to self.sent_messages as a history.
        """
        self.generate_email()
        session = self.get_session()

        recipients = []
        if self.to:
            self.message['To'] = self.list_to_string(self.to)
            recipients.append(self.to)
        if self.cc:
            self.message['Cc'] = self.list_to_string(self.cc)
            recipients.append(self.cc)
        if self.bcc:
            self.message['Bcc'] = self.list_to_string(self.bcc)
            recipients.append(self.bcc)

        session.sendmail(self.from_, recipients, self.message.as_string())
        session.quit()
        print('Message sent...')
        self.sent_messages.append(repr(self))


    def send_async(self):
        """Send message asynchronously."""
        MESSAGELOOP.add_message(self)

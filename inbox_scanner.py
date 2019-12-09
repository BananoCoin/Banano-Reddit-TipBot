import sys
import traceback

import praw.exceptions
import prawcore

import util

#import time

class InboxScanner:

    def __init__(self, db, reddit_client, wallet_id, rest_wallet, subreddit, tipper, log):
        self.wallet_id = wallet_id
        self.db = db
        self.reddit_client = reddit_client
        self.rest_wallet = rest_wallet
        self.subreddit = subreddit
        self.log = log

        self.tipper = tipper

    def transfer_funds(self, amount, item, send_address):
        try:
            user_data = util.find_user(item.author.name, self.log, self.db)
            user_address = user_data['ban_address']
            data = {'action': 'account_balance', 'account': user_address}
            parsed_json = self.rest_wallet.post_to_wallet(data, self.log)

            raw_send = str(util.banano_to_raw(float(amount)))
            # check amount left
            if int(raw_send) <= int(parsed_json['balance']):
                data = {'action': 'send', 'wallet': self.wallet_id, 'source': user_address, 'destination': send_address,
                        'amount': int(raw_send)}
                parsed_json = self.rest_wallet.post_to_wallet(data, self.log)
                reply_message = 'Successfully sent %s BANANO to %s\n\nYou can view this transaction on [BananoVault](https://vault.banano.cc/transaction/%s)' % (
                    amount, send_address, str(parsed_json['block']))
                item.reply(reply_message)
            else:
                reply_message = 'Insufficient Banano left in your account to transfer\n\n'
                item.reply(reply_message)
        except:
            reply_message = 'Invalid amount : %s' % amount
            item.reply(reply_message)
            self.log.error("Unexpected error: " + str(sys.exc_info()[0]))
            tb = traceback.format_exc()
            self.log.error(tb)

    def prepare_send(self, commands, item):
        amount = commands[1]
        send_address = commands[2]
        data = {"action": "validate_account_number", "account": send_address}
        check_address = self.rest_wallet.post_to_wallet(data, self.log)
        if len(send_address) != 64 or send_address[:4] != "ban_" or check_address['valid'] != '1':
            self.log.info('Invalid destination address')
            reply_message = 'Invalid destination address : %s' % send_address
            item.reply(reply_message)
        else:
            self.transfer_funds(amount, item, send_address)

    def get_balance(self, item):
        user_data = util.find_user(item.author.name, self.log, self.db)
        user_address = user_data['ban_address']
        data = {'action': 'account_balance', 'account': user_address}
        parsed_json = self.rest_wallet.post_to_wallet(data, self.log)
        ban_balance = util.raw_to_banano(int(parsed_json['balance']))
        self.log.info(str(ban_balance) + ' xrb balance')  
        #rate = util.get_price()
        #if rate is not None:
        #    usd = float(xrb_balance) * rate
        #    reply_message = 'Your balance is :\n\n %s BANANO' % xrb_balance
        #else:
        reply_message = 'Your balance is :\n\n %s BANANO' % ban_balance
        item.reply(reply_message)

    def register_account(self, item, user_table):
        # Generate address
        data = {'action': 'account_create', 'wallet': self.wallet_id}
        parsed_json = self.rest_wallet.post_to_wallet(data, self.log)
        self.log.info(parsed_json['account'])
        # Add to database
        record = dict(user_id=item.author.name, ban_address=parsed_json['account'])
        self.log.info("Inserting into db: " + str(record))
        user_table.insert(record)
        # Reply
        explorer_link = 'https://vault.banano.cc/account/' + parsed_json['account']
        reply_message = 'Thanks for registering, your deposit address is ' + parsed_json['account'] + \
                        ' and you can see your balance here ' + explorer_link + '\r\nFor more details reply with "help"'

        item.reply(reply_message)

    def process_mention(self, item):
        comment = None
        command = ["/u/Banano_TipBot", "u/Banano_TipBot"]
        message_table = self.db['message'] #only needed in case of exceptions to add skipping entries
        try:
            self.log.info("Mention Found")
            comment_parts = item.name.split("_")
            comment_id = comment_parts[len(comment_parts) - 1]
            self.log.info("Comment ID: " + comment_id)
            comment = self.reddit_client.comment(comment_id)
            submission_parts = comment.link_id.split("_")
            submission_id = submission_parts[len(submission_parts) - 1]
            submission = self.reddit_client.submission(submission_id)
            comment.link_author = submission.author.name
        except AttributeError:
            reply_message = 'Could not execute tip because parent author was not found.\n\n' + \
                            ' Also paging /u/chocolatefudcake AttributeError id: ' + item.name + '\n\n'
            item.reply(reply_message)
            record = dict(user_id=None, message_id=item.name)
            self.log.info("skipping comment_id permanently: " + comment_id)
            # comment_id will look like this  eyi9e1w  whereas item.name will look like this t1_eyi9e1w
            message_table.insert(record)
            comment = None
            self.log.error("AttributeError: " + str(sys.exc_info()[0]))
            tb = traceback.format_exc()
            self.log.error(tb)
            
        except:
            try:
                reply_message = 'Could not execute tip. Will not retry. Check if parent post is deleted. \n\n' + \
                                ' Paging /u/chocolatefudcake error id: ' + item.name + '\n\n'
                item.reply(reply_message)
            except:
                self.log.error("Can not reply because comments probably are locked.")
                #APIException: THREAD_LOCKED: 'Comments are locked.' on field 'parent'
            record = dict(user_id=None, message_id=item.name)
            self.log.info("skipping comment_id permanently: " + comment_id)
            message_table.insert(record)
            comment = None
            self.log.error("Unexpected error: " + str(sys.exc_info()[0]))
            tb = traceback.format_exc()
            self.log.error(tb)
            
        if comment is not None:
            self.tipper.parse_comment(comment, command, True)

    def parse_item(self, item):
        self.log.info("New Inbox Received")
        message_table = self.db['message']

        if message_table.find_one(message_id=item.name):
            self.log.info(item.name + " already in db, ignore.")
        else:
            author_obj = item.author
            if author_obj is not None:
                author_name = author_obj.name
                if author_name is not None:
                    author = author_name.lower()
                    if author != "reddit" and author != "banano_tipbot" \
                            and author != "automoderator":
                        user_table = self.db['user']

                        self.log.info("Item is as follows:")
                        self.log.info((vars(item)))

                        self.log.info("Attribute - Item was comment: " + str(item.was_comment))
                        if item.was_comment:
                            self.log.info("Comment subject: " + str(item.subject))
                            if item.subject == 'username mention':
                                self.process_mention(item)
                        else:
                            user_data = util.find_user(item.author.name, self.log, self.db)
                            if user_data is not None:
                                self.log.info('Found Author ' + str(item.author.name))
                                commands = item.body.split(" ")
                                self.log.info(item.body)
                                if 'help' in item.body.lower():
                                    reply_message = 'Help\n\n Reply with the command in the body of text:\n\n  balance - get' \
                                                    + ' your balance\n\n  send <amount> <address> - send BANANO to an external ' \
                                                      'address\n\naddress - get your deposit address\n\nMore info: ' \
                                                    + 'https://np.reddit.com/r/banano/wiki/reddit-tipbot'
                                    item.reply(reply_message)

                                elif 'address' in item.body.lower():
                                    self.log.info(user_data['ban_address'])
                                    reply_message = 'Your deposit address is :\n\n%s' % user_data['ban_address']
                                    item.reply(reply_message)

                                elif 'balance' in item.body.lower():
                                    self.log.info('Getting balance')
                                    self.get_balance(item)

                                elif 'send' in item.body.lower():
                                    self.log.info('Sending BANANO')
                                    if len(commands) > 2:
                                        self.prepare_send(commands, item)
                                    else:
                                        reply_message = 'Sorry I could not parse your request.\n\nWhen making requests only put' + \
                                                        ' one command in the message body with no other text\n\nTry the "help"' + \
                                                        ' command\n\nMore info: ' \
                                                        + 'https://np.reddit.com/r/banano/wiki/reddit-tipbot'
                                        item.reply(reply_message)

                                elif 'register' in item.body.lower():
                                    self.log.info("Already Registered")
                                    reply_message = 'Your account is already registered\n\nTry the "help" command\n\nMore info: ' \
                                                    + 'https://np.reddit.com/r/banano/wiki/reddit-tipbot'
                                    item.reply(reply_message)

                                else:
                                    self.log.info("Bad message")
                                    reply_message = 'Sorry I could not parse your request.\n\nWhen making requests only put' + \
                                                    ' one command in the message body with no other text\n\nTry the "help"' + \
                                                    ' command\n\nMore info: ' \
                                                    + 'https://np.reddit.com/r/banano/wiki/reddit-tipbot'
                                    item.reply(reply_message)
                            else:
                                self.log.info(str(item.author.name) + ' Not in DB')
                                if 'register' in item.body.lower():
                                    self.log.info('Registering account')
                                    self.register_account(item, user_table)

                                else:
                                    self.log.info("Could not parse message")
                                    reply_message = 'Your account is not registered and I could not parse your command\n\n' + \
                                                    ' Reply with "register" in the body of a private message to begin\n\n'
                                    item.reply(reply_message)
            passing = False
            author_obj = item.author
            if author_obj is not None:
                author_name = author_obj.name
                if author_name is not None:
                    passing = True

            if passing:
                record = dict(user_id=item.author.name, message_id=item.name)
            else:
                record = dict(user_id=None, message_id=item.name)

            # Add message to database
            self.log.info("Inserting DM into 'message' db table: " + str(record))
            message_table.insert(record)

    def scan_inbox(self):
        self.log.info('Tracking Inbox')

        try:
            for item in self.reddit_client.inbox.stream():
                self.parse_item(item)

        except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException) as e:
            self.log.error("could not log in because: " + str(e))
            tb = traceback.format_exc()
            self.log.error(tb)
            self.log.error('The thread probably is locked so item.reply(reply_message) will not work and therefore you should delete the mention in' + item.context)

    def run_scan_loop(self):
        while 1:
            #time.sleep(20)
            self.scan_inbox()

import math
import sys
import traceback

import praw.exceptions

import util


class Tipper:
    def __init__(self, db, reddit_client, wallet_id, rest_wallet, log):
        self.wallet_id = wallet_id
        self.db = db
        self.reddit_client = reddit_client
        self.rest_wallet = rest_wallet
        self.log = log

    def comment_reply(self, comment, reply_text, dm_subject="Message from Banano TipBot", dm_fallback=None):
        self.log.info("BOT MAKING COMMENT REPLY:")
        self.log.info(reply_text)
        try:
            comment.reply(reply_text)
        except Exception:
            self.log.info("BOT COMMENT REPLY FAILED, ATTEMPTING DM")
            try:
                if dm_fallback is None:
                    # Send message to author of the comment
                    comment.author.message(dm_subject, reply_text)
                else:
                    # Send message to dm_fallback
                    self.reddit_client.redditor(dm_fallback).message(dm_subject, reply_text)
            except Exception as e:
                self.log.exception(e)
            
    @staticmethod
    def is_usd(amount):
        if amount.startswith("$"):
            return True
        return False

    def send_tip(self, comment, amount, sender_user_address, receiving_address, receiving_user, prior_reply_text):
        try:
#             rate = util.get_price()
#             if rate is None:
#                raise ValueError('Could not retrieve rate')
#
#            formatted_rate = str(format(float(rate), '.3f'))
            formatted_amount = amount
#            if self.is_usd(amount):
#                amount = amount[1:]
#                usd = amount
#                formatted_usd = usd
#                amount = float(amount) / rate
#                formatted_amount = str(format(float(amount), '.2f'))
#            else:
#                usd = float(amount) * rate
#                formatted_usd = str(format(float(usd), '.3f'))

            self.log.info("Sending amount: " + str(amount) + "BANANO")
            data = {'action': 'account_balance',
                    'account': sender_user_address}
            post_body = self.rest_wallet.post_to_wallet(data, self.log)

            # float of total send
            float_amount = float(amount)
            if float_amount > 0:
                raw_send = str(util.banano_to_raw(float_amount))
                self.log.info("Current rai balance: " + str(util.raw_to_banano(int(post_body['balance']))))

                # Add prior reply text to new
                reply_text = ""

                if prior_reply_text is not None:
                    reply_text = prior_reply_text + "\n\n"

                # check amount left
                if int(raw_send) <= int(post_body['balance']):
                    self.log.info( 'comment ' + comment.fullname + ' ' + comment.author.name + ' ' + sender_user_address + ' tipping ' + receiving_address + ' now ')
                    data = {'action': 'send', 'wallet': self.wallet_id, 'source': sender_user_address,
                            'destination': receiving_address, 'amount': int(raw_send)}
                    post_body = self.rest_wallet.post_to_wallet(data, self.log)
                    reply_text = reply_text + \
                                 'Tipped %s BANANO to %s\n\n You can view this transaction on [BananoVault](https://vault.banano.cc/transaction/%s)' \
                                 % (formatted_amount, receiving_user,
                                    str(post_body['block']))
                    reply_text = reply_text + "  \n\nGo to the [wiki]" + \
                                 "(https://np.reddit.com/r/banano/wiki/reddit-tipbot) for more info"
                    dm_subject = 'You tipped %s Banano to /u/%s' % (formatted_amount, comment.author.name)
                    self.comment_reply(comment, reply_text, dm_subject=dm_subject)
                    tip_received_text = 'You were tipped %s BANANO by /u/%s\n\n You can view this transaction on [BananoVault](https://vault.banano.cc/transaction/%s)' \
                                 % (formatted_amount, comment.author.name,
                                    str(post_body['block']))
                    tip_received_text = tip_received_text + "  \n\nGo to the [wiki]" + \
                         "(https://np.reddit.com/r/banano/wiki/reddit-tipbot) for more info"
                    dm_subject = 'You were tipped %s Banano by /u/%s' % (formatted_amount, comment.author.name)
                    self.reddit_client.redditor(receiving_user).message(dm_subject, tip_received_text)
                else:
                    reply_text = reply_text + 'Insufficient Banano! top up your account to tip'
                    dm_subject='Could not send tip to /u/%s!' % receiving_user
                    self.comment_reply(comment, reply_text, dm_subject=dm_subject)
        except TypeError as e:
            reply_message = 'Ooops, I seem to have broken.\n\n' + \
                            ' Paging /u/chocolatefudcake TypeError id: ' + comment.fullname + '\n\n'
            self.comment_reply(comment, reply_message, dm_subject='Reddit TipBot Error', dm_fallback='chocolatefudcake')
            tb = traceback.format_exc()
            self.log.error(e)
            self.log.error(tb)
        except:
            reply_message = 'Ooops, I seem to have broken.\n\n' + \
                            ' Paging /u/chocolatefudcake generic error: ' + comment.fullname + '\n\n'
            self.comment_reply(comment, reply_message, dm_subject='Reddit TipBot Error', dm_fallback='chocolatefudcake')
            self.log.error("Unexpected error in send_tip: " + str(sys.exc_info()[0]))
            tb = traceback.format_exc()
            self.log.error(tb)

    def process_tip(self, amount, comment, receiving_user):
        if receiving_user.lower() == 'giftnano':
            receiving_user = 'giftxrb'
        user_table = self.db['user']
        comment_table = self.db['comments']

        # See if we have an author xrb address and a to xrb address, if not invite to register
        self.log.info("Looking for sender " + "'" + comment.author.name + "'" + " in db")

        sender_user_data = util.find_user(comment.author.name, self.log, self.db)

        if sender_user_data is not None:
            self.log.info('Sender in db')
            # Author registered
            sender_user_address = sender_user_data['ban_address']

            reply_text = None

            user_data = util.find_user(receiving_user, self.log, self.db)
            if user_data is not None:
                receiving_address = user_data['ban_address']
            else:
                self.log.info("Receiving User " + "'" + receiving_user + "'" + " Not in DB - registering")
                # Generate address
                data = {'action': 'account_create',
                        'wallet': self.wallet_id}
                post_body = self.rest_wallet.post_to_wallet(data, self.log)
                self.log.info("Receiving User new account: " + str(post_body['account']))

                # Add to database
                record = dict(user_id=receiving_user, ban_address=post_body['account'])
                self.log.info("Inserting into 'user' db table: " + str(record))
                user_table.insert(record)
                receiving_address = post_body['account']

                reply_text = str(receiving_user) \
                             + ' isn\'t registered, so I made an account for them. ' \
                             + 'They can access it by messaging my inbox.'

            self.send_tip(comment, amount, sender_user_address, receiving_address, receiving_user, reply_text)

        else:
            self.log.info('Sender NOT in db')
            reply_text = 'Hi /u/' + str(comment.author.name) + ', please register by sending me a' \
                         + ' private message with the text "register" in the body of the message.  \n\nGo to the [wiki]' + \
                         "(https://np.reddit.com/r/banano/wiki/reddit-tipbot) for more info"

            self.comment_reply(comment, reply_text, dm_subject='Not registered with Banano TipBot')

        # Add to db
        record = dict(
            comment_id=comment.fullname, to=receiving_user, amount=amount, author=comment.author.name)
        self.log.info("Inserting into 'comments' db table: " + str(record))
        comment_table.insert(record)
        self.log.info('DB updated')

    @staticmethod
    def isfloat(value):
        try:
            if len(value) > 0 and value.startswith("$"):
                value = value[1:]

            float_val = float(value)
            if not math.isnan(float_val):
                return True
        except ValueError:
            return False
        return False

    @staticmethod
    def parse_user(user):
        if user.startswith('/u/'):
            user = user[3:]
        return user

    def user_exists(self, user):
        exists = True
        try:
            self.reddit_client.redditor(user).fullname
        except praw.exceptions.PRAWException:
            self.log.error("User '" + user + "' not found")
            exists = False
        except:
            self.log.error("Unexpected error in send_tip: " + str(sys.exc_info()[0]))
            tb = traceback.format_exc()
            self.log.error(tb)
            exists = False
        return exists

    def invalid_formatting(self, comment, mention):
        comment_table = self.db['comments']
        self.log.info('Invalid formatting')
        if comment.author.name.lower() != 'banano_tipbot':
            if mention:
                self.comment_reply(comment, 'Was I mentioned? I could not parse your request  \n\nGo to the [wiki]' +
                                   '(https://np.reddit.com/r/banano/wiki/reddit-tipbot) to learn how to tip with' +
                                   ' BANANO')
            else:
                self.comment_reply(comment,
                                   'Tip command is invalid. Tip with any of the following formats:  \n\n' +
                                   '`!tipbanano <username> <amount>`  \n\n`!ban <username> <amount>`  \n\n'
                                   + '`/u/banano_tipbot <username> <amount>`  \n\nGo to the [wiki]' +
                                   '(https://np.reddit.com/r/banano/wiki/reddit-tipbot) for more commands')
        record = dict(
            comment_id=comment.fullname, to=None, amount=None, author=comment.author.name)
        self.log.info("Inserting into 'comments' db table: " + str(record))
        comment_table.insert(record)
        self.log.info('DB updated')

    def process_command(self, comment, receiving_user, amount):
        # parse reddit username
        receiving_user = self.parse_user(receiving_user)
        self.log.info("Receiving user: " + receiving_user)
        self.process_tip(amount, comment, receiving_user)

    def validate_double_parameter_tip(self, parts_of_comment, command_index):
        receiving_user = parts_of_comment[command_index + 1]
        amount = parts_of_comment[command_index + 2]
        passing = False
        if self.isfloat(amount):
            # valid amount input
            # parse reddit username
            receiving_user = self.parse_user(receiving_user)
            # check if that is a valid reddit
            if self.user_exists(receiving_user):
                passing = True

        return passing

    def validate_single_parameter_tip(self, parts_of_comment, command_index):
        # check that index+1 is a float before proceeding to extract receiving_user
        amount = parts_of_comment[command_index + 1]
        if self.isfloat(amount):
            return True
        return False

    def process_single_parameter_tip(self, comment, amount):
        # initialize skip deleted variable 
        is_skipped = 0
        # Is this a root comment?
        is_root = comment.is_root
        self.log.info("Root comment? " + str(comment.is_root))
        if is_root:
            receiving_user = comment.link_author
        else:
            # Get parent
            parent = comment.parent()
            try:
                self.log.info("Trying to tip this parent: ")
                self.log.info(vars(parent))
                receiving_user = parent.author.name
            except:
                # redefine variable if parent does not exist anymore 
                is_skipped = 1
                self.log.info("Parent apparently does not exist anymore. skipping.")
                # Add to db so it'll be ignored next run
                record = dict(
                    comment_id=comment.fullname, to='unknown-deleted', amount=amount, author=comment.author.name)
                self.log.info("Inserting skipped deleted comment into 'comments' db table: " + str(record))
                comment_table = self.db['comments']
                comment_table.insert(record)
                
        # skip if parent was deleted
        if (not is_skipped):
            self.process_command(comment, receiving_user, amount)

    def parse_tip(self, comment, parts_of_comment, command_index, mention):
        # get a reference to the table 'comments'
        comment_table = self.db['comments']

        # Save the comment id in a database so we don't repeat this
        if comment.created_utc < 1575650749.0 :
            # do nothing if comment is older than the checkpoint
            # self.log.info(comment.fullname + ' before checkpoint - passing') 
            pass
        elif comment_table.find_one(comment_id=comment.fullname):
            self.log.info(comment.fullname + ' already in db, ignore')
        else:
            self.log.info('Comment is not in database yet:')
            self.log.info((vars(comment)))
            author = comment.author.name.lower()
            try:
                subreddit_name = comment.subreddit.display_name;
            except:
                subreddit_name = ''

            if author != "reddit" and author != "banano_tipbot" \
                    and author != "automoderator":
                length = len(parts_of_comment)
                passing = False

                # check that index+2 exists in array
                if command_index + 2 < length:
                    # check for both tip formats
                    # !tipxrb <user> <amount>
                    # !tipxrb <amount>
                    receiving_user = parts_of_comment[command_index + 1]
                    amount = parts_of_comment[command_index + 2]
                    if self.validate_double_parameter_tip(parts_of_comment, command_index):
                        self.process_command(comment, receiving_user, amount)
                        passing = True
                    elif self.validate_single_parameter_tip(parts_of_comment, command_index):
                        amount = parts_of_comment[command_index + 1]
                        self.process_single_parameter_tip(comment, amount)
                        passing = True

                elif command_index + 1 < length:
                    # check for one tip format
                    # !tipxrb <amount>
                    if self.validate_single_parameter_tip(parts_of_comment, command_index):
                        amount = parts_of_comment[command_index + 1]
                        self.process_single_parameter_tip(comment, amount)
                        passing = True

                if not passing:
                    # invalid command
                    self.invalid_formatting(comment, mention)
            else:
                # Add to db
                record = dict(
                    comment_id=comment.fullname, to=None, amount=None, author=comment.author.name)
                self.log.info("Inserting into 'comments' db table: " + str(record))
                comment_table.insert(record)
                self.log.info('DB updated')

    def parse_comment(self, comment, commands, mention):
        comment_split_newlines = comment.body.lower().splitlines()
        found = False
        for line in comment_split_newlines:
            parts_of_comment = line.split(" ")
            for command in commands:
                command = command.lower()
                if command in parts_of_comment and not found:
                    found = True
                    self.log.info('Found tip reference in comments.')

                    command_index = parts_of_comment.index(command)
                    self.parse_tip(comment, parts_of_comment, command_index, mention)

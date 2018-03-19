import datetime
import logging

import dataset
import praw

import inbox_scanner
import rpc_wallet
import settings
import tipper


class InboxLauncher:

    # Multiprocessing not completely functional currently, launch the scanners separately

    def __init__(self):
        self.reddit_client = praw.Reddit(user_agent=settings.user_agent,
                                         client_id=settings.client_id,
                                         client_secret=settings.client_secret,
                                         username=settings.username,
                                         password=settings.password)
        self.db = dataset.connect(settings.connection_string)
        self.wallet_id = settings.wallet_id

        self.rest_wallet = rpc_wallet.RestWallet(settings.node_ip, settings.node_port)

        self.subreddit = settings.subreddit

        log_file_name = "inbox_scanner_" + str(datetime.datetime.now().isoformat()) + ".log"
        logging.basicConfig(filename=log_file_name, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
        log = logging.getLogger("inbox")

        self.log = log

        self.tipper = tipper.Tipper(self.db, self.reddit_client, self.wallet_id, self.rest_wallet, self.log)

    def main(self):
        inbox = inbox_scanner.InboxScanner(self.db, self.reddit_client, self.wallet_id, self.rest_wallet,
                                           self.subreddit, self.tipper, self.log)
        inbox.run_scan_loop()


if __name__ == '__main__':
    launcher = InboxLauncher()
    launcher.main()

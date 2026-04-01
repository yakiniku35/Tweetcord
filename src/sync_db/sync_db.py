import asyncio

from tweety import Twitter
from tweety.exceptions import TwitterError

from src.log import setup_logger
from src.utils import get_accounts

log = setup_logger(__name__)

_SELF_FOLLOW_CODE = 158


async def sync_db(follow_list: dict[str, str]) -> None:

    apps: dict[str, Twitter] = {}
    for account_name, _ in get_accounts().items():
        app = Twitter(account_name)
        await app.connect()
        apps[account_name] = app

    for user_id, client_used in follow_list.items():
        app = apps[client_used]
        try:
            await app.follow_user(user_id)
            await app.enable_user_notification(user_id)
        except TwitterError as e:
            if e.error_code == _SELF_FOLLOW_CODE:
                log.warning(f"skipping user {user_id}: cannot follow yourself (TwitterError {_SELF_FOLLOW_CODE})")
            else:
                log.error(f"TwitterError while syncing user {user_id}: {e}")
        await asyncio.sleep(1)

    log.info('synchronization with database completed')
